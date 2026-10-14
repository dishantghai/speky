"""`speky run`: the built-in agent loop, driven by a scripted model."""
import json

from speky_core.runner import Runner

from .conftest import GOOD_SPEC, git


class Script:
    def __init__(self, *calls):
        self.calls = list(calls)
        self.prompts = []
        self.systems = []

    def __call__(self, prompt, system):
        self.prompts.append(prompt)
        self.systems.append(system)
        nxt = self.calls.pop(0)
        return nxt if isinstance(nxt, str) else json.dumps(nxt)


def runner(project, script, **kw):
    return Runner(project, script, interactive=False, log=lambda m: None, **kw)


def test_runner_reads_writes_and_uses_speky(project):
    (project.root / "app.py").write_text("def hello():\n    return 'hi'\n")
    script = Script(
        {"tool": "read_file", "args": {"path": "app.py"}, "why": "see the code"},
        {"tool": "edit_file", "args": {"path": "app.py", "old": "'hi'", "new": "'hello'"}},
        {"tool": "speky", "args": {"argv": ["spec", "Greeting"]}},
        {"tool": "write_file", "args": {"path": ".speky/specs/001-greeting/spec.md", "content": GOOD_SPEC}},
        {"tool": "speky", "args": {"argv": ["check", "001"]}},
        {"tool": "finish", "args": {"summary": "done"}},
    )
    out = runner(project, script).run("Make hello say hello")
    assert out["finished"] and out["summary"] == "done"
    assert "return 'hello'" in (project.root / "app.py").read_text()
    assert '"converged": true' in out["steps"][4]["observation"]
    assert "1: def hello():" in script.prompts[1]
    assert "## Skill: speky" in script.systems[0] and "SPEKY workflow" in script.systems[0]


def test_runner_confines_files_and_shell(project):
    script = Script(
        {"tool": "read_file", "args": {"path": "../../etc/passwd"}},
        {"tool": "write_file", "args": {"path": ".git/config", "content": "x"}},
        {"tool": "run", "args": {"command": "rm -rf /"}},
        {"tool": "run", "args": {"command": "git status"}},
        {"tool": "run", "args": {"command": "git status; rm -rf ."}},
        {"tool": "speky", "args": {"argv": ["run", "again"]}},
        {"tool": "finish", "args": {"summary": "x"}},
    )
    git(project.root, "init", "-q")
    out = runner(project, script).run("try things")
    obs = [s["observation"] for s in out["steps"]]
    assert obs[0].startswith("refused: ") and "outside the repository" in obs[0]
    assert "off limits" in obs[1]
    assert obs[2].startswith("refused") and obs[3].startswith("exit 0") and obs[4].startswith("refused")
    assert obs[5].startswith("refused")


def test_runner_allows_the_projects_test_command(project):
    from speky_core import config
    config.save(project.root, {**config.DEFAULTS, "verify_command": "echo ran-tests"})
    script = Script({"tool": "run", "args": {"command": "echo ran-tests"}}, {"tool": "finish", "args": {}})
    out = runner(project, script).run("run the tests")
    assert "ran-tests" in out["steps"][0]["observation"]


def test_runner_without_a_user_and_with_bad_replies(project):
    script = Script("I think we should do X.",
                    {"tool": "ask_user", "args": {"question": "Which DB?", "recommended": "SQLite"}},
                    {"tool": "nope", "args": {}},
                    {"tool": "skill", "args": {"name": "speky-test"}},
                    {"tool": "finish", "args": {"summary": "ok"}})
    out = runner(project, script).run("pick a database")
    obs = [s["observation"] for s in out["steps"]]
    assert "not one JSON tool call" in obs[0]
    assert "informed guess" in obs[1] and "assumption" in obs[1]
    assert "not one JSON tool call" in obs[2]
    assert "# Tests" in obs[3]


def test_runner_stops_at_max_steps(project):
    script = Script(*[{"tool": "list_files", "args": {}}] * 3)
    out = runner(project, script, max_steps=3).run("loop")
    assert not out["finished"] and len(out["steps"]) == 3


def test_run_without_a_model_explains_how_to_set_one(tmp_path, monkeypatch):
    import speky_llm
    from .conftest import cli
    (tmp_path / ".speky").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(speky_llm, "GLOBAL_CONFIG", tmp_path / "none.yaml")
    for var in ("SPEKY_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
                "OPENCODE_API_KEY", "NEBIUS_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(speky_llm.shutil, "which", lambda name: None)
    err = cli("run", "do something", expect=1)["error"]
    assert err["code"] == "no_model" and "speky config model" in err["fix"]


def test_runner_reports_usage_errors_and_help(project):
    script = Script(
        {"tool": "speky", "args": {"argv": ["evidence", "X", "R1", "--status", "met", "--note", "x"]}},
        {"tool": "speky", "args": {"argv": ["evidence", "--help"]}},
        {"tool": "finish", "args": {"summary": "ok"}},
    )
    out = runner(project, script).run("try")
    assert "unrecognized arguments: --note" in out["steps"][0]["observation"]
    assert "--evidence" in out["steps"][1]["observation"]
