"""The module-level ``load_dotenv()`` in app.py, run for real in a fresh interpreter.

app.py loads ``.env`` at import time, so each case copies app.py next to a temporary
``.env`` and imports it in a subprocess (re-importing in-process would replace the
Flask app and cache the other tests hold).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_PY = Path(__file__).resolve().parent.parent / "app.py"
PROBE = "import os, app; print(repr(os.environ.get('SHEETS_API_KEY')))"


def _key_seen_by_app(tmp_path: Path, dotenv_text: str, **env: str) -> str:
    shutil.copy(APP_PY, tmp_path / "app.py")
    (tmp_path / ".env").write_text(dotenv_text, encoding="utf-8")
    child_env = {k: v for k, v in os.environ.items() if k != "SHEETS_API_KEY"}
    child_env.update(env)
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=tmp_path,
        env=child_env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return result.stdout.strip()


def test_dotenv_next_to_app_supplies_the_key(tmp_path):
    # Local runs read the key from archive/page/.env (the file sits next to app.py).
    assert _key_seen_by_app(tmp_path, 'SHEETS_API_KEY="from-dotenv"\n') == "'from-dotenv'"


def test_process_environment_wins_over_dotenv(tmp_path):
    # ECS injects the key from Secrets Manager; a stray .env must never override it.
    seen = _key_seen_by_app(tmp_path, "SHEETS_API_KEY=from-dotenv\n", SHEETS_API_KEY="from-ecs")
    assert seen == "'from-ecs'"


def test_blank_key_with_inline_comment_counts_as_unset(tmp_path):
    # python-dotenv 1.2.4+: ``KEY= # note`` is an empty value, not the comment text, so
    # /readyz and the proxy report the key as missing instead of sending "# note" to Google.
    assert _key_seen_by_app(tmp_path, "SHEETS_API_KEY= # paste the key here\n") == "''"
