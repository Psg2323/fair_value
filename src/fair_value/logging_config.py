import logging

from fair_value.settings import get_settings


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(log_level: str | None = None) -> None:
    """프로젝트 전체 로깅 형식을 설정합니다."""
    settings = get_settings()
    level = (log_level or settings.log_level).upper()

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        force=True,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)