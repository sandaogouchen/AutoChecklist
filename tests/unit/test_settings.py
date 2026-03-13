from pathlib import Path

from app.config.settings import Settings


def test_settings_uses_repo_root_env_file() -> None:
    env_file = Path(Settings.model_config["env_file"])

    assert env_file.is_absolute()
    assert env_file == Path(__file__).resolve().parents[2] / ".env"


def test_settings_ignore_empty_environment_values(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "LLM_API_KEY=file-key",
                "LLM_BASE_URL=https://example.com/v1",
                "LLM_MODEL=test-model",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LLM_API_KEY", "")

    settings = Settings(_env_file=env_file)

    assert settings.llm_api_key == "file-key"
