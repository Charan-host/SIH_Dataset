from fastapi import APIRouter
from sqlalchemy import text

from ..database.connection import engine

router = APIRouter(
    prefix="/vessels",
    tags=["Vessel Correlation"]
)


@router.get("/{incident_id}")
def get_vessels(incident_id: int):

    with engine.connect() as connection:
        result = connection.execute(
            text("""
                SELECT *
                FROM ais_positions
                WHERE incident_id = :incident_id
                ORDER BY position_time DESC
            """),
            {"incident_id": incident_id}
        )

        vessels = [
            dict(row._mapping)
            for row in result
        ]

    return {
        "incident_id": incident_id,
        "count": len(vessels),
        "vessels": vessels
    }