"""Run the API and the hosted Angular build."""

from __future__ import annotations

import logging

from waitress import serve

from kiln_api.app import create_app
from kiln_api.settings import load_settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()
    logging.getLogger("kiln").info(
        "Kiln API on http://%s:%s (frontend dist %s)",
        settings.api_host,
        settings.api_port,
        settings.frontend_dist,
    )
    serve(create_app(settings), host=settings.api_host, port=settings.api_port, threads=8)


if __name__ == "__main__":
    main()
