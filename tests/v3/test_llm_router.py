"""speky_llm: model refs, .env keys, and the removed host mode."""
import pytest

import speky_llm
from speky_core.errors import SpekyError


def test_resolve_and_dotenv(tmp_path, monkeypatch):
    monkeypatch.setattr(speky_llm, "GLOBAL_CONFIG", tmp_path / "none.yaml")
    for k in ("SPEKY_MODEL", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    (tmp_path / ".env").write_text('# keys\nexport OPENROUTER_API_KEY="sk-or-1"\n')
    r = speky_llm.LLMRouter(project_root=tmp_path, log=lambda m: None)
    assert r.resolve("openrouter/moonshotai/kimi-k2") == ("openrouter", "moonshotai/kimi-k2")
    assert r.resolve("claude-sonnet-4-5")[0] == "anthropic"
    assert r.status("openrouter") == "ready"
    assert "host" not in r.providers


def test_runner_explains_removed_host_model(tmp_path, monkeypatch):
    from speky_core import runner
    from speky_core.items import Project
    monkeypatch.setattr(speky_llm, "GLOBAL_CONFIG", tmp_path / "none.yaml")
    monkeypatch.setenv("SPEKY_MODEL", "host")
    with pytest.raises(SpekyError) as e:
        runner.make_completer(Project(tmp_path))
    assert "host" in e.value.message and "speky config model" in e.value.fix


def test_v2_config_model_is_used_unless_it_is_v2s_default(tmp_path, monkeypatch):
    monkeypatch.setattr(speky_llm, "GLOBAL_CONFIG", tmp_path / "none.yaml")
    monkeypatch.delenv("SPEKY_MODEL", raising=False)
    (tmp_path / ".speky").mkdir()
    cfg = tmp_path / ".speky" / "config.yaml"
    cfg.write_text("ide: windsurf\nmodel: openrouter/moonshotai/kimi-k2\n")
    assert speky_llm.LLMRouter(project_root=tmp_path, log=lambda m: None).model_ref == "openrouter/moonshotai/kimi-k2"
    cfg.write_text("model: claude-sonnet-4-20250514\n")
    assert speky_llm.LLMRouter(project_root=tmp_path, log=lambda m: None).model_ref != "claude-sonnet-4-20250514" \
        or __import__("os").environ.get("ANTHROPIC_API_KEY")
