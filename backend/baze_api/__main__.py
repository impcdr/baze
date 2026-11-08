"""Run the API and the hosted Angular build."""

from __future__ import annotations

import logging
import os
import threading

from waitress import serve

from baze_api.activity import clear_stale_turns
from baze_api.boxes import start_denial_watch
from baze_api.app import create_app
from baze_api.docker import DockerCli, bridge_gateway, open_proxy_from_bridge
from baze_api.limits import sweep_forever
from baze_api.product import resume_decided_plan
from baze_api.provisioner import ensure_managed, stop_idle_progress
from baze_api.proxy import start_proxy
from baze_api.runtime import RuntimeServices
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
    clear_stale_turns(settings)
    stop_idle_progress(settings)
    runner = DockerCli()
    ensure_managed(settings, runner)
    start_denial_watch(settings)
    threading.Thread(
        target=sweep_forever,
        args=(settings, runner),
        name="baze-expiry",
        daemon=True,
    ).start()
    services = RuntimeServices.production()
    resume_id = os.environ.get("BAZE_RESUME_APP", "").strip()
    if resume_id:
        threading.Thread(
            target=resume_decided_plan,
            args=(settings, services, resume_id),
            name="baze-resume",
            daemon=True,
        ).start()
    log.info(
        "API on http://%s:%s (frontend dist %s)",
        settings.api_host,
        settings.api_port,
        settings.frontend_dist,
    )
    serve(create_app(settings, services), host=settings.api_host, port=settings.api_port, threads=8)


if __name__ == "__main__":
    main()
