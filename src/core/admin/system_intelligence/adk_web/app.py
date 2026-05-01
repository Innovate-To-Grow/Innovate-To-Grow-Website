import json
import mimetypes
import os
import shutil
from pathlib import Path

from django.conf import settings

from core.services.system_intelligence_adk.constants import AGENT_NAME, APP_NAME

from .auth import AdminADKWebAuthMiddleware
from .constants import (
    SYSTEM_INTELLIGENCE_ADK_LOGO_URL,
    SYSTEM_INTELLIGENCE_ADK_PREFIX,
    SYSTEM_INTELLIGENCE_ADK_RUNTIME_DIRNAME,
)
from .loader import SystemIntelligenceAgentLoader


def get_system_intelligence_adk_asgi_application():
    from fastapi.responses import PlainTextResponse, RedirectResponse, Response
    from fastapi.staticfiles import StaticFiles
    from google.adk.cli import fast_api as adk_fast_api
    from google.adk.cli.fast_api import get_fast_api_app

    runtime_dir = Path(settings.MEDIA_ROOT) / SYSTEM_INTELLIGENCE_ADK_RUNTIME_DIRNAME
    runtime_dir.mkdir(parents=True, exist_ok=True)
    browser_assets_dir = _prepare_browser_assets(runtime_dir, adk_fast_api.__file__)

    session_service_uri = os.environ.get("SYSTEM_INTELLIGENCE_ADK_SESSION_SERVICE_URI")
    artifact_service_uri = os.environ.get("SYSTEM_INTELLIGENCE_ADK_ARTIFACT_SERVICE_URI")
    app = get_fast_api_app(
        agents_dir=str(runtime_dir),
        agent_loader=SystemIntelligenceAgentLoader(),
        session_service_uri=session_service_uri,
        artifact_service_uri=artifact_service_uri,
        use_local_storage=True,
        web=False,
        url_prefix=SYSTEM_INTELLIGENCE_ADK_PREFIX,
        allow_origins=None,
        auto_create_session=False,
    )

    redirect_dev_ui_url = f"{SYSTEM_INTELLIGENCE_ADK_PREFIX}/dev-ui/"

    @app.get("/dev-ui/config")
    async def get_ui_config():
        return {
            "logo_text": "System Intelligence",
            "logo_image_url": SYSTEM_INTELLIGENCE_ADK_LOGO_URL,
        }

    @app.get("/dev/build_graph/{app_name}")
    async def get_build_graph(app_name: str):
        if app_name != APP_NAME:
            return Response(status_code=404)
        return {
            "name": app_name,
            "root_agent": {
                "name": AGENT_NAME,
                "description": "Administrative assistant for Innovate to Grow operational data.",
            },
        }

    @app.get("/dev/build_graph_image/{app_name}")
    async def get_build_graph_image(app_name: str):
        if app_name != APP_NAME:
            return Response(status_code=404)
        return Response(status_code=204)

    @app.get("/builder/app/{app_name}", response_class=PlainTextResponse)
    async def get_agent_builder(app_name: str):
        if app_name != APP_NAME:
            return Response(status_code=404)
        return ""

    @app.get("/")
    async def redirect_root_to_dev_ui():
        return RedirectResponse(redirect_dev_ui_url)

    @app.get("/dev-ui")
    async def redirect_dev_ui_add_slash():
        return RedirectResponse(redirect_dev_ui_url)

    mimetypes.add_type("application/javascript", ".js", True)
    mimetypes.add_type("text/javascript", ".js", True)
    app.mount(
        "/dev-ui/",
        StaticFiles(directory=browser_assets_dir, html=True, follow_symlink=True),
        name="adk-static",
    )
    return app


def get_protected_system_intelligence_adk_asgi_application():
    return AdminADKWebAuthMiddleware(get_system_intelligence_adk_asgi_application())


def _prepare_browser_assets(runtime_dir: Path, fast_api_file: str) -> Path:
    source_dir = Path(fast_api_file).resolve().parent / "browser"
    target_dir = runtime_dir / "browser"
    shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
    runtime_config_dir = target_dir / "assets" / "config"
    runtime_config_dir.mkdir(parents=True, exist_ok=True)
    with (runtime_config_dir / "runtime-config.json").open("w") as config_file:
        json.dump(
            {
                "backendUrl": SYSTEM_INTELLIGENCE_ADK_PREFIX,
                "logo": {
                    "text": "System Intelligence",
                    "imageUrl": SYSTEM_INTELLIGENCE_ADK_LOGO_URL,
                },
            },
            config_file,
            indent=2,
        )
    return target_dir
