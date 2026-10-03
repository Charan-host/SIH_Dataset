from math import radians, sin, cos, atan2, sqrt, degrees
from datetime import timedelta, timezone

EARTH_RADIUS_KM = 6371.0088
DEFAULT_WINDAGE = 0.03


def destination(lat, lon, bearing_deg, distance_km):
    """Return destination latitude/longitude after travelling distance_km."""
    lat1 = radians(float(lat))
    lon1 = radians(float(lon))
    bearing = radians(float(bearing_deg))
    angular_distance = float(distance_km) / EARTH_RADIUS_KM

    lat2 = sin(lat1) * cos(angular_distance) + (
        cos(lat1) * sin(angular_distance) * cos(bearing)
    )
    lat2 = atan2(lat2, sqrt(max(0.0, 1.0 - lat2 * lat2)))

    lon2 = lon1 + atan2(
        sin(bearing) * sin(angular_distance) * cos(lat1),
        cos(angular_distance) - sin(lat1) * sin(lat2),
    )

    return degrees(lat2), ((degrees(lon2) + 540) % 360) - 180


def vector_from_speed_direction(speed_knots, direction_deg):
    """Convert speed in knots + bearing into east/north velocity."""
    speed_kmh = float(speed_knots) * 1.852
    angle = radians(float(direction_deg))
    return speed_kmh * sin(angle), speed_kmh * cos(angle)


def vector_to_speed_direction(east, north):
    """Convert east/north velocity into speed in knots + bearing."""
    speed_kmh = sqrt(float(east) ** 2 + float(north) ** 2)
    bearing = (degrees(atan2(float(east), float(north))) + 360) % 360
    return speed_kmh / 1.852, bearing


def wind_from_to_direction(wind_from_deg):
    """Meteorological wind direction is FROM; drift needs TO."""
    return (float(wind_from_deg) + 180) % 360


def effective_drift(
    wind_speed_knots,
    wind_from_deg,
    current_speed_knots,
    current_direction_deg,
    windage=DEFAULT_WINDAGE,
):
    """Combine ocean current with a small windage contribution."""
    wind_to = wind_from_to_direction(wind_from_deg)

    current_e, current_n = vector_from_speed_direction(
        current_speed_knots, current_direction_deg
    )
    wind_e, wind_n = vector_from_speed_direction(
        wind_speed_knots, wind_to
    )

    return vector_to_speed_direction(
        current_e + wind_e * float(windage),
        current_n + wind_n * float(windage),
    )


def generate_trajectory(
    start_lat,
    start_lon,
    start_time,
    duration_hours,
    wind_speed_knots,
    wind_from_deg,
    current_speed_knots,
    current_direction_deg,
    direction_mode="forward",
    step_minutes=30,
):
    """Generate forward forecast or backward source reconstruction."""
    drift_speed, drift_direction = effective_drift(
        wind_speed_knots,
        wind_from_deg,
        current_speed_knots,
        current_direction_deg,
    )

    travel_direction = (
        (drift_direction + 180) % 360
        if direction_mode == "backward"
        else drift_direction
    )

    points = []
    total_steps = int((float(duration_hours) * 60) / int(step_minutes))

    for step in range(total_steps + 1):
        elapsed_hours = (step * int(step_minutes)) / 60
        distance_km = drift_speed * 1.852 * elapsed_hours

        lat, lon = destination(
            start_lat, start_lon, travel_direction, distance_km
        )

        if direction_mode == "backward":
            point_time = start_time - timedelta(minutes=step * int(step_minutes))
        else:
            point_time = start_time + timedelta(minutes=step * int(step_minutes))

        points.append({
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "timestamp": point_time.isoformat(),
            "distance_km": round(distance_km, 3),
        })

    return {
        "points": points,
        "speed_knots": round(drift_speed, 3),
        "direction_deg": round(travel_direction, 2),
    }


def calculate_drift(
    spill_lat,
    spill_lon,
    spill_time,
    backtrack_hours,
    forecast_hours,
    wind_speed_knots,
    wind_from_deg,
    current_speed_knots,
    current_direction_deg,
    wind_uncertainty=0.15,
    current_uncertainty=0.10,
):
    """Run transparent forward drift and backward source reconstruction."""
    if spill_time.tzinfo is None:
        spill_time = spill_time.replace(tzinfo=timezone.utc)

    backtrack = generate_trajectory(
        spill_lat,
        spill_lon,
        spill_time,
        backtrack_hours,
        wind_speed_knots,
        wind_from_deg,
        current_speed_knots,
        current_direction_deg,
        direction_mode="backward",
    )

    forecast = generate_trajectory(
        spill_lat,
        spill_lon,
        spill_time,
        forecast_hours,
        wind_speed_knots,
        wind_from_deg,
        current_speed_knots,
        current_direction_deg,
        direction_mode="forward",
    )

    source = backtrack["points"][-1]

    uncertainty_factor = float(wind_uncertainty) + float(current_uncertainty)
    source_radius_km = max(
        1.0,
        source["distance_km"] * uncertainty_factor,
    )

    confidence = max(0.0, min(1.0, 1.0 - uncertainty_factor))

    return {
        "spill_position": {
            "latitude": round(float(spill_lat), 6),
            "longitude": round(float(spill_lon), 6),
        },
        "spill_time": spill_time.isoformat(),
        "backtrack": {
            "duration_hours": backtrack_hours,
            "speed_knots": backtrack["speed_knots"],
            "direction_deg": backtrack["direction_deg"],
            "trajectory": backtrack["points"],
        },
        "source_region": {
            "latitude": source["latitude"],
            "longitude": source["longitude"],
            "radius_km": round(source_radius_km, 2),
            "confidence": round(confidence, 3),
        },
        "forecast": {
            "duration_hours": forecast_hours,
            "speed_knots": forecast["speed_knots"],
            "direction_deg": forecast["direction_deg"],
            "trajectory": forecast["points"],
        },
        "inputs": {
            "wind_speed_knots": wind_speed_knots,
            "wind_from_deg": wind_from_deg,
            "current_speed_knots": current_speed_knots,
            "current_direction_deg": current_direction_deg,
            "wind_uncertainty": wind_uncertainty,
            "current_uncertainty": current_uncertainty,
            "windage_factor": DEFAULT_WINDAGE,
        },
    }
