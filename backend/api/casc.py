import json
from hashlib import sha256

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from ..database.connection import engine
from ..services.casc_service import (
    CASC_UNCERTAINTY_SUMMARY,
    calculate_casc,
    robustness_interpretation,
)
from ..services.persistence_validation import latest_complete_casc_run
from .candidates import get_candidates


router = APIRouter(prefix="/casc", tags=["CASC Analysis"])


def _run_payload(row):
    winner_distribution = row["winner_distribution"] or {}
    candidate_count = len(winner_distribution)
    return {
        "id": row["id"],
        "created_at": row.get("created_at"),
        "incident_id": row["incident_id"],
        "candidate_id": row["candidate_id"],
        "vessel_name": row["vessel_name"],
        "analysis_signature": row["analysis_signature"],
        "record_classification": row.get("record_classification", "COMPLETE"),
        "total_scenarios": row["total_scenarios"],
        "candidate_count": candidate_count,
        "winner_probability": float(row["winner_probability"] or 0),
        "closest_alternate": row["closest_alternate"],
        "winner_flip_minutes": (
            float(row["winner_flip_minutes"])
            if row["winner_flip_minutes"] is not None else None
        ),
        "winner_flip_interpretation": (
            "Score gap multiplied by 60; minute-equivalent indicator only, "
            "not a physical time shift or searched threshold."
        ),
        "normalized_perturbation": float(row["normalized_perturbation"] or 0),
        "stability_status": row["stability_status"],
        "robustness_interpretation": robustness_interpretation(
            winner_distribution, row["vessel_name"], row["total_scenarios"]
        ),
        "evidence_score_perturbation": True,
        "physical_input_perturbation": False,
        "ais_data_source_type": "SEEDED_DEMONSTRATION",
        # Normalize older persisted summaries that predate the explicit
        # limitation wording, so API clients never imply physical simulation.
        "uncertainty_summary": CASC_UNCERTAINTY_SUMMARY,
        "winner_distribution": winner_distribution,
    }


def _latest_run(connection, incident_id, analysis_signature=None):
    # Incomplete historical records are classified as LEGACY / INCOMPLETE by
    # the validator and are never considered for normal reads or reuse.
    return latest_complete_casc_run(
        connection, incident_id, analysis_signature=analysis_signature
    )


def _insert_scenarios(connection, run_id, incident_id, scenarios):
    candidate_rows = connection.execute(text("""
        SELECT id, vessel_name
        FROM candidate_vessels
        WHERE incident_id = :incident_id
    """), {"incident_id": incident_id}).mappings().all()
    candidate_ids = {row["vessel_name"]: row["id"] for row in candidate_rows}
    rows = [{
        "casc_run_id": run_id,
        "scenario_number": scenario["scenario_number"],
        # The current model perturbs evidence scores rather than physical
        # time/location/current/wind/AIS inputs, so those fields stay NULL.
        "winner_candidate_id": candidate_ids.get(scenario.get("winner_vessel")),
        "winner_score": scenario.get("winner_score"),
        "valid": scenario.get("valid", True),
    } for scenario in scenarios]
    if rows:
        connection.execute(text("""
            INSERT INTO casc_scenarios (
                casc_run_id, scenario_number, winner_candidate_id,
                winner_score, valid
            ) VALUES (
                :casc_run_id, :scenario_number, :winner_candidate_id,
                :winner_score, :valid
            )
        """), rows)


@router.get("/{incident_id}")
def get_casc(incident_id: int):
    """Return the latest persisted analysis without computing or writing."""
    with engine.connect() as connection:
        incident = connection.execute(text(
            "SELECT id FROM incidents WHERE id = :incident_id"
        ), {"incident_id": incident_id}).first()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        existing = _latest_run(connection, incident_id)

    if not existing:
        return {
            "incident_id": incident_id,
            "mode": "CASC_PERSISTED",
            "count": 0,
            "casc_runs": [],
        }
    return {
        "incident_id": incident_id,
        "mode": "CASC_PERSISTED",
        "count": 1,
        "casc_runs": [_run_payload(existing)],
    }


@router.post("/{incident_id}/run")
def run_casc(incident_id: int):
    """Compute CASC and atomically persist its run and scenario winners."""
    candidate_data = get_candidates(incident_id)
    candidates = candidate_data.get("candidates", [])
    if not candidates:
        return {
            "incident_id": incident_id,
            "mode": "CASC",
            "status": "ABSTAIN",
            "message": "No candidate vessels available",
            "casc_runs": [],
        }

    serialized_inputs = json.dumps(candidates, sort_keys=True, default=str)
    analysis_signature = sha256(serialized_inputs.encode("utf-8")).hexdigest()
    with engine.connect() as connection:
        existing = _latest_run(connection, incident_id, analysis_signature)
    if existing:
        return {
            "incident_id": incident_id,
            "mode": "CASC_PERSISTED",
            "reused": True,
            "count": 1,
            "casc_runs": [_run_payload(existing)],
        }

    result = calculate_casc(candidates=candidates, scenarios=5000, seed=143)
    leading_vessel = result.get("leading_vessel")
    uncertainty_summary = CASC_UNCERTAINTY_SUMMARY

    # Serialize first-run creation per incident. A retry that races with the
    # first request reads the committed result instead of inserting a duplicate.
    reused = False
    with engine.begin() as connection:
        incident = connection.execute(text(
            "SELECT id FROM incidents WHERE id = :incident_id FOR UPDATE"
        ), {"incident_id": incident_id}).first()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        existing = _latest_run(connection, incident_id, analysis_signature)
        reused = existing is not None
        if not existing:
            candidate = connection.execute(text("""
                SELECT id FROM candidate_vessels
                WHERE incident_id = :incident_id AND vessel_name = :vessel_name
                ORDER BY id DESC LIMIT 1
            """), {
                "incident_id": incident_id,
                "vessel_name": leading_vessel,
            }).mappings().first()
            inserted_run = connection.execute(text("""
                INSERT INTO casc_runs (
                    incident_id, candidate_id, leading_vessel, winner_distribution,
                    analysis_signature,
                    total_scenarios,
                    winner_probability, closest_alternate, winner_flip_minutes,
                    normalized_perturbation, stability_status, uncertainty_summary
                ) VALUES (
                    :incident_id, :candidate_id, :leading_vessel, CAST(:winner_distribution AS jsonb),
                    :analysis_signature,
                    :total_scenarios,
                    :winner_probability, :closest_alternate, :winner_flip_minutes,
                    :normalized_perturbation, :stability_status, :uncertainty_summary
                ) RETURNING id
            """), {
                "incident_id": incident_id,
                "candidate_id": candidate["id"] if candidate else None,
                "leading_vessel": leading_vessel,
                "winner_distribution": json.dumps(result.get("winner_distribution", {})),
                "analysis_signature": analysis_signature,
                "total_scenarios": result.get("total_scenarios", 5000),
                "winner_probability": result.get("winner_probability", 0.0),
                "closest_alternate": result.get("closest_alternate"),
                "winner_flip_minutes": result.get("winner_flip_minutes"),
                "normalized_perturbation": result.get("normalized_perturbation", 0.0),
                "stability_status": result.get("stability_status", "ABSTAIN"),
                "uncertainty_summary": uncertainty_summary,
            }).mappings().one()
            run_id = inserted_run["id"]
            _insert_scenarios(
                connection, run_id, incident_id, result.get("scenarios", [])
            )
            existing = _latest_run(connection, incident_id, analysis_signature)
        # If a complete matching run appeared while this request computed,
        # return it unchanged. Incomplete historical rows are preserved and
        # never repaired or reused as if they were complete.

    if not existing:
        raise HTTPException(status_code=500, detail="CASC result could not be persisted")
    return {
        "incident_id": incident_id,
        "mode": "CASC_PERSISTED",
        "reused": reused,
        "count": 1,
        "casc_runs": [_run_payload(existing)],
    }
