import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.test import SimpleTestCase, override_settings

from system_intelligence.admin.adk_web.app import (
    _adk_allow_origins,
    _get_runtime_dir,
    _prepare_browser_assets,
    get_system_intelligence_adk_asgi_application,
)


class SystemIntelligenceADKBrowserAssetsTests(SimpleTestCase):
    def test_runtime_dir_uses_app_data_not_media_root(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir) / "app"
            media_root = base_dir / "media"

            with override_settings(BASE_DIR=base_dir, MEDIA_ROOT=media_root):
                runtime_dir = _get_runtime_dir()

            self.assertEqual(runtime_dir, base_dir / "data" / "system-intelligence-adk")
            self.assertNotIn("media", runtime_dir.parts)

    def test_fast_api_app_uses_explicit_same_origin_adk_config(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fast_api_file = _make_fast_api_browser_source(temp_path / "adk", "original")
            base_dir = temp_path / "app"
            fake_app = _FakeFastAPIApp()

            with (
                override_settings(BASE_DIR=base_dir, MEDIA_ROOT=base_dir / "media"),
                mock.patch("google.adk.cli.fast_api.__file__", str(fast_api_file)),
                mock.patch("google.adk.cli.fast_api.get_fast_api_app", return_value=fake_app) as get_fast_api_app,
            ):
                app = get_system_intelligence_adk_asgi_application()

            self.assertIs(app, fake_app)
            self.assertEqual(get_fast_api_app.call_args.kwargs["allow_origins"], _adk_allow_origins())
            self.assertEqual(
                get_fast_api_app.call_args.kwargs["agents_dir"], str(base_dir / "data" / "system-intelligence-adk")
            )

    def test_prepare_browser_assets_writes_runtime_config_and_stamp(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fast_api_file = _make_fast_api_browser_source(temp_path / "adk", "original")
            runtime_dir = temp_path / "runtime"
            runtime_dir.mkdir()

            with mock.patch(
                "system_intelligence.admin.adk_web.app.package_version",
                return_value="1.31.1",
            ):
                browser_assets_dir = _prepare_browser_assets(runtime_dir, str(fast_api_file))

            self.assertEqual(browser_assets_dir, runtime_dir / "browser")
            self.assertEqual((browser_assets_dir / "asset.txt").read_text(encoding="utf-8"), "original")
            runtime_config = json.loads(
                (browser_assets_dir / "assets" / "config" / "runtime-config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(runtime_config["backendUrl"], "/admin/system-intelligence/adk")
            self.assertEqual(runtime_config["logo"]["text"], "System Intelligence")
            stamp = json.loads((browser_assets_dir / ".browser-assets.stamp.json").read_text(encoding="utf-8"))
            self.assertEqual(stamp["adk_version"], "1.31.1")
            self.assertEqual(stamp["runtime_config"], runtime_config)
            self.assertEqual(stamp["source_dir"], str(fast_api_file.resolve().parent / "browser"))

    def test_prepare_browser_assets_skips_copy_when_stamp_matches(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fast_api_file = _make_fast_api_browser_source(temp_path / "adk", "original")
            runtime_dir = temp_path / "runtime"
            runtime_dir.mkdir()

            with mock.patch(
                "system_intelligence.admin.adk_web.app.package_version",
                return_value="1.31.1",
            ):
                _prepare_browser_assets(runtime_dir, str(fast_api_file))

            with (
                mock.patch(
                    "system_intelligence.admin.adk_web.app.package_version",
                    return_value="1.31.1",
                ),
                mock.patch("system_intelligence.admin.adk_web.app.shutil.copytree") as copytree,
            ):
                browser_assets_dir = _prepare_browser_assets(runtime_dir, str(fast_api_file))

            self.assertEqual(browser_assets_dir, runtime_dir / "browser")
            copytree.assert_not_called()

    def test_prepare_browser_assets_copies_while_holding_runtime_lock(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fast_api_file = _make_fast_api_browser_source(temp_path / "adk", "original")
            runtime_dir = temp_path / "runtime"
            lock_active = False
            lock_events = []

            @contextmanager
            def fake_lock(lock_runtime_dir):
                nonlocal lock_active
                lock_events.append(("enter", lock_runtime_dir))
                lock_active = True
                try:
                    yield
                finally:
                    lock_active = False
                    lock_events.append(("exit", lock_runtime_dir))

            def fake_copytree(_source_dir, target_dir, **_kwargs):
                self.assertTrue(lock_active)
                Path(target_dir).mkdir(parents=True, exist_ok=True)

            with (
                mock.patch(
                    "system_intelligence.admin.adk_web.app.package_version",
                    return_value="1.31.1",
                ),
                mock.patch("system_intelligence.admin.adk_web.app._browser_assets_lock", side_effect=fake_lock),
                mock.patch("system_intelligence.admin.adk_web.app.shutil.copytree", side_effect=fake_copytree),
            ):
                _prepare_browser_assets(runtime_dir, str(fast_api_file))

            self.assertEqual(lock_events, [("enter", runtime_dir), ("exit", runtime_dir)])

    def test_prepare_browser_assets_recopies_when_stamp_changes(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fast_api_file = _make_fast_api_browser_source(temp_path / "adk", "original")
            runtime_dir = temp_path / "runtime"
            runtime_dir.mkdir()

            with mock.patch(
                "system_intelligence.admin.adk_web.app.package_version",
                return_value="1.31.1",
            ):
                _prepare_browser_assets(runtime_dir, str(fast_api_file))

            with (
                mock.patch(
                    "system_intelligence.admin.adk_web.app.package_version",
                    return_value="1.31.2",
                ),
                mock.patch("system_intelligence.admin.adk_web.app.shutil.copytree", wraps=shutil.copytree) as copytree,
            ):
                _prepare_browser_assets(runtime_dir, str(fast_api_file))

            copytree.assert_called_once()
            stamp = json.loads(((runtime_dir / "browser") / ".browser-assets.stamp.json").read_text(encoding="utf-8"))
            self.assertEqual(stamp["adk_version"], "1.31.2")


def _make_fast_api_browser_source(root: Path, asset_text: str) -> Path:
    browser_dir = root / "browser"
    browser_dir.mkdir(parents=True)
    (browser_dir / "asset.txt").write_text(asset_text, encoding="utf-8")
    fast_api_file = root / "fast_api.py"
    fast_api_file.write_text("# fake ADK FastAPI module\n", encoding="utf-8")
    return fast_api_file


class _FakeFastAPIApp:
    def get(self, *_args, **_kwargs):
        def decorator(function):
            return function

        return decorator

    def mount(self, *_args, **_kwargs):
        return None
