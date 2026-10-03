from datetime import datetime
from math import exp


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0):
    return max(minimum, min(maximum, value))


def parse_datetime(value):
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
        except ValueError:
            return None

    return None


def make_timezone_compatible(vessel_time, source_start, source_end):
    if vessel_time is None:
        return vessel_time, source_start, source_end

    if source_start is None or source_end is None:
        return vessel_time, source_start, source_end

    # Make naive/aware datetime values compatible
    if vessel_time.tzinfo and source_start.tzinfo is None:
        source_start = source_start.replace(
            tzinfo=vessel_time.tzinfo
        )
        source_end = source_end.replace(
            tzinfo=vessel_time.tzinfo
        )

    elif vessel_time.tzinfo is None and source_start.tzinfo:
        vessel_time = vessel_time.replace(
            tzinfo=source_start.tzinfo
        )

    return vessel_time, source_start, source_end


def time_score(
    vessel_time,
    source_start,
    source_end
):
    """
    Score vessel based on AIS observation time.
    """

    vessel_time = parse_datetime(vessel_time)
    source_start = parse_datetime(source_start)
    source_end = parse_datetime(source_end)

    if vessel_time is None:
        return 0.0

    if source_start is None or source_end is None:
        return 0.0

    vessel_time, source_start, source_end = (
        make_timezone_compatible(
            vessel_time,
            source_start,
            source_end
        )
    )

    # Inside reconstructed source window
    if source_start <= vessel_time <= source_end:
        return 1.0

    # Outside window → gradually reduce
    if vessel_time < source_start:
        difference_minutes = (
            source_start - vessel_time
        ).total_seconds() / 60.0
    else:
        difference_minutes = (
            vessel_time - source_end
        ).total_seconds() / 60.0

    return clamp(
        exp(-difference_minutes / 60.0)
    )


def space_score(
    distance_km: float,
    source_radius_km: float
):
    """
    Score based on distance from reconstructed source.
    """

    if distance_km is None:
        return 0.0

    if source_radius_km <= 0:
        return 0.0

    if distance_km <= source_radius_km:
        return 1.0

    return clamp(
        exp(
            -(distance_km - source_radius_km)
            / source_radius_km
        )
    )


def drift_score(
    distance_km: float,
    source_radius_km: float
):
    """
    Current distance-based proxy. This is not independent drift-trajectory
    validation; the runtime calculation currently matches space_score.
    """

    return space_score(
        distance_km,
        source_radius_km
    )


def ais_score(
    source_region_overlap: bool,
    time_window_match: bool
):
    """
    AIS consistency score.
    """

    if source_region_overlap and time_window_match:
        return 1.0

    if source_region_overlap:
        return 0.7

    if time_window_match:
        return 0.4

    return 0.0


def calculate_combined_score(
    time: float,
    space: float,
    drift: float,
    ais: float
):
    """
    Weighted evidence combination.

    Time  = 25%
    Space = 30%
    Drift = 25%
    AIS   = 20%
    """

    score = (
        0.25 * time
        + 0.30 * space
        + 0.25 * drift
        + 0.20 * ais
    )

    return clamp(score)


def rank_candidates(
    candidates,
    source_radius_km: float,
    source_start,
    source_end
):
    """
    Rank vessels using Time + Space + Drift + AIS evidence.

    Rows are grouped by MMSI and scored individually. Only the strongest
    single observation contributes to one ranked vessel candidate; repeated
    rows never count as independent vessels or add their scores together.
    """

    # --------------------------------------------------
    # GROUP AIS POSITIONS BY MMSI
    # --------------------------------------------------

    vessel_groups = {}

    for candidate in candidates:

        mmsi = candidate.get("mmsi")

        if mmsi is None:
            continue

        mmsi = str(mmsi)

        if mmsi not in vessel_groups:
            vessel_groups[mmsi] = []

        vessel_groups[mmsi].append(candidate)

    ranked = []

    # --------------------------------------------------
    # CALCULATE BEST EVIDENCE FOR EACH VESSEL
    # --------------------------------------------------

    for mmsi, positions in vessel_groups.items():

        best_result = None
        best_combined = -1.0

        for candidate in positions:

            distance_value = candidate.get(
                "closest_approach_km",
                candidate.get("distance_km", 9999)
            )

            try:
                distance_km = float(distance_value)
            except (TypeError, ValueError):
                distance_km = 9999.0

            vessel_time = candidate.get("timestamp")

            # Evidence scores
            t_score = time_score(
                vessel_time,
                source_start,
                source_end
            )

            s_score = space_score(
                distance_km,
                source_radius_km
            )

            d_score = drift_score(
                distance_km,
                source_radius_km
            )

            a_score = ais_score(
                candidate.get(
                    "source_region_overlap",
                    False
                ),
                candidate.get(
                    "time_window_match",
                    False
                )
            )

            combined = calculate_combined_score(
                time=t_score,
                space=s_score,
                drift=d_score,
                ais=a_score
            )

            # Keep the strongest AIS observation
            if combined > best_combined:

                best_combined = combined

                best_result = {
                    "vessel_name": candidate.get(
                        "vessel_name",
                        "UNKNOWN VESSEL"
                    ),

                    "mmsi": mmsi,

                    "time_score": round(
                        t_score,
                        4
                    ),

                    "space_score": round(
                        s_score,
                        4
                    ),

                    "drift_score": round(
                        d_score,
                        4
                    ),

                    "ais_score": round(
                        a_score,
                        4
                    ),

                    "combined_score": round(
                        combined,
                        4
                    ),

                    "closest_approach_km": round(
                        distance_km,
                        3
                    ),

                    "source_region_overlap":
                        candidate.get(
                            "source_region_overlap",
                            False
                        ),

                    "time_window_match":
                        candidate.get(
                            "time_window_match",
                            False
                        )
                }

        if best_result:
            ranked.append(best_result)

    # --------------------------------------------------
    # SORT BY COMBINED EVIDENCE
    # --------------------------------------------------

    ranked.sort(
        key=lambda x: x["combined_score"],
        reverse=True
    )

    # --------------------------------------------------
    # ASSIGN RANK
    # --------------------------------------------------

    for index, candidate in enumerate(
        ranked,
        start=1
    ):
        candidate["rank"] = index

    return ranked
