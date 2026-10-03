from random import Random

CASC_UNCERTAINTY_SUMMARY = (
    "CASC varies multipliers on precomputed evidence scores only. It does not "
    "recompute AIS features or perturb wind, ocean currents, AIS trajectories, "
    "timestamps, source geometry, or spill geometry."
)


def robustness_interpretation(winner_distribution, leading_vessel, total_scenarios):
    candidate_count = len(winner_distribution or {})
    winner_share = float((winner_distribution or {}).get(leading_vessel, 0) or 0)
    wins = round(winner_share * total_scenarios)
    if candidate_count <= 1:
        return (
            f"Leading candidate unchanged in {wins:,} of {total_scenarios:,} "
            "evidence-score variations (±10%). One observed candidate was "
            "available; competitive stability against alternative observed "
            "vessels was not evaluated."
        )

    if winner_share >= 1:
        return (
            f"Leading candidate unchanged in {wins:,} of {total_scenarios:,} "
            f"evidence-score variations (±10%) across {candidate_count} observed candidates."
        )
    return (
        f"{leading_vessel or 'The leading candidate'} led in {wins:,} of "
        f"{total_scenarios:,} evidence-score variations (±10%) across "
        f"{candidate_count} observed candidates."
    )


def clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, value))


def calculate_casc(candidates, scenarios=5000, seed=143):
    """
    CASC - Counterfactual Attribution Stability Certificate

    Tests whether the leading vessel remains the winner
    under score-level uncertainty in:
      - time
      - space
      - drift
      - AIS evidence

    This model perturbs the precomputed evidence scores only. It does not
    recompute AIS features or perturb wind, current, drift inputs, source
    position, timestamps, or spill geometry.
    """

    if not candidates:
        return {
            "total_scenarios": 0,
            "scenarios": [],
            "winner_probability": 0.0,
            "closest_alternate": None,
            "winner_flip_minutes": None,
            "normalized_perturbation": 0.0,
            "stability_status": "ABSTAIN",
            "winner_distribution": {}
        }

    rng = Random(seed)

    # --------------------------------------------------
    # Baseline ranking
    # --------------------------------------------------

    baseline = sorted(
        candidates,
        key=lambda x: float(
            x.get("combined_score", 0.0)
        ),
        reverse=True
    )

    leader = baseline[0]

    leader_name = leader.get(
        "vessel_name",
        "UNKNOWN"
    )

    # --------------------------------------------------
    # Winner counters
    # --------------------------------------------------

    winner_counts = {
        candidate.get(
            "vessel_name",
            "UNKNOWN"
        ): 0
        for candidate in baseline
    }
    scenario_results = []

    # --------------------------------------------------
    # Monte Carlo uncertainty scenarios
    # --------------------------------------------------

    for scenario_index in range(scenarios):

        scenario_scores = []

        # Plausible uncertainty:
        # each evidence component can vary slightly.

        for candidate in baseline:

            time_value = float(
                candidate.get(
                    "time_score",
                    0.0
                )
            )

            space_value = float(
                candidate.get(
                    "space_score",
                    0.0
                )
            )

            drift_value = float(
                candidate.get(
                    "drift_score",
                    0.0
                )
            )

            ais_value = float(
                candidate.get(
                    "ais_score",
                    0.0
                )
            )

            # Random uncertainty ±10%
            time_factor = rng.uniform(
                0.90,
                1.10
            )

            space_factor = rng.uniform(
                0.90,
                1.10
            )

            drift_factor = rng.uniform(
                0.90,
                1.10
            )

            ais_factor = rng.uniform(
                0.90,
                1.10
            )

            uncertain_time = clamp(
                time_value * time_factor
            )

            uncertain_space = clamp(
                space_value * space_factor
            )

            uncertain_drift = clamp(
                drift_value * drift_factor
            )

            uncertain_ais = clamp(
                ais_value * ais_factor
            )

            # Same evidence weights used by ranking engine
            score = (
                0.25 * uncertain_time
                + 0.30 * uncertain_space
                + 0.25 * uncertain_drift
                + 0.20 * uncertain_ais
            )

            scenario_scores.append(
                {
                    "vessel_name": candidate.get(
                        "vessel_name",
                        "UNKNOWN"
                    ),
                    "score": score
                }
            )

        # Find scenario winner
        scenario_scores.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        scenario_winner = scenario_scores[0]
        winner = scenario_winner["vessel_name"]

        winner_counts[winner] += 1
        scenario_results.append({
            "scenario_number": scenario_index + 1,
            "winner_vessel": winner,
            "winner_score": round(scenario_winner["score"], 4),
            "valid": True,
        })

    # --------------------------------------------------
    # Winner distribution
    # --------------------------------------------------

    winner_distribution = {}

    for vessel, count in winner_counts.items():

        winner_distribution[vessel] = round(
            count / scenarios,
            4
        )

    leader_probability = winner_distribution.get(
        leader_name,
        0.0
    )

    # --------------------------------------------------
    # Closest alternate
    # --------------------------------------------------

    alternates = [
        candidate
        for candidate in baseline
        if candidate.get("vessel_name") != leader_name
    ]

    closest_alternate = None

    if alternates:
        closest_alternate = alternates[0].get(
            "vessel_name"
        )

    # --------------------------------------------------
    # Winner flip test
    # --------------------------------------------------

    winner_flip_minutes = None

    normalized_perturbation = 1.0

    if alternates:

        alternate = alternates[0]

        leader_score = float(
            leader.get(
                "combined_score",
                0.0
            )
        )

        alternate_score = float(
            alternate.get(
                "combined_score",
                0.0
            )
        )

        score_gap = leader_score - alternate_score

        # Express the score gap as a minute-equivalent operational indicator.
        # No time input is changed, searched, or recomputed here.

        if score_gap > 0:

            winner_flip_minutes = round(
                score_gap * 60.0,
                2
            )

            normalized_perturbation = clamp(
                score_gap
            )

        else:

            winner_flip_minutes = 0.0
            normalized_perturbation = 0.0

    # --------------------------------------------------
    # Stability classification
    # --------------------------------------------------

    if leader_probability >= 0.80:

        stability_status = "ROBUST"

    elif leader_probability >= 0.55:

        stability_status = "SENSITIVE"

    else:

        stability_status = "ABSTAIN"

    # --------------------------------------------------
    # Final CASC result
    # --------------------------------------------------

    return {
        "total_scenarios": scenarios,

        "scenarios": scenario_results,

        "winner_probability": round(
            leader_probability,
            4
        ),

        "leading_vessel": leader_name,

        "closest_alternate": closest_alternate,

        "winner_flip_minutes": winner_flip_minutes,

        "normalized_perturbation": round(
            normalized_perturbation,
            4
        ),

        "stability_status": stability_status,

        "winner_distribution": winner_distribution
    }
