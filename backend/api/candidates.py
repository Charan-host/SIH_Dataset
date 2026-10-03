from fastapi import APIRouter
from sqlalchemy import text

from ..database.connection import engine
from ..services.ranking_service import rank_candidates
from ..services.ais_service import haversine_distance


router = APIRouter(
    prefix="/candidates",
    tags=["Candidate Ranking"]
)


@router.get("/{incident_id}")
def get_candidates(incident_id: int):

    # --------------------------------------------------
    # Get latest drift information
    # --------------------------------------------------

    with engine.connect() as connection:

        drift_result = connection.execute(
            text("""
                SELECT *
                FROM drift_runs
                WHERE incident_id = :incident_id
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"incident_id": incident_id}
        )

        drift = drift_result.mappings().first()

    if not drift:
        return {
            "mode": "NO_DRIFT_DATA",
            "candidates": []
        }

    source_start = drift["start_time"]
    source_end = drift["end_time"]

    # --------------------------------------------------
    # Get source location from latest metocean observation
    # --------------------------------------------------

    with engine.connect() as connection:

        met_result = connection.execute(
            text("""
                SELECT latitude, longitude
                FROM metocean_observations
                WHERE incident_id = :incident_id
                ORDER BY observation_time DESC
                LIMIT 1
            """),
            {"incident_id": incident_id}
        )

        met = met_result.mappings().first()

    if not met:
        return {
            "mode": "NO_METOCEAN_DATA",
            "candidates": []
        }

    source_lat = float(met["latitude"])
    source_lon = float(met["longitude"])

    # Temporary operational source-region radius
    source_radius_km = 5.0

    # --------------------------------------------------
    # Get AIS positions
    # --------------------------------------------------

    with engine.connect() as connection:

        ais_result = connection.execute(
            text("""
                SELECT *
                FROM ais_positions
                WHERE incident_id = :incident_id
                ORDER BY position_time, id DESC
            """),
            {"incident_id": incident_id}
        )

        ais_rows = ais_result.mappings().all()

        fixture_rows = connection.execute(
            text("""
                SELECT mmsi, vessel_name, attribution_score
                FROM candidate_vessels
                WHERE incident_id = :incident_id
                ORDER BY id
            """),
            {"incident_id": incident_id}
        ).mappings().all()

    # These persisted seed scores are traceability metadata only. They are not
    # ranking inputs and are deliberately kept outside each candidate object,
    # so they cannot alter CASC inputs or its analysis signature.
    fixture_score_by_mmsi = {}
    for row in fixture_rows:
        fixture_score_by_mmsi.setdefault(
            str(row["mmsi"]),
            float(row["attribution_score"])
            if row["attribution_score"] is not None else None,
        )

    candidates = []

    # --------------------------------------------------
    # Convert AIS positions into candidate evidence
    # --------------------------------------------------

    for row in ais_rows:

        latitude = row.get("latitude")
        longitude = row.get("longitude")

        if latitude is None or longitude is None:
            continue

        latitude = float(latitude)
        longitude = float(longitude)

        distance_km = haversine_distance(
            source_lat,
            source_lon,
            latitude,
            longitude
        )

        timestamp = row.get("position_time")

        source_region_overlap = (
            distance_km <= source_radius_km
        )

        time_window_match = False

        if timestamp is not None:

            try:
                time_window_match = (
                    source_start
                    <= timestamp
                    <= source_end
                )
            except TypeError:
                time_window_match = False

        candidates.append({
            "vessel_name": row.get(
                "vessel_name",
                "UNKNOWN VESSEL"
            ),

            "mmsi": row.get("mmsi"),

            "timestamp": timestamp,

            "distance_km": distance_km,

            "closest_approach_km": distance_km,

            "source_region_overlap":
                source_region_overlap,

            "time_window_match":
                time_window_match
        })

    # --------------------------------------------------
    # Rank vessels
    # --------------------------------------------------

    ranked = rank_candidates(
        candidates=candidates,
        source_radius_km=source_radius_km,
        source_start=source_start,
        source_end=source_end
    )

    # --------------------------------------------------
    # Response
    # --------------------------------------------------

    return {
        "mode": "EVIDENCE_RANKING",

        "incident_id": incident_id,

        "source_region": {
            "latitude": source_lat,
            "longitude": source_lon,
            "radius_km": source_radius_km
        },

        "time_window": {
            "start": source_start,
            "end": source_end
        },

        "weights": {
            "time": 0.25,
            "space": 0.30,
            "drift": 0.25,
            "ais": 0.20
        },

        "score_semantics": {
            "field": "combined_score",
            "label": "Current combined evidence score",
            "formula": "0.25*time_score + 0.30*space_score + 0.25*drift_score + 0.20*ais_score",
            "component_notes": {
                "space_score": "Distance decay from the latest metocean location using a 5 km radius",
                "drift_score": "Reuses the same distance-decay calculation as space_score; it is not trajectory validation",
                "ais_score": "Computed from source-region overlap and drift-window match flags"
            },
            "duplicate_handling": "Best observation per MMSI; duplicate rows do not create additional vessel candidates",
            "runtime_ranking_field": "combined_score",
            "persisted_fixture_field": "candidate_vessels.attribution_score",
            "persisted_fixture_score_by_mmsi": fixture_score_by_mmsi,
            "ais_data_source_type": "SEEDED_DEMONSTRATION",
        },

        "candidate_count": len(ranked),

        "leading_vessel": (
            ranked[0]["vessel_name"]
            if ranked
            else None
        ),

        "candidates": ranked
    }
