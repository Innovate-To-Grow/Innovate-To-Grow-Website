from i2g_admin.app import app
from typer.testing import CliRunner

runner = CliRunner()


def test_completion_show_bash_emits_script():
    result = runner.invoke(app, ["completion", "show", "bash"])
    assert result.exit_code == 0
    assert result.output.strip()
    assert "_I2G_ADMIN_COMPLETE" in result.output or "complete" in result.output


def test_completion_show_zsh_emits_script():
    result = runner.invoke(app, ["completion", "show", "zsh"])
    assert result.exit_code == 0
    assert result.output.strip()


def test_completion_show_fish_emits_script():
    result = runner.invoke(app, ["completion", "show", "fish"])
    assert result.exit_code == 0
    assert result.output.strip()


def test_completion_show_unsupported_shell_exits_nonzero():
    result = runner.invoke(app, ["completion", "show", "powershell"])
    assert result.exit_code == 1
    assert "Unsupported shell" in result.output
    assert "powershell" in result.output


def test_completion_show_garbage_shell_exits_nonzero():
    result = runner.invoke(app, ["completion", "show", "not-a-shell"])
    assert result.exit_code == 1
    assert "Unsupported shell" in result.output


def test_completion_group_help_points_at_install_completion():
    result = runner.invoke(app, ["completion", "--help"])
    assert result.exit_code == 0
    assert "--install-completion" in result.output
