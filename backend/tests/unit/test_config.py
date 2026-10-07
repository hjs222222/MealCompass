import pytest
from pydantic import ValidationError

from core.config import Settings


def test_settings_without_env_file_use_dev_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "dev"
    assert settings.app_version == "0.1.0"


def test_settings_reject_invalid_app_env() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="invalid")


def test_prod_default_jwt_secret_is_rejected_at_runtime() -> None:
    settings = Settings(_env_file=None, app_env="prod")
    with pytest.raises(ValueError, match="JWT_SECRET"):
        settings.validate_runtime()


def test_prod_valid_jwt_secret_is_accepted() -> None:
    settings = Settings(_env_file=None, app_env="prod", jwt_secret="a-secure-secret")
    settings.validate_runtime()


def test_app_version_can_be_overridden() -> None:
    assert Settings(_env_file=None, app_version="2.4.0").app_version == "2.4.0"
