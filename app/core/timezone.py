from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings

APP_TZ = ZoneInfo(settings.APP_TIMEZONE)


def now() -> datetime:
    """Return current datetime in the configured app timezone (APP_TIMEZONE in .env)."""
    return datetime.now(APP_TZ)


def ensure_tz_aware(dt: datetime | None) -> datetime | None:
    """Ensure a datetime object is timezone-aware (uses APP_TZ if naive)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=APP_TZ)
    return dt

