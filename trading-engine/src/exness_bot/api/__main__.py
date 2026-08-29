"""CLI entry point for read-only API server."""

from __future__ import annotations

import uvicorn

from exness_bot.api.dependencies import get_cached_settings
from exness_bot.logging.setup import configure_logging


def main() -> None:
    settings = get_cached_settings()
    configure_logging(settings)
    uvicorn.run(
        "exness_bot.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
