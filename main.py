"""Main entry point for WABotII application."""

import uvicorn

from src.wabotii.config.settings import get_settings


def main():
    """Run the application."""
    settings = get_settings()
    uvicorn.run(
        "src.wabotii.__main__:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.dev_mode,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
