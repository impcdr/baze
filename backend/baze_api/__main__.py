"""Run the API and the hosted Angular build."""

from __future__ import annotations

import logging

from waitress import serve

from baze_api.app import create_app
from baze_api.docker import DockerCli, bridge_gateway, open_proxy_from_bridge
from baze_api.provisioner import ensure_managed
from baze_api.proxy import start_proxy
from baze_api.settings import load_settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()
    log = logging.getLogger("baze")
    if start_proxy(settings) is not None:
        try:
            open_proxy_from_bridge(settings.hermes_image, bridge_gateway(), settings.proxy_port)
        except Exception:
            log.exception("app containers cannot reach the inference proxy")
    ensure_managed(settings, DockerCli())
    log.info(
        "API on http://%s:%s (frontend dist %s)",
        settings.api_host,
        settings.api_port,
        settings.frontend_dist,
    )
    serve(create_app(settings), host=settings.api_host, port=settings.api_port, threads=8)


if __name__ == "__main__":
    main()
