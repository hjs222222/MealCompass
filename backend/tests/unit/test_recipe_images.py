from fastapi.testclient import TestClient

from core.config import Settings
from main import create_app


def test_source_image_is_served_with_image_content_type() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))
    response = client.get("/recipe-images/aquatic/鳊鱼炖豆腐/鳊鱼炖豆腐.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content.startswith(b"\xff\xd8")


def test_raw_markdown_is_not_exposed_as_image() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))
    assert client.get("/recipe-images/aquatic/鳊鱼炖豆腐/鳊鱼炖豆腐.md").status_code == 404


def test_parent_path_cannot_escape_image_root() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))
    assert client.get("/recipe-images/%2e%2e/%2e%2e/README.md").status_code == 404
