import json

from fastapi import APIRouter
from sqlalchemy import text

from ..database.connection import engine


router = APIRouter(
    prefix="/detection",
    tags=["Detection"]
)


@router.get("/{incident_id}")
def get_detection(incident_id: int):
    with engine.connect() as connection:
        result = connection.execute(
            text("""
                SELECT
                    id,
                    incident_id,
                    detection_time,
                    confidence,
                    spill_mask_path,
                    ST_AsGeoJSON(spill_polygon) AS spill_polygon_geojson,
                    ST_Y(centroid) AS centroid_lat,
                    ST_X(centroid) AS centroid_lon,
                    created_at
                FROM spill_detections
                WHERE incident_id = :incident_id
                ORDER BY detection_time DESC
            """),
            {"incident_id": incident_id}
        )

        detections = []
        for row in result.mappings():
            detection = dict(row)
            geometry = detection.pop("spill_polygon_geojson", None)
            detection["spill_polygon"] = json.loads(geometry) if geometry else None
            detections.append(detection)

    return {
        "incident_id": incident_id,
        "count": len(detections),
        "detections": detections
    }
