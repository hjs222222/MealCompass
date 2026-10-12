"""Exercise batch SQL and preserve original step content."""

from uuid import UUID

from sqlalchemy.dialects import postgresql

from infra.recipe_steps import SqlRecipeStepsReader


class Result:
    def all(self) -> list[tuple[UUID, str]]:
        return [(UUID(int=1), "切菜。"), (UUID(int=1), "炒熟。"), (UUID(int=2), "煮熟。")]


class Connection:
    def __init__(self) -> None:
        self.statement = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        pass

    async def execute(self, statement):
        self.statement = statement
        return Result()


class Engine:
    def __init__(self) -> None:
        self.connection = Connection()
        self.calls = 0

    def connect(self):
        self.calls += 1
        return self.connection


async def test_batch_reader_limits_ids_orders_steps_and_preserves_content() -> None:
    engine = Engine()
    result = await SqlRecipeStepsReader(engine).get_steps([str(UUID(int=1)), str(UUID(int=2))])
    assert result[str(UUID(int=1))] == ["切菜。", "炒熟。"]
    assert result[str(UUID(int=2))] == ["煮熟。"]
    sql = str(engine.connection.statement.compile(dialect=postgresql.dialect()))
    assert "WHERE recipe_steps.recipe_id IN" in sql
    assert "ORDER BY recipe_steps.recipe_id, recipe_steps.step_no" in sql


async def test_empty_ids_never_open_connection() -> None:
    engine = Engine()
    assert await SqlRecipeStepsReader(engine).get_steps([]) == {}
    assert engine.calls == 0
