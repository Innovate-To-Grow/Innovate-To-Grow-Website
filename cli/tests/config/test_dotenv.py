import os
from pathlib import Path

import i2g_admin
import pytest
from i2g_admin import config
from i2g_admin.config import dotenv

# Where i2g_admin/ was imported from: <checkout>/cli/src for a source checkout
# (editable install or PYTHONPATH=src), site-packages for a wheel install.
IMPORT_ROOT = Path(i2g_admin.__file__).resolve().parent.parent


def test_load_dotenv_populates_env(tmp_path, monkeypatch):
    monkeypatch.delenv("I2G_ADMIN_BASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('# comment\nI2G_ADMIN_BASE_URL="https://from-dotenv"\nBLANK\n')
    monkeypatch.setattr(dotenv, "_dotenv_paths", lambda: [env_file])
    config.load_dotenv()
    assert os.environ["I2G_ADMIN_BASE_URL"] == "https://from-dotenv"


def test_load_dotenv_ignores_non_cli_environment_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("I2G_ADMIN_BASE_URL", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "I2G_ADMIN_BASE_URL=https://safe.example.com\n"
        "HTTPS_PROXY=https://attacker.example.com\n"
        "XDG_CONFIG_HOME=./stolen-tokens\n"
    )
    monkeypatch.setattr(dotenv, "_dotenv_paths", lambda: [env_file])

    config.load_dotenv()

    assert os.environ["I2G_ADMIN_BASE_URL"] == "https://safe.example.com"
    assert "HTTPS_PROXY" not in os.environ
    assert "XDG_CONFIG_HOME" not in os.environ


def test_dotenv_paths_never_include_current_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert tmp_path / ".env" not in dotenv._dotenv_paths()


@pytest.mark.skipif(IMPORT_ROOT.name != "src", reason="i2g_admin is installed from a wheel, not a source checkout")
def test_package_root_is_the_cli_project_directory():
    # _package_root() counts parent directories of config/dotenv.py, so moving the
    # module silently retargets cli/.env (conftest sets the base URL, so no other
    # test would notice). Pin it to the cli/ directory that holds the imported src/.
    cli_root = IMPORT_ROOT.parent
    assert (cli_root / "pyproject.toml").is_file()
    assert dotenv._package_root() == cli_root
    assert dotenv._dotenv_paths() == [cli_root / ".env"]
