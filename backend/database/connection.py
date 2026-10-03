import logging
import os
import traceback
from urllib.parse import quote, quote_plus

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from ..config import DATABASE_URL


database_url = make_url(DATABASE_URL)
if database_url.drivername in ("postgres", "postgresql"):
    database_url = database_url.set(drivername="postgresql+psycopg")


def safe_database_error(error):
    """Return a credential-free error category and message for diagnostics."""
    original = getattr(error, "orig", error)
    message = str(original).lower()
    error_type = type(original).__name__

    if "no module named" in message and "psycopg" in message:
        category, safe_message = "driver_missing", "PostgreSQL driver is unavailable."
    elif "password authentication failed" in message or "authentication failed" in message:
        category, safe_message = "authentication_failed", "Database authentication failed."
    elif "does not exist" in message and "database" in message:
        category, safe_message = "database_not_found", "The configured database does not exist."
    elif "ssl" in message or "tls" in message:
        category, safe_message = "ssl_error", "The database SSL connection failed."
    elif "permission denied" in message or "not authorized" in message:
        category, safe_message = "permission_denied", "The database user lacks required permissions."
    elif "does not exist" in message or "undefinedtable" in message:
        category, safe_message = "schema_error", "A required database table or schema object is missing."
    elif "resolve host" in message or "getaddrinfo failed" in message:
        category, safe_message = "host_resolution_failed", "The database host could not be resolved."
    elif "connection refused" in message or "could not connect" in message or "timeout" in message:
        category, safe_message = "connection_failed", "The database server could not be reached."
    else:
        category, safe_message = "database_error", "The database operation failed."

    return {"type": error_type, "category": category, "message": safe_message}


def log_database_error(error):
    """Log a local-development traceback after removing connection secrets."""
    if os.getenv("APP_ENV", "development").lower() not in {"development", "local"}:
        return

    details = safe_database_error(error)
    formatted = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    secrets = {database_url.password}
    if database_url.password:
        secrets.update({
            quote(database_url.password, safe=""),
            quote_plus(database_url.password, safe=""),
        })
    for secret in filter(None, secrets):
        formatted = formatted.replace(secret, "[REDACTED]")
    logging.getLogger(__name__).error(
        "Database check failed (%s, %s): %s\n%s",
        details["type"], details["category"], details["message"], formatted,
    )

engine = create_engine(
    database_url,
    pool_pre_ping=True
)
