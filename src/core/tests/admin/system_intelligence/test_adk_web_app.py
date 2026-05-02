import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.test import SimpleTestCase

from core.admin.system_intelligence.adk_web.app import _prepare_browser_assets


class SystemIntelligenceADKBrowserAssetsTests(SimpleTestCase):
    def test_prepare_browser_assets_writes_runtime_config_and_stamp(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fast_api_file = _make_fast_api_browser_source(temp_path / "adk", "original")
            runtime_dir = temp_path / "runtime"
            runtime_dir.mkdir()

            with mock.patch(
                "core.admin.system_intelligence.adk_web.app.package_version",
                return_value="1.31.1",
            ):
                browser_assets_dir = _prepare_browser_assets(runtime_dir, str(fast_api_file))

            self.assertEqual(browser_assets_dir, runtime_dir / "browser")
            self.assertEqual((browser_assets_dir / "asset.txt").read_text(encoding="utf-8"), "original")
            runtime_config = json.loads(
                (browser_assets_dir / "assets" / "config" / "runtime-config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(runtime_config["backendUrl"], "/admin/core/system-intelligence/adk")
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
                "core.admin.system_intelligence.adk_web.app.package_version",
                return_value="1.31.1",
            ):
                _prepare_browser_assets(runtime_dir, str(fast_api_file))

            with (
                mock.patch(
                    "core.admin.system_intelligence.adk_web.app.package_version",
                    return_value="1.31.1",
                ),
                mock.patch("core.admin.system_intelligence.adk_web.app.shutil.copytree") as copytree,
            ):
                browser_assets_dir = _prepare_browser_assets(runtime_dir, str(fast_api_file))

            self.assertEqual(browser_assets_dir, runtime_dir / "browser")
            copytree.assert_not_called()

    def test_prepare_browser_assets_recopies_when_stamp_changes(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fast_api_file = _make_fast_api_browser_source(temp_path / "adk", "original")
            runtime_dir = temp_path / "runtime"
            runtime_dir.mkdir()

            with mock.patch(
                "core.admin.system_intelligence.adk_web.app.package_version",
                return_value="1.31.1",
            ):
                _prepare_browser_assets(runtime_dir, str(fast_api_file))

            with (
                mock.patch(
                    "core.admin.system_intelligence.adk_web.app.package_version",
                    return_value="1.31.2",
                ),
                mock.patch(
                    "core.admin.system_intelligence.adk_web.app.shutil.copytree", wraps=shutil.copytree
                ) as copytree,
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
