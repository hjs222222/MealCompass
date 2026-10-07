import json
import logging

from core.logging import configure_logging


def test_json_logging_contains_required_fields(capsys) -> None:
    configure_logging("INFO")
    logger = logging.getLogger("test.logging")

    logger.info("hello", extra={"request_id": "req-log"})

    captured = capsys.readouterr().err.strip()
    payload = json.loads(captured)
    assert payload["timestamp"]
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logging"
    assert payload["message"] == "hello"


def test_json_logging_preserves_safe_extra_fields_and_serializes_values(capsys) -> None:
    configure_logging("INFO")
    logger = logging.getLogger("test.logging.extras")
    logger.info(
        "structured",
        extra={"provider": "local", "degraded": True, "operation": "embed", "secret": "hidden", "obj": object()},
    )

    payload = json.loads(capsys.readouterr().err.strip())
    assert payload["provider"] == "local"
    assert payload["degraded"] is True
    assert payload["operation"] == "embed"
    assert "secret" not in payload
    assert payload["obj"]


def test_json_logging_includes_exception_traceback(capsys) -> None:
    configure_logging("INFO")
    logger = logging.getLogger("test.logging.exception")
    try:
        raise RuntimeError("private failure")
    except RuntimeError:
        logger.exception("failed", extra={"operation": "test"})

    payload = json.loads(capsys.readouterr().err.strip())
    assert "RuntimeError: private failure" in payload["traceback"]
