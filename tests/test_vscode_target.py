import json

from speky import IDEIntegration


def test_vscode_rules_never_touch_settings_json(tmp_path):
    settings = tmp_path / ".vscode" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"editor.tabSize": 2}))

    IDEIntegration(tmp_path, ide="vscode").update_context_file("Product context", target_ide="vscode")

    assert json.loads(settings.read_text()) == {"editor.tabSize": 2}
    instructions = tmp_path / ".github" / "copilot-instructions.md"
    assert "SPEKY" in instructions.read_text()
