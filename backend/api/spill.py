import json
from math import cos, pi, sin

from fastapi import APIRouter
from sqlalchemy import text

from ..database.connection import engine


router = APIRouter(
    prefix="/spill",
    tags=["Spill Characterization"]
)


def estimated_footprint(latitude, longitude, length_km, width_km, orientation_deg=0):
    """Build a clearly identified approximate ellipse from reported dimensions."""
    latitude = float(latitude)
    longitude = float(longitude)
    semi_major = max(float(length_km or 0), 0.05) / 2
    semi_minor = max(float(width_km or 0), 0.05) / 2
    bearing = float(orientation_deg or 0) * pi / 180
    ring = []

    for step in range(65):
        angle = 2 * pi * step / 64
        wobble = 1 + 0.035 * sin(3 * angle + 0.4) + 0.018 * cos(5 * angle - 0.3)
        along = semi_major * (1 if cos(angle) >= 0 else -1) * abs(cos(angle)) ** 0.5 * wobble
        across = semi_minor * (1 if sin(angle) >= 0 else -1) * abs(sin(angle)) ** 0.5 * wobble
        east = along * sin(bearing) + across * cos(bearing)
        north = along * cos(bearing) - across * sin(bearing)
        lat = latitude + north / 111.32
        lon = longitude + east / (111.32 * max(abs(cos(latitude * pi / 180)), 0.01))
        ring.append([round(lon, 7), round(lat, 7)])

    return {"type": "Polygon", "coordinates": [ring]}


@router.get("/{incident_id}")
def get_spill_characterization(incident_id: int):
    with engine.connect() as connection:
        characteristic = connection.execute(
            text("""
                SELECT *
                FROM spill_characteristics
                WHERE incident_id = :incident_id
                ORDER BY created_at DESC, id DESC
                LIMIT 1
            """),
            {"incident_id": incident_id}
        ).mappings().first()

        detection = connection.execute(
            text("""
                SELECT
                    ST_AsGeoJSON(spill_polygon) AS spill_geojson,
                    ST_Y(centroid) AS centroid_lat,
                    ST_X(centroid) AS centroid_lon
                FROM spill_detections
                WHERE incident_id = :incident_id
                  AND (spill_polygon IS NOT NULL OR centroid IS NOT NULL)
                ORDER BY detection_time DESC NULLS LAST, id DESC
                LIMIT 1
            """),
            {"incident_id": incident_id}
        ).mappings().first()

        metocean = connection.execute(
            text("""
                SELECT latitude, longitude
                FROM metocean_observations
                WHERE incident_id = :incident_id
                  AND latitude IS NOT NULL
                  AND longitude IS NOT NULL
                ORDER BY observation_time DESC NULLS LAST, id DESC
                LIMIT 1
            """),
            {"incident_id": incident_id}
        ).mappings().first()

    result = dict(characteristic) if characteristic else {}
    geometry = None
    geometry_source = "UNAVAILABLE"

    if detection and detection.get("spill_geojson"):
        geometry = json.loads(detection["spill_geojson"])
        geometry_source = "DETECTED"

    center_lat = (
        detection.get("centroid_lat") if detection else None
    )
    center_lon = (
        detection.get("centroid_lon") if detection else None
    )
    if (center_lat is None or center_lon is None) and metocean:
        center_lat = metocean["latitude"]
        center_lon = metocean["longitude"]

    length_km = float(characteristic.get("length_km") or 0) if characteristic else 0
    width_km = float(characteristic.get("width_km") or 0) if characteristic else 0
    if (geometry is None and characteristic and center_lat is not None and center_lon is not None
            and length_km > 0 and width_km > 0):
        orientation = characteristic.get("orientation_deg") or 0
        geometry = estimated_footprint(
            center_lat,
            center_lon,
            characteristic.get("length_km"),
            characteristic.get("width_km"),
            orientation,
        )
        geometry_source = "ESTIMATED_FROM_DIMENSIONS"

    result.update({
        "geometry": geometry,
        "geometry_source": geometry_source,
        "geometry_note": (
            "Approximate rounded slick footprint derived from reported dimensions around the metocean location, oriented north-south because no measured outline or orientation is available; it is not a measured SAR boundary."
            if geometry_source == "ESTIMATED_FROM_DIMENSIONS"
            else None
        ),
        "centroid_lat": float(center_lat) if center_lat is not None else None,
        "centroid_lon": float(center_lon) if center_lon is not None else None,
    })

    has_spill_data = bool(characteristic or geometry)
    return {
        "incident_id": incident_id,
        "count": 1 if has_spill_data else 0,
        "characteristics": [result] if has_spill_data else [],
    }
