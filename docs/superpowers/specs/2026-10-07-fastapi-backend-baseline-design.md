# FastAPI 后端基线设计

## 目标

建立一个可启动、可检查、可扩展的 FastAPI 后端基线，完成 T1.14、T1.15、T1.16，为后续认证、推荐 Agent 和前端接入提供稳定边界。

## 范围

本阶段只实现：

- FastAPI 应用入口与薄路由
- 健康检查与版本接口
- 依赖注入出口
- pydantic-settings 配置外置及 dev/prod 安全边界
- 统一异常模型与 JSON 响应
- request ID、中间件和结构化日志
- 对应单元/接口测试

本阶段不实现认证、用户画像、推荐 Agent、业务数据库仓储或前端页面。

## 目录与职责

```text
backend/
  main.py                 # FastAPI app factory、生命周期与全局 middleware/handlers
  api/
    __init__.py
    deps.py               # FastAPI Depends 统一出口
    v1/
      __init__.py
      health.py           # /health、/version 薄路由
  core/
    config.py             # 唯一配置入口
    exceptions.py         # 领域/应用异常与统一响应模型
    logging.py            # JSON formatter、request-id context 与配置
```

`api` 只做请求/响应和依赖调用，不直连 infra；`core` 不承载业务逻辑；健康检查只报告进程和配置降级状态，不泄露密钥、连接串或完整异常堆栈。

## API 契约

- `GET /health`：返回 `status`, `environment`, `tracing_enabled`, `tracing_degraded`。
- `GET /version`：返回 `name`, `version`, `environment`。
- 未处理异常：返回统一 JSON `{code, message, request_id}`，HTTP 500；生产响应不包含堆栈。
- 请求头 `X-Request-ID`：客户端提供且合法时复用，否则生成 UUID；响应始终回传该 ID。

## 配置契约

继续使用 `Settings(BaseSettings)` 和 `.env`/环境变量。增加稳定的应用版本字段和环境枚举校验。生产环境若仍使用默认 JWT secret，应在配置校验/启动阶段失败；开发环境允许默认值以便本地启动。健康接口只能输出非敏感配置摘要。

## 日志契约

输出 JSON 行，至少包含：`timestamp`, `level`, `logger`, `message`, `request_id`。请求完成日志增加 `method`, `path`, `status_code`, `duration_ms`。request ID 使用 context variable，避免跨协程污染；未配置 Langfuse 时只记录本地结构化日志。

## 验收

- `TestClient` 可调用 `/health`、`/version`。
- 自定义 request ID 被透传，缺失时自动生成。
- 统一异常响应包含 request ID 且不泄露 traceback。
- 默认生产 JWT secret 被拒绝，开发配置可加载。
- Ruff、格式检查和全量 pytest 通过。
