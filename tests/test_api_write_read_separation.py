"""Focused route tests for CASC/certificate read and write responsibilities."""

import copy
import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from backend.api import casc as casc_api
from backend.api import certificate as certificate_api


class FakeResult:
    def __init__(self, rows=None, scalar=None):
        self.rows = rows or []
        self.scalar = scalar

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def one(self):
        if not self.rows:
            raise AssertionError("Expected one row")
        return self.rows[0]

    def all(self):
        return self.rows

    def scalar_one(self):
        return self.scalar


class FakeDatabase:
    """Small transactional store sufficient to exercise the route handlers."""

    def __init__(self):
        self.state = {"runs": [], "scenarios": [], "certificates": []}
        self.inserts = {"runs": 0, "scenarios": 0, "certificates": 0}
        self.candidate = {"id": 7, "vessel_name": "TEST VESSEL"}

    def connect(self):
        return self._connection()

    @contextmanager
    def begin(self):
        before = copy.deepcopy(self.state)
        try:
            yield FakeConnection(self)
        except Exception:
            self.state = before
            raise

    @contextmanager
    def _connection(self):
        yield FakeConnection(self)


class FakeConnection:
    def __init__(self, database):
        self.database = database

    def execute(self, statement, params=None):
        query = " ".join(str(statement).lower().split())
        params = params or {}
        state = self.database.state

        if query.startswith("select id from incidents"):
            return FakeResult([{"id": params.get("incident_id", 1)}])

        if "from casc_runs cr" in query:
            if "analysis_signature" in query:
                rows = [r for r in state["runs"]
                        if r["incident_id"] == params["incident_id"]
                        and r["analysis_signature"] == params["analysis_signature"]]
            else:
                rows = [r for r in state["runs"] if r["incident_id"] == params["incident_id"]]
            for row in rows:
                distribution = row.get("winner_distribution")
                if isinstance(distribution, str):
                    row["winner_distribution"] = json.loads(distribution)
                scenarios = [s for s in state["scenarios"] if s["casc_run_id"] == row["id"]]
                valid = [s for s in scenarios if s.get("valid") and s.get("winner_candidate_id") is not None and s.get("winner_score") is not None]
                numbers = [s["scenario_number"] for s in scenarios]
                row.update({
                    "scenario_count": len(scenarios),
                    "valid_scenario_count": len(valid),
                    "distinct_scenario_numbers": len(set(numbers)),
                    "first_scenario_number": min(numbers) if numbers else None,
                    "last_scenario_number": max(numbers) if numbers else None,
                })
            rows.sort(key=lambda r: r["id"], reverse=True)
            return FakeResult(rows[:1])

        if query.startswith("select count(*) from casc_scenarios"):
            rows = [s for s in state["scenarios"] if s["casc_run_id"] == params["run_id"]]
            return FakeResult(scalar=len(rows))

        if query.startswith("select id from candidate_vessels where"):
            if params.get("vessel_name") == self.database.candidate["vessel_name"]:
                return FakeResult([{"id": self.database.candidate["id"]}])
            return FakeResult()

        if query.startswith("select id, vessel_name from candidate_vessels"):
            return FakeResult([self.database.candidate])

        if query.startswith("insert into casc_runs"):
            row = dict(params)
            row.update({
                "id": len(state["runs"]) + 1,
                "vessel_name": row["leading_vessel"],
            })
            state["runs"].append(row)
            self.database.inserts["runs"] += 1
            return FakeResult([row])

        if query.startswith("insert into casc_scenarios"):
            rows = params if isinstance(params, list) else [params]
            if any(row.get("scenario_number") is None for row in rows):
                raise ValueError("scenario_number violates NOT NULL")
            state["scenarios"].extend(dict(row) for row in rows)
            self.database.inserts["scenarios"] += len(rows)
            return FakeResult()

        if "from certificates c" in query:
            rows = []
            for cert in state["certificates"]:
                run = next((r for r in state["runs"] if r["id"] == cert["casc_run_id"]), None)
                if not run:
                    continue
                scenarios = [s for s in state["scenarios"] if s["casc_run_id"] == run["id"]]
                valid = [s for s in scenarios if s.get("valid") and s.get("winner_candidate_id") is not None and s.get("winner_score") is not None]
                numbers = [s["scenario_number"] for s in scenarios]
                rows.append({
                    "certificate_row_id": cert["id"],
                    "certificate_incident_id": cert["incident_id"],
                    "casc_run_id": cert["casc_run_id"],
                    "certificate_id": cert["certificate_id"],
                    "certificate_leading_vessel": cert["leading_vessel"],
                    "certificate_stability_status": cert["stability_status"],
                    "certificate_winner_probability": cert["winner_probability"],
                    "certificate_closest_alternate": cert.get("closest_alternate"),
                    "certificate_winner_flip_minutes": cert.get("winner_flip_minutes"),
                    "certificate_normalized_perturbation": cert.get("normalized_perturbation"),
                    "decision_summary": cert["decision_summary"],
                    "generated_at": cert.get("generated_at", "now"),
                    "run_id": run["id"],
                    "run_incident_id": run["incident_id"],
                    "run_leading_vessel": run["leading_vessel"],
                    "analysis_signature": run["analysis_signature"],
                    "winner_distribution": run["winner_distribution"],
                    "total_scenarios": run["total_scenarios"],
                    "run_winner_probability": run["winner_probability"],
                    "run_stability_status": run["stability_status"],
                    "scenario_count": len(scenarios),
                    "valid_scenario_count": len(valid),
                    "distinct_scenario_numbers": len(set(numbers)),
                    "first_scenario_number": min(numbers) if numbers else None,
                    "last_scenario_number": max(numbers) if numbers else None,
                })
            return FakeResult(rows)

        if query.startswith("select * from certificates"):
            rows = [c for c in state["certificates"] if c["casc_run_id"] == params["casc_run_id"]]
            rows.sort(key=lambda r: r["id"], reverse=True)
            return FakeResult(rows[:1])

        if query.startswith("insert into certificates"):
            row = dict(params)
            row["id"] = len(state["certificates"]) + 1
            row["generated_at"] = "now"
            state["certificates"].append(row)
            self.database.inserts["certificates"] += 1
            return FakeResult()

        raise AssertionError(f"Unexpected SQL in route test: {query}")


def sample_candidates(_incident_id):
    return {"candidates": [{
        "vessel_name": "TEST VESSEL",
        "combined_score": 0.9,
        "time_score": 0.9,
        "space_score": 0.9,
        "drift_score": 0.9,
        "ais_score": 0.9,
    }]}


def sample_analysis(candidates, scenarios=2, seed=143):
    name = candidates[0]["vessel_name"]
    return {
        "total_scenarios": 2,
        "scenarios": [
            {"scenario_number": 1, "winner_vessel": name, "winner_score": 0.91, "valid": True},
            {"scenario_number": 2, "winner_vessel": name, "winner_score": 0.89, "valid": True},
        ],
        "leading_vessel": name,
        "winner_probability": 1.0,
        "closest_alternate": None,
        "winner_flip_minutes": None,
        "normalized_perturbation": 1.0,
        "stability_status": "ROBUST",
        "winner_distribution": {name: 1.0},
    }


class WriteReadSeparationTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.patches = [
            patch.object(casc_api, "engine", self.database),
            patch.object(certificate_api, "engine", self.database),
            patch.object(casc_api, "get_candidates", side_effect=sample_candidates),
            patch.object(casc_api, "calculate_casc", side_effect=sample_analysis),
        ]
        for active_patch in self.patches:
            active_patch.start()

    def tearDown(self):
        for active_patch in reversed(self.patches):
            active_patch.stop()

    def test_route_methods_separate_reads_from_writes(self):
        casc_methods = {(r.path, method) for r in casc_api.router.routes for method in r.methods}
        cert_methods = {(r.path, method) for r in certificate_api.router.routes for method in r.methods}
        self.assertIn(("/casc/{incident_id}", "GET"), casc_methods)
        self.assertIn(("/casc/{incident_id}/run", "POST"), casc_methods)
        self.assertIn(("/certificates/{incident_id}", "GET"), cert_methods)
        self.assertIn(("/certificates/{incident_id}", "POST"), cert_methods)

    def test_casc_get_is_read_only_and_post_persists_idempotently(self):
        first = casc_api.run_casc(1)
        self.assertFalse(first["reused"])
        self.assertEqual(first["casc_runs"][0]["total_scenarios"], 2)
        self.assertEqual(self.database.inserts, {"runs": 1, "scenarios": 2, "certificates": 0})

        repeated = casc_api.run_casc(1)
        self.assertTrue(repeated["reused"])
        self.assertEqual(repeated["casc_runs"][0]["id"], first["casc_runs"][0]["id"])
        self.assertEqual(self.database.inserts["runs"], 1)
        self.assertEqual(self.database.inserts["scenarios"], 2)

        before = dict(self.database.inserts)
        retrieved = casc_api.get_casc(1)
        self.assertEqual(retrieved["casc_runs"][0]["id"], first["casc_runs"][0]["id"])
        self.assertEqual(self.database.inserts, before)

    def test_failed_run_rolls_back_run_and_scenarios(self):
        marked = sample_candidates(1)
        marked["candidates"][0]["test_signature_marker"] = "rollback"
        before = copy.deepcopy(self.database.state)
        bad_result = dict(sample_analysis(marked["candidates"]))
        bad_result["scenarios"] = [{
            "scenario_number": None,
            "winner_vessel": "TEST VESSEL",
            "winner_score": 0.5,
        }]
        bad_result["total_scenarios"] = 1
        with patch.object(casc_api, "get_candidates", return_value=marked), \
             patch.object(casc_api, "calculate_casc", return_value=bad_result):
            with self.assertRaises(ValueError):
                casc_api.run_casc(1)
        self.assertEqual(self.database.state, before)

    def test_certificate_post_persists_and_get_is_read_only(self):
        run = casc_api.run_casc(1)["casc_runs"][0]
        certificate = certificate_api.create_certificate(1)["certificates"][0]
        self.assertEqual(certificate["casc_run_id"], run["id"])
        self.assertEqual(self.database.inserts["certificates"], 1)

        before = dict(self.database.inserts)
        retrieved = certificate_api.get_certificate(1)["certificates"][0]
        self.assertEqual(retrieved["certificate_id"], certificate["certificate_id"])
        repeated = certificate_api.create_certificate(1)["certificates"][0]
        self.assertEqual(repeated["certificate_id"], certificate["certificate_id"])
        self.assertEqual(self.database.inserts, before)


if __name__ == "__main__":
    unittest.main()
