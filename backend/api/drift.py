from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from math import atan2, degrees, sqrt

from ..database.connection import engine
from ..services.drift_service import calculate_drift


router = APIRouter(
    prefix="/drift",
    tags=["Drift / Backtrack"]
)


MS_TO_KNOTS = 1.943844


def vector_to_speed_direction(u: float, v: float):
    """
    Convert U/V vector to speed (knots)
    and direction TO in degrees.
    """

    speed_ms = sqrt((u ** 2) + (v ** 2))
    speed_knots = speed_ms * MS_TO_KNOTS

    direction_to = (
        degrees(atan2(u, v)) + 360
    ) % 360

    return speed_knots, direction_to


def wind_from_direction(u: float, v: float):
    """
    Convert wind U/V vector to meteorological
    direction FROM.
    """

    _, direction_to = vector_to_speed_direction(u, v)

    return (direction_to + 180) % 360


@router.get("/{incident_id}")
def get_drift(incident_id: int):

    # =====================================================
    # 1. CHECK INCIDENT
    # =====================================================

    with engine.connect() as connection:

        incident_query = text("""
            SELECT id
            FROM incidents
            WHERE id = :incident_id
            LIMIT 1
        """)

        incident = connection.execute(
            incident_query,
            {"incident_id": incident_id}
        ).mappings().first()

        if not incident:
            raise HTTPException(
                status_code=404,
                detail="Incident not found"
            )

        # =================================================
        # 2. GET SPILL CHARACTERIZATION
        # =================================================

        spill_query = text("""
            SELECT *
            FROM spill_characteristics
            WHERE incident_id = :incident_id
            LIMIT 1
        """)

        spill = connection.execute(
            spill_query,
            {"incident_id": incident_id}
        ).mappings().first()

        if not spill:
            raise HTTPException(
                status_code=404,
                detail="Spill characteristics not found"
            )

        # =================================================
        # 3. GET SATELLITE OBSERVATION TIME
        # =================================================

        satellite_query = text("""
            SELECT
                satellite_name,
                sensor_name,
                observation_time
            FROM satellite_observations
            WHERE incident_id = :incident_id
            ORDER BY observation_time DESC
            LIMIT 1
        """)

        satellite = connection.execute(
            satellite_query,
            {"incident_id": incident_id}
        ).mappings().first()

        # =================================================
        # 4. GET METOCEAN DATA
        # =================================================

        metocean_query = text("""
            SELECT
                observation_time,
                latitude,
                longitude,
                wind_u,
                wind_v,
                current_u,
                current_v,
                source
            FROM metocean_observations
            WHERE incident_id = :incident_id
            ORDER BY observation_time DESC
            LIMIT 1
        """)

        metocean = connection.execute(
            metocean_query,
            {"incident_id": incident_id}
        ).mappings().first()

    if not metocean:
        raise HTTPException(
            status_code=404,
            detail="Metocean observation not found"
        )

    # =====================================================
    # 5. SPILL LOCATION
    # =====================================================
    #
    # spill_characteristics does not contain coordinates.
    # Therefore the metocean observation location is used
    # as the current spill-position proxy for this incident.
    #

    latitude = float(metocean["latitude"])
    longitude = float(metocean["longitude"])

    # Prefer satellite acquisition time.
    # Otherwise use metocean observation time.

    if satellite and satellite["observation_time"]:
        spill_time = satellite["observation_time"]
    else:
        spill_time = metocean["observation_time"]

    # =====================================================
    # 6. ACTUAL WIND / CURRENT VALUES
    # =====================================================

    wind_u = float(metocean["wind_u"] or 0)
    wind_v = float(metocean["wind_v"] or 0)

    current_u = float(metocean["current_u"] or 0)
    current_v = float(metocean["current_v"] or 0)

    # Convert m/s → knots

    wind_speed_knots, _ = vector_to_speed_direction(
        wind_u,
        wind_v
    )

    wind_from_deg = wind_from_direction(
        wind_u,
        wind_v
    )

    current_speed_knots, current_direction_deg = (
        vector_to_speed_direction(
            current_u,
            current_v
        )
    )

    # =====================================================
    # 7. RUN DRIFT + BACKTRACK
    # =====================================================

    result = calculate_drift(
        spill_lat=latitude,
        spill_lon=longitude,
        spill_time=spill_time,

        backtrack_hours=6,
        forecast_hours=12,

        wind_speed_knots=wind_speed_knots,
        wind_from_deg=wind_from_deg,

        current_speed_knots=current_speed_knots,
        current_direction_deg=current_direction_deg,

        wind_uncertainty=0.15,
        current_uncertainty=0.10
    )

    # =====================================================
    # 8. API RESPONSE
    # =====================================================

    return {
        "incident_id": incident_id,

        "mode": "CALCULATED",

        "spill_position": result["spill_position"],

        "spill_time": result["spill_time"],

        "backtrack": result["backtrack"],

        "source_region": result["source_region"],

        "forecast": result["forecast"],

        "inputs": {
            "satellite": {
                "satellite_name": (
                    satellite["satellite_name"]
                    if satellite
                    else None
                ),
                "sensor_name": (
                    satellite["sensor_name"]
                    if satellite
                    else None
                ),
                "observation_time": (
                    str(satellite["observation_time"])
                    if satellite
                    else None
                )
            },

            "spill_position": {
                "latitude": latitude,
                "longitude": longitude
            },

            "metocean": {
                "observation_time": str(
                    metocean["observation_time"]
                ),

                "latitude": float(
                    metocean["latitude"]
                ),

                "longitude": float(
                    metocean["longitude"]
                ),

                "wind_u_ms": wind_u,
                "wind_v_ms": wind_v,

                "current_u_ms": current_u,
                "current_v_ms": current_v,

                "wind_speed_knots": round(
                    wind_speed_knots,
                    3
                ),

                "wind_from_deg": round(
                    wind_from_deg,
                    2
                ),

                "current_speed_knots": round(
                    current_speed_knots,
                    3
                ),

                "current_direction_deg": round(
                    current_direction_deg,
                    2
                ),

                "source": metocean["source"]
            }
        }
    }