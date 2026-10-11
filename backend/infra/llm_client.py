"""LLM 客户端：OpenAI 兼容的 `/chat/completions`（DeepSeek / SiliconFlow 等同协议服务）。

契约（`domain/ports.LLMClient`）：`model` 是实例属性，`complete()` 返回纯文本。
额外能力：
- `complete_with_usage()` 额外返回 `{"input_tokens", "output_tokens"}`，供 trace 的 `usage_details` 使用
  （CONVENTIONS §4.5：LLM 调用必须带 model + usage_details，否则成本视图为空）；
- `strip_code_fence()` 兼容模型把 JSON 包在 ```` ```json ... ``` ```` 里的情况；
- 对 429 / 5xx 做指数退避重试（基数 0.5s，最多 3 次）；
- 连接池惰性创建，`aclose()` 只关自己创建的（与 `infra/embedding_client.py` 的 `_owns_client` 模式一致）。

分层：本模块在 `infra`，只依赖 `core` / `domain` 与标准库，**不** import `agents` / `services` / `api`。
安全：`api_key` 只放进请求头，绝不打印、绝不写日志、绝不进 trace。

可观测性说明：本客户端**不**自己记 span（`infra` 不依赖 `observability` 的调用点语义），
由调用方（`agents/` 或 `services/`）用 `SpanName.GENERATE_RECOMMENDATIONS`
把 `model` + `complete_with_usage()` 的 usage 记成 `generation`。
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence

import httpx

from core.config import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BASE_DELAY = 0.5
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

_FENCE_OPEN = re.compile(r"^```[A-Za-z0-9_+-]*[ \t]*")
_FENCE_CLOSE = re.compile(r"[ \t]*```$")


def strip_code_fence(text: str) -> str:
    """剥掉 ```` ```json ... ``` ```` 围栏并去掉首尾空白。

    模型被要求输出 JSON 时经常自带 Markdown 围栏（有时还没有收尾围栏、语言标识后有空格），
    这里统一剥掉，让调用方拿到可直接 `json.loads` 的文本。无围栏时只做 `strip()`。
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    stripped = _FENCE_OPEN.sub("", stripped, count=1)
    stripped = _FENCE_CLOSE.sub("", stripped, count=1)
    return stripped.strip()


class RemoteLLM:
    """OpenAI 兼容的文本补全客户端（远程，无本地兜底）。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
        client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max(0, max_retries)
        self._retry_base_delay = max(0.0, retry_base_delay)
        self._client = client
        self._owns_client = client is None
        self._sleep = sleep or asyncio.sleep

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        """只关自己创建的连接池；外部注入的由调用方负责。"""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.1,
        response_format: str | None = None,
    ) -> str:
        """按消息生成文本（`response_format="json_object"` 时要求服务端返回 JSON）。"""
        content, _ = await self.complete_with_usage(
            messages,
            temperature=temperature,
            response_format=response_format,
        )
        return content

    async def complete_with_usage(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.1,
        response_format: str | None = None,
    ) -> tuple[str, dict[str, int]]:
        """同 `complete()`，额外返回 `{"input_tokens", "output_tokens"}` 供 trace 记账。

        服务端没给 usage 时记 0（结构稳定，调用方不用判空）。
        """
        payload = self._build_payload(messages, temperature=temperature, response_format=response_format)
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base_url}/chat/completions"
        client = self._get_client()

        for attempt in range(self._max_retries + 1):
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code in RETRY_STATUS and attempt < self._max_retries:
                delay = self._retry_base_delay * 2**attempt
                logger.warning(
                    "LLM 返回 %s，%.2fs 后第 %d 次重试：model=%s",
                    response.status_code,
                    delay,
                    attempt + 1,
                    self.model,
                )
                await self._sleep(delay)
                continue
            response.raise_for_status()
            content, usage = self._parse(response.json())
            return content, usage

        raise RuntimeError("unreachable: 重试循环必然 return 或 raise")  # pragma: no cover

    def _build_payload(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float,
        response_format: str | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": temperature,
        }
        if response_format is not None:
            payload["response_format"] = {"type": response_format}
        return payload

    @staticmethod
    def _parse(data: Mapping[str, object]) -> tuple[str, dict[str, int]]:
        usage_block = data.get("usage")
        prompt_tokens = usage_block.get("prompt_tokens") if isinstance(usage_block, Mapping) else None
        completion_tokens = usage_block.get("completion_tokens") if isinstance(usage_block, Mapping) else None
        return _extract_content(data), {
            "input_tokens": prompt_tokens if isinstance(prompt_tokens, int) else 0,
            "output_tokens": completion_tokens if isinstance(completion_tokens, int) else 0,
        }


def _extract_content(data: Mapping[str, object]) -> str:
    """取 `choices[0].message.content` 并剥围栏；结构不对时返回空串而不是崩。"""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, Mapping):
        return ""
    message = first.get("message")
    if not isinstance(message, Mapping):
        return ""
    content = message.get("content")
    return strip_code_fence(content) if isinstance(content, str) else ""


def build_llm_client(settings: Settings | None = None) -> RemoteLLM:
    """按配置装配 LLM 客户端；key 未配置时用空串（服务端会返回 401，调用方负责降级）。"""
    settings = settings or get_settings()
    return RemoteLLM(
        api_key=settings.llm_api_key or "",
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
