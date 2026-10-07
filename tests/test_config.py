from mirrorguard.config import Settings


def test_defaults_work_without_any_environment(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.database_url.startswith("sqlite")
    assert len(settings.target_models) >= 1


def test_target_models_accept_a_comma_separated_list(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MG_TARGET_MODELS", "groq/a, groq/b,")
    monkeypatch.setenv("MG_LLM_REQUESTS_PER_MINUTE", "10")
    settings = Settings()
    assert settings.target_models == ["groq/a", "groq/b"]
    assert settings.llm_requests_per_minute == 10
