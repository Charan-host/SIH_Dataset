"""Run safe SQLAlchemy/PostgreSQL diagnostics: python -m backend.database.diagnostics"""

from sqlalchemy import text

from .connection import database_url, engine, log_database_error, safe_database_error


def run_diagnostics():
    print("Connection:", {
        "driver": database_url.drivername,
        "host": database_url.host,
        "port": database_url.port,
        "database": database_url.database,
        "username": database_url.username,
        "password_present": database_url.password is not None,
    })
    try:
        with engine.connect() as connection:
            print("SELECT 1 ->", connection.execute(text("SELECT 1")).scalar_one())
            print("PostgreSQL version ->", connection.execute(text("SELECT version()")).scalar_one())
            print("PostGIS version ->", connection.execute(text("SELECT PostGIS_Version()")).scalar_one())
            incidents_exists = connection.execute(
                text("SELECT to_regclass('public.incidents') IS NOT NULL")
            ).scalar_one()
            print("incidents table exists ->", incidents_exists)
            if incidents_exists:
                print("incidents count ->", connection.execute(
                    text("SELECT COUNT(*) FROM incidents")
                ).scalar_one())
    except Exception as error:
        log_database_error(error)
        print("Database diagnostic failed:", safe_database_error(error))
        raise SystemExit(1) from None


if __name__ == "__main__":
    run_diagnostics()
