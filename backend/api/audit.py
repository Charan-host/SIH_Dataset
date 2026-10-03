from fastapi import APIRouter
from sqlalchemy import text

from ..database.connection import engine

router = APIRouter(
    prefix="/audit",
    tags=["Audit History"]
)


@router.get("/{incident_id}")
def get_audit_history(incident_id: int):
    with engine.connect() as connection:
        result = connection.execute(
            text("""
                SELECT *
                FROM audit_events
                WHERE incident_id = :incident_id
                ORDER BY id DESC
            """),
            {"incident_id": incident_id}
        )

        events = [
            dict(row._mapping)
            for row in result
        ]

    return {
        "incident_id": incident_id,
        "count": len(events),
        "events": events
    }
