"""`infra/db.py` 的单测：单例语义、配置传递、事务边界与释放。

**这里有个容易踩的坑**：`create_async_engine` 是**惰性**的——它只建对象，不建连接。
所以本文件**不需要真 PostgreSQL**，也不会触发任何网络 IO。也就是说 `infra/db.py`
之前 64% 的覆盖率不是"环境不可测"，而是"没人写测试"。

约定（与仓库其它单测一致）：每个用例前后重置模块级单例，避免用例间串扰。
"""

from __future__ import annotations

import pytest

from infra import db


@pytest.fixture(autouse=True)
def _reset_db_module_state() -> None:
    """把模块级单例清空，保证用例互相独立。"""
    db._engine = None
    db._session_factory = None
    yield
    db._engine = None
    db._session_factory = None


class _FakeTransaction:
    """假事务：记录 enter/exit，可注入异常以验证回滚路径。"""

    def __init__(self, log: list[str], *, fail: bool = False) -> None:
        self._log = log
        self._fail = fail
        self.exited_with: tuple[object, object, object] | None = None

    async def __aenter__(self) -> _FakeTransaction:
        self._log.append("begin")
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self.exited_with = (exc_type, exc, tb)
        self._log.append("rollback" if exc_type is not None else "commit")
        return False  # 不吞异常


class _FakeSession:
    """假 session：只需支持 `async with` 与 `.begin()`。"""

    def __init__(self, log: list[str], *, fail: bool = False) -> None:
        self._log = log
        self._fail = fail

    async def __aenter__(self) -> _FakeSession:
        self._log.append("session-enter")
        if self._fail:
            raise RuntimeError("模拟建连失败")
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self._log.append("session-exit")
        return False

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction(self._log)


def _install_fake_factory(monkeypatch: pytest.MonkeyPatch, log: list[str], *, fail: bool = False) -> None:
    """把 `_session_factory` 换成一个返回假 session 的可调用对象。"""

    def factory() -> _FakeSession:
        log.append("factory-called")
        return _FakeSession(log, fail=fail)

    monkeypatch.setattr(db, "_session_factory", factory)


def test_get_engine_is_process_singleton() -> None:
    """同一进程内多次调用必须拿到同一个 engine（否则每次请求都新建连接池）。"""
    assert db.get_engine() is db.get_engine()


def test_get_engine_uses_configured_dsn() -> None:
    """DSN 只能来自 core.config，不能硬编码。

    注意：`str(engine.url)` 会把密码渲染成 `***`（SQLAlchemy 的防泄漏设计），
    所以这里必须用 `render_as_string(hide_password=False)` 取真实 DSN——**用 `str()`
    去断言 DSN 会被静默"通过"**（两边都是 `***` 时看起来一样，实际可能是别的库）。
    """
    from core.config import get_settings

    engine = db.get_engine()
    assert engine.url.render_as_string(hide_password=False) == get_settings().database_url
    assert str(engine.url).endswith("@localhost:5432/mealcompass")  # 默认渲染确实脱敏


def test_get_engine_hides_password_in_str() -> None:
    """反向断言：日志里不小心 `str(engine.url)` 时，密码不会泄漏。"""
    assert "***" in str(db.get_engine().url)
    assert "mealcompass:mealcompass@" not in str(db.get_engine().url)


def test_get_engine_enables_pool_pre_ping() -> None:
    """`pool_pre_ping=True` 是长连接必需项（否则 Docker 重启后拿到死连接）。"""
    assert db.get_engine().pool._pre_ping is True


def test_get_session_factory_is_singleton_and_shares_engine() -> None:
    factory = db.get_session_factory()
    assert factory is db.get_session_factory()
    assert factory.kw["bind"] is db.get_engine()


def test_get_session_factory_does_not_expire_objects_on_commit() -> None:
    """`expire_on_commit=False`：commit 后仍能读对象属性，避免懒加载触发意外 IO。"""
    assert db.get_session_factory().kw["expire_on_commit"] is False


async def test_session_scope_commits_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常退出 → 事务提交，且 session 被正确关闭。"""
    log: list[str] = []
    _install_fake_factory(monkeypatch, log)

    async with db.session_scope() as session:
        log.append("body")
        assert isinstance(session, _FakeSession)

    assert log == ["factory-called", "session-enter", "begin", "body", "commit", "session-exit"]


async def test_session_scope_rolls_back_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """body 抛异常 → 事务回滚，而且**异常必须继续向上抛**（不能被 db 层吞掉）。"""
    log: list[str] = []
    _install_fake_factory(monkeypatch, log)

    with pytest.raises(ValueError, match="业务错误"):
        async with db.session_scope():
            raise ValueError("业务错误")

    assert "rollback" in log
    assert "commit" not in log


async def test_session_scope_propagates_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """建连失败时不得进入事务体（否则会拿 None session 做查询）。"""
    log: list[str] = []
    _install_fake_factory(monkeypatch, log, fail=True)

    with pytest.raises(RuntimeError, match="模拟建连失败"):
        async with db.session_scope():
            log.append("不应到达")

    assert "不应到达" not in log
    assert "begin" not in log


async def test_dispose_engine_clears_singletons() -> None:
    """`dispose_engine()` 后单例必须归零，否则下次 `get_engine()` 会复用已释放的池。"""
    first = db.get_engine()
    db.get_session_factory()
    await db.dispose_engine()
    assert db._engine is None
    assert db._session_factory is None
    assert db.get_engine() is not first  # 必须是新对象（旧池已释放）


async def test_dispose_engine_is_idempotent() -> None:
    """重复 dispose 不能抛（应用关闭路径可能被调用两次）。"""
    await db.dispose_engine()
    await db.dispose_engine()
    assert db._engine is None
