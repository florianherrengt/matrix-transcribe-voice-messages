import os
import pytest

from src.config import Config


def test_config_loads_from_env(monkeypatch):
    monkeypatch.setenv("MATRIX_HOMESERVER", "https://matrix.example.com")
    monkeypatch.setenv("MATRIX_USER_ID", "@bot:example.com")
    monkeypatch.setenv("MATRIX_PASSWORD", "secret123")
    monkeypatch.setenv("PARAKEET_URL", "http://oxygen:5092")
    monkeypatch.delenv("MATRIX_DEVICE_ID", raising=False)
    monkeypatch.delenv("STORE_PATH", raising=False)

    config = Config.from_env()

    assert config.homeserver == "https://matrix.example.com"
    assert config.user_id == "@bot:example.com"
    assert config.password == "secret123"
    assert config.device_id is None
    assert config.parakeet_url == "http://oxygen:5092"
    assert config.store_path == "./store"


def test_config_with_optional_fields(monkeypatch):
    monkeypatch.setenv("MATRIX_HOMESERVER", "https://matrix.example.com")
    monkeypatch.setenv("MATRIX_USER_ID", "@bot:example.com")
    monkeypatch.setenv("MATRIX_PASSWORD", "secret123")
    monkeypatch.setenv("PARAKEET_URL", "http://oxygen:5092")
    monkeypatch.setenv("MATRIX_DEVICE_ID", "DEVICEXYZ")
    monkeypatch.setenv("STORE_PATH", "/data/store")

    config = Config.from_env()

    assert config.device_id == "DEVICEXYZ"
    assert config.store_path == "/data/store"


def test_config_missing_required_raises(monkeypatch):
    for key in [
        "MATRIX_HOMESERVER",
        "MATRIX_USER_ID",
        "MATRIX_PASSWORD",
        "PARAKEET_URL",
    ]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValueError, match="Missing required"):
        Config.from_env()
