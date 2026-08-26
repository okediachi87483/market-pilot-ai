from app.core.config import Settings, get_settings


def test_settings_load_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "development"
    assert settings.api_port == 8000
    assert settings.postgres_db == "marketpilot"


def test_settings_read_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("POSTGRES_DB", "custom_db")
    settings = Settings(_env_file=None)
    assert settings.app_env == "test"
    assert settings.postgres_db == "custom_db"


def test_database_url_assembled_from_parts() -> None:
    settings = Settings(
        _env_file=None,
        postgres_user="u",
        postgres_password="p",
        postgres_host="h",
        postgres_port=5555,
        postgres_db="d",
    )
    assert settings.database_url == "postgresql+asyncpg://u:p@h:5555/d"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
