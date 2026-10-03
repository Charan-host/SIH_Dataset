from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from ..database.connection import engine
from ..services.casc_service import (
    CASC_UNCERTAINTY_SUMMARY,
    robustness_interpretation,
)
from ..services.persistence_validation import (
    latest_complete_casc_run,
    latest_complete_certificate,
)


router = APIRouter(prefix="/certificates", tags=["Stability Certificates"])


def _certificate_payload(row, casc):
    probability = row["winner_probability"]
    winner_distribution = casc["winner_distribution"] or {}
    total_scenarios = casc["total_scenarios"]
    return {
        "certificate_id": row["certificate_id"],
        "generated_at": row.get("generated_at"),
        "record_classification": row.get("record_classification", "COMPLETE"),
        "incident_id": row["incident_id"],
        "casc_run_id": row["casc_run_id"],
        "analysis_signature": casc["analysis_signature"],
        "total_scenarios": total_scenarios,
        "candidate_count": len(winner_distribution),
        "ais_data_source_type": "SEEDED_DEMONSTRATION",
        "leading_vessel": row["leading_vessel"] or "UNKNOWN",
        "initial_correlation": None,
        "casc_stability": round(float(probability or 0) * 100, 2),
        "closest_alternate": row["closest_alternate"],
        "winner_flip_minutes": (
            float(row["winner_flip_minutes"])
            if row["winner_flip_minutes"] is not None else None
        ),
        "winner_flip_interpretation": (
            "Score gap multiplied by 60; minute-equivalent indicator only, "
            "not a physical time shift or searched threshold."
        ),
        "normalized_perturbation": (
            float(row["normalized_perturbation"] or 0)
        ),
        "status": row["stability_status"],
        "robustness_interpretation": robustness_interpretation(
            winner_distribution,
            casc["leading_vessel"] or casc["vessel_name"],
            total_scenarios,
        ),
        "evidence_score_perturbation": True,
        "physical_input_perturbation": False,
        "decision_summary": row["decision_summary"],
        "uncertainty_summary": CASC_UNCERTAINTY_SUMMARY,
    }


def _latest_run(connection, incident_id):
    return latest_complete_casc_run(connection, incident_id)


def _certificate_for_run(connection, casc, incident_id):
    return latest_complete_certificate(connection, casc, incident_id)


@router.get("/{incident_id}")
def get_certificate(incident_id: int):
    """Return the certificate for the latest persisted run; never writes."""
    with engine.connect() as connection:
        incident = connection.execute(text(
            "SELECT id FROM incidents WHERE id = :incident_id"
        ), {"incident_id": incident_id}).first()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        casc = _latest_run(connection, incident_id)
        if not casc:
            return {"incident_id": incident_id, "count": 0, "certificates": []}
        existing = _certificate_for_run(connection, casc, incident_id)
    if not existing:
        return {"incident_id": incident_id, "count": 0, "certificates": []}
    return {
        "incident_id": incident_id,
        "count": 1,
        "mode": "CERTIFICATE_PERSISTED",
        "certificates": [_certificate_payload(existing, casc)],
    }


@router.post("/{incident_id}")
def create_certificate(incident_id: int):
    """Persist a certificate for an existing CASC run, reusing it on retries."""
    with engine.connect() as connection:
        incident = connection.execute(text(
            "SELECT id FROM incidents WHERE id = :incident_id"
        ), {"incident_id": incident_id}).first()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        casc = _latest_run(connection, incident_id)
        if not casc:
            raise HTTPException(status_code=409, detail="No persisted CASC result exists")
        existing = _certificate_for_run(connection, casc, incident_id)
    if existing:
        return {
            "incident_id": incident_id,
            "count": 1,
            "mode": "CERTIFICATE_PERSISTED",
            "certificates": [_certificate_payload(existing, casc)],
        }

    decision_summary = (
        "Leading vessel is a source hypothesis based on satellite, drift and AIS "
        "evidence. This certificate does not establish definitive responsibility."
    )
    with engine.begin() as connection:
        incident = connection.execute(text(
            "SELECT id FROM incidents WHERE id = :incident_id FOR UPDATE"
        ), {"incident_id": incident_id}).first()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        casc = _latest_run(connection, incident_id)
        if not casc:
            raise HTTPException(status_code=409, detail="No persisted CASC result exists")
        casc_run_id = casc["id"]
        existing = _certificate_for_run(connection, casc, incident_id)
        if not existing:
            certificate_id = f"CASC-CERT-{incident_id:04d}-{casc_run_id}"
            connection.execute(text("""
                INSERT INTO certificates (
                    incident_id, casc_run_id, certificate_id, leading_vessel,
                    stability_status, winner_probability, closest_alternate,
                    winner_flip_minutes, normalized_perturbation, decision_summary
                ) VALUES (
                    :incident_id, :casc_run_id, :certificate_id, :leading_vessel,
                    :stability_status, :winner_probability, :closest_alternate,
                    :winner_flip_minutes, :normalized_perturbation, :decision_summary
                )
            """), {
                "incident_id": incident_id,
                "casc_run_id": casc_run_id,
                "certificate_id": certificate_id,
                "leading_vessel": casc.get("vessel_name"),
                "stability_status": casc.get("stability_status", "ABSTAIN"),
                "winner_probability": casc.get("winner_probability", 0.0),
                "closest_alternate": casc.get("closest_alternate"),
                "winner_flip_minutes": casc.get("winner_flip_minutes"),
                "normalized_perturbation": casc.get("normalized_perturbation", 0.0),
                "decision_summary": decision_summary,
            })
            existing = _certificate_for_run(connection, casc, incident_id)

    if not existing:
        raise HTTPException(status_code=500, detail="Certificate could not be persisted")
    return {
        "incident_id": incident_id,
        "count": 1,
        "mode": "CERTIFICATE_PERSISTED",
        "certificates": [_certificate_payload(existing, casc)],
    }
