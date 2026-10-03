"""Validation helpers for selecting complete persisted CASC records."""

import math

from sqlalchemy import text


def _signature_present(value):
    return isinstance(value, str) and bool(value.strip())


def _valid_distribution(value):
    if not isinstance(value, dict) or not value:
        return False
    try:
        shares = [float(share) for share in value.values()]
    except (TypeError, ValueError):
        return False
    return (
        all(math.isfinite(share) and 0 <= share <= 1 for share in shares)
        and math.isclose(sum(shares), 1.0, rel_tol=0, abs_tol=0.001)
    )


def classify_casc_run(row):
    """Return COMPLETE only when run metadata and its full scenario set agree."""
    if not _signature_present(row.get("analysis_signature")):
        return "LEGACY / INCOMPLETE"
    if not isinstance(row.get("leading_vessel"), str) or not row["leading_vessel"].strip():
        return "LEGACY / INCOMPLETE"
    distribution = row.get("winner_distribution")
    if not _valid_distribution(distribution):
        return "LEGACY / INCOMPLETE"
    if row.get("leading_vessel") not in distribution:
        return "LEGACY / INCOMPLETE"

    try:
        expected = int(row.get("total_scenarios"))
        winner_probability = float(row.get("winner_probability"))
    except (TypeError, ValueError):
        return "LEGACY / INCOMPLETE"
    if expected <= 0 or not math.isfinite(winner_probability) or not 0 <= winner_probability <= 1:
        return "LEGACY / INCOMPLETE"
    if row.get("stability_status") not in {"ROBUST", "SENSITIVE", "ABSTAIN"}:
        return "LEGACY / INCOMPLETE"

    if row.get("scenario_count") != expected:
        return "LEGACY / INCOMPLETE"
    if row.get("valid_scenario_count") != expected:
        return "LEGACY / INCOMPLETE"
    if row.get("distinct_scenario_numbers") != expected:
        return "LEGACY / INCOMPLETE"
    if row.get("first_scenario_number") != 1 or row.get("last_scenario_number") != expected:
        return "LEGACY / INCOMPLETE"
    return "COMPLETE"


def latest_complete_casc_run(connection, incident_id, analysis_signature=None):
    """Find the newest fully persisted run; incomplete historical rows are skipped."""
    rows = connection.execute(text("""
        SELECT cr.*,
               COALESCE(cr.leading_vessel, cv.vessel_name) AS vessel_name,
               COALESCE(sc.scenario_count, 0) AS scenario_count,
               COALESCE(sc.valid_scenario_count, 0) AS valid_scenario_count,
               COALESCE(sc.distinct_scenario_numbers, 0) AS distinct_scenario_numbers,
               sc.first_scenario_number,
               sc.last_scenario_number
        FROM casc_runs cr
        LEFT JOIN candidate_vessels cv ON cv.id = cr.candidate_id
        LEFT JOIN (
            SELECT casc_run_id,
                   COUNT(*) AS scenario_count,
                   COUNT(*) FILTER (
                       WHERE valid IS TRUE
                         AND winner_candidate_id IS NOT NULL
                         AND winner_score IS NOT NULL
                   ) AS valid_scenario_count,
                   COUNT(DISTINCT scenario_number) AS distinct_scenario_numbers,
                   MIN(scenario_number) AS first_scenario_number,
                   MAX(scenario_number) AS last_scenario_number
            FROM casc_scenarios
            GROUP BY casc_run_id
        ) sc ON sc.casc_run_id = cr.id
        WHERE cr.incident_id = :incident_id
        ORDER BY cr.created_at DESC, cr.id DESC
    """), {"incident_id": incident_id}).mappings().all()

    selected = None
    for result in rows:
        row = dict(result)
        classification = classify_casc_run(row)
        signature_matches = (
            analysis_signature is None
            or row.get("analysis_signature") == analysis_signature
        )
        if classification == "COMPLETE" and signature_matches and selected is None:
            row["record_classification"] = classification
            selected = row
    return selected


def classify_certificate(certificate, casc_run, incident_id):
    """A certificate is complete only when it faithfully records a complete run."""
    if classify_casc_run(casc_run) != "COMPLETE":
        return "LEGACY / INCOMPLETE"
    if certificate.get("incident_id") != incident_id or casc_run.get("incident_id") != incident_id:
        return "LEGACY / INCOMPLETE"
    if certificate.get("casc_run_id") != casc_run.get("id"):
        return "LEGACY / INCOMPLETE"
    if not isinstance(certificate.get("certificate_id"), str) or not certificate["certificate_id"].strip():
        return "LEGACY / INCOMPLETE"
    if certificate.get("leading_vessel") != casc_run.get("leading_vessel"):
        return "LEGACY / INCOMPLETE"
    if certificate.get("stability_status") != casc_run.get("stability_status"):
        return "LEGACY / INCOMPLETE"
    if not isinstance(certificate.get("decision_summary"), str) or not certificate["decision_summary"].strip():
        return "LEGACY / INCOMPLETE"
    if certificate.get("generated_at") is None:
        return "LEGACY / INCOMPLETE"
    try:
        probability = float(certificate.get("winner_probability"))
        run_probability = float(casc_run.get("winner_probability"))
    except (TypeError, ValueError):
        return "LEGACY / INCOMPLETE"
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        return "LEGACY / INCOMPLETE"
    if not math.isclose(probability, run_probability, rel_tol=0, abs_tol=0.0001):
        return "LEGACY / INCOMPLETE"
    return "COMPLETE"


def latest_complete_certificate(connection, casc_run, incident_id):
    """Classify historical certificates and return one for the selected run."""
    rows = connection.execute(text("""
        SELECT c.id AS certificate_row_id,
               c.incident_id AS certificate_incident_id,
               c.casc_run_id,
               c.certificate_id,
               c.leading_vessel AS certificate_leading_vessel,
               c.stability_status AS certificate_stability_status,
               c.winner_probability AS certificate_winner_probability,
               c.closest_alternate AS certificate_closest_alternate,
               c.winner_flip_minutes AS certificate_winner_flip_minutes,
               c.normalized_perturbation AS certificate_normalized_perturbation,
               c.decision_summary,
               c.generated_at,
               r.id AS run_id,
               r.incident_id AS run_incident_id,
               r.leading_vessel AS run_leading_vessel,
               r.analysis_signature,
               r.winner_distribution,
               r.total_scenarios,
               r.winner_probability AS run_winner_probability,
               r.stability_status AS run_stability_status,
               COALESCE(s.scenario_count, 0) AS scenario_count,
               COALESCE(s.valid_scenario_count, 0) AS valid_scenario_count,
               COALESCE(s.distinct_scenario_numbers, 0) AS distinct_scenario_numbers,
               s.first_scenario_number,
               s.last_scenario_number
        FROM certificates c
        JOIN casc_runs r ON r.id = c.casc_run_id
        LEFT JOIN (
            SELECT casc_run_id,
                   COUNT(*) AS scenario_count,
                   COUNT(*) FILTER (
                       WHERE valid IS TRUE
                         AND winner_candidate_id IS NOT NULL
                         AND winner_score IS NOT NULL
                   ) AS valid_scenario_count,
                   COUNT(DISTINCT scenario_number) AS distinct_scenario_numbers,
                   MIN(scenario_number) AS first_scenario_number,
                   MAX(scenario_number) AS last_scenario_number
            FROM casc_scenarios
            GROUP BY casc_run_id
        ) s ON s.casc_run_id = r.id
        WHERE c.incident_id = :incident_id
        ORDER BY c.generated_at DESC, c.id DESC
    """), {
        "incident_id": incident_id,
    }).mappings().all()
    selected = None
    for result in rows:
        result = dict(result)
        run = {
            "id": result["run_id"],
            "incident_id": result["run_incident_id"],
            "leading_vessel": result["run_leading_vessel"],
            "analysis_signature": result["analysis_signature"],
            "winner_distribution": result["winner_distribution"],
            "total_scenarios": result["total_scenarios"],
            "winner_probability": result["run_winner_probability"],
            "stability_status": result["run_stability_status"],
            "scenario_count": result["scenario_count"],
            "valid_scenario_count": result["valid_scenario_count"],
            "distinct_scenario_numbers": result["distinct_scenario_numbers"],
            "first_scenario_number": result["first_scenario_number"],
            "last_scenario_number": result["last_scenario_number"],
        }
        certificate = {
            "id": result["certificate_row_id"],
            "incident_id": result["certificate_incident_id"],
            "casc_run_id": result["casc_run_id"],
            "certificate_id": result["certificate_id"],
            "leading_vessel": result["certificate_leading_vessel"],
            "stability_status": result["certificate_stability_status"],
            "winner_probability": result["certificate_winner_probability"],
            "closest_alternate": result["certificate_closest_alternate"],
            "winner_flip_minutes": result["certificate_winner_flip_minutes"],
            "normalized_perturbation": result["certificate_normalized_perturbation"],
            "decision_summary": result["decision_summary"],
            "generated_at": result["generated_at"],
        }
        classification = classify_certificate(certificate, run, incident_id)
        if (
            classification == "COMPLETE"
            and run["id"] == casc_run["id"]
            and selected is None
        ):
            certificate["record_classification"] = classification
            selected = certificate
    return selected
