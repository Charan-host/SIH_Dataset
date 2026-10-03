-- ============================================================
-- DEMO DATA
-- ============================================================
BEGIN;

INSERT INTO incidents (
    incident_id,
    incident_type,
    location_name,
    detected_at,
    satellite_source,
    status
)
VALUES (
    'CASC-2026-001',
    'Possible Marine Oil Spill',
    'Gulf of Mexico',
    '2026-09-04 08:42:00+00',
    'Sentinel-1 SAR',
    'ACTIVE'
);



-- ============================================================
-- DEMO SATELLITE OBSERVATION
-- ============================================================

INSERT INTO satellite_observations (
    incident_id,
    satellite_name,
    sensor_name,
    observation_time,
    image_path
)
SELECT
    id,
    'Sentinel-1',
    'SAR',
    '2026-09-04 08:42:00+00',
    'data/demo/sentinel1_casc_2026_001.tif'
FROM incidents
WHERE incident_id = 'CASC-2026-001';






-- ============================================================
-- DEMO SPILL DETECTION
-- ============================================================

INSERT INTO spill_detections (
    incident_id,
    detection_time,
    confidence,
    spill_mask_path
)
SELECT
    id,
    '2026-09-04 08:42:00+00',
    0.9100,
    'data/demo/spill_mask_casc_2026_001.tif'
FROM incidents
WHERE incident_id = 'CASC-2026-001';


-- ============================================================
-- DEMO SPILL CHARACTERISTICS
-- ============================================================

INSERT INTO spill_characteristics (
    incident_id,
    area_km2,
    perimeter_km,
    morphology,
    length_km,
    width_km,
    boundary_confidence
)
SELECT
    id,
    12.800,
    18.600,
    'Organic Slick',
    5.400,
    2.370,
    0.8800
FROM incidents
WHERE incident_id = 'CASC-2026-001';





-- ============================================================
-- DEMO METOCEAN OBSERVATION
-- ============================================================

INSERT INTO metocean_observations (
    incident_id,
    observation_time,
    latitude,
    longitude,
    wind_u,
    wind_v,
    current_u,
    current_v,
    source
)
SELECT
    id,
    '2026-09-04 08:00:00+00',
    28.950000,
    -89.150000,
    4.20,
    -2.10,
    0.35,
    0.18,
    'ERA5 + GLORYS12V1'
FROM incidents
WHERE incident_id = 'CASC-2026-001';




-- ============================================================
-- DEMO DRIFT RUN
-- ============================================================

INSERT INTO drift_runs (
    incident_id,
    start_time,
    end_time,
    duration_hours,
    direction,
    model_name,
    uncertainty_km
)
SELECT
    id,
    '2026-09-04 02:42:00+00',
    '2026-09-04 08:42:00+00',
    6.00,
    'NORTHEAST',
    'CASC Drift Model',
    5.00
FROM incidents
WHERE incident_id = 'CASC-2026-001';







-- ============================================================
-- DEMO AIS POSITIONS
-- ============================================================

INSERT INTO ais_positions (
    incident_id,
    mmsi,
    vessel_name,
    imo_number,
    vessel_type,
    position_time,
    latitude,
    longitude,
    sog,
    cog,
    heading
)
SELECT
    id,
    '636019876',
    'ALPHA MERIDIAN',
    '9876543',
    'Crude Tanker',
    '2026-09-04 07:30:00+00',
    28.840000,
    -89.200000,
    10.80,
    72.00,
    72.00
FROM incidents
WHERE incident_id = 'CASC-2026-001';




-- ============================================================
-- 7. DEMO AIS POSITIONS
-- This repeated fixture INSERT is the source of the two identical ALPHA
-- MERIDIAN rows. Keep both existing sample records; they represent one vessel
-- observation, not two vessels. Ranking collapses them by MMSI and the UI
-- collapses exact duplicate observations for display.
-- ============================================================

INSERT INTO ais_positions (
    incident_id,
    mmsi,
    vessel_name,
    imo_number,
    vessel_type,
    position_time,
    latitude,
    longitude,
    sog,
    cog,
    heading
)
SELECT
    id,
    '636019876',
    'ALPHA MERIDIAN',
    '9876543',
    'Crude Tanker',
    '2026-09-04 07:30:00+00',
    28.840000,
    -89.200000,
    10.80,
    72.00,
    72.00
FROM incidents
WHERE incident_id = 'CASC-2026-001';


-- ============================================================
-- 8. DEMO CANDIDATE VESSELS
-- ============================================================

INSERT INTO candidate_vessels (
    incident_id,
    mmsi,
    vessel_name,
    vessel_type,
    candidate_rank,
    attribution_score,
    temporal_score,
    spatial_score,
    drift_score,
    heading_speed_score,
    ais_quality_score,
    evidence_summary
)
SELECT
    id,
    '636019876',
    'ALPHA MERIDIAN',
    'Crude Tanker',
    1,
    0.8700,
    0.9200,
    0.8800,
    0.9100,
    0.8400,
    0.8000,
    'Strong temporal, spatial and drift consistency with the detected spill.'
FROM incidents
WHERE incident_id = 'CASC-2026-001';


INSERT INTO candidate_vessels (
    incident_id,
    mmsi,
    vessel_name,
    vessel_type,
    candidate_rank,
    attribution_score,
    temporal_score,
    spatial_score,
    drift_score,
    heading_speed_score,
    ais_quality_score,
    evidence_summary
)
SELECT
    id,
    '636019877',
    'BRAVO TRADER',
    'Product Tanker',
    2,
    0.7400,
    0.7800,
    0.7600,
    0.7200,
    0.7300,
    0.7000,
    'Moderate spatial and temporal consistency; weaker drift agreement.'
FROM incidents
WHERE incident_id = 'CASC-2026-001';


INSERT INTO candidate_vessels (
    incident_id,
    mmsi,
    vessel_name,
    vessel_type,
    candidate_rank,
    attribution_score,
    temporal_score,
    spatial_score,
    drift_score,
    heading_speed_score,
    ais_quality_score,
    evidence_summary
)
SELECT
    id,
    '636019878',
    'CHARLIE STAR',
    'Cargo Vessel',
    3,
    0.6100,
    0.6500,
    0.6200,
    0.5800,
    0.6000,
    0.5900,
    'Lower overall consistency with the reconstructed spill source region.'
FROM incidents
WHERE incident_id = 'CASC-2026-001';


-- ============================================================
-- 9. DEMO EVIDENCE SCORES
-- ============================================================

INSERT INTO evidence_scores (
    candidate_id,
    evidence_type,
    evidence_value,
    confidence,
    explanation
)
SELECT
    id,
    'TEMPORAL',
    temporal_score,
    0.9000,
    'AIS position timing is consistent with the estimated spill window.'
FROM candidate_vessels
WHERE vessel_name = 'ALPHA MERIDIAN'
  AND incident_id = (
      SELECT id FROM incidents
      WHERE incident_id = 'CASC-2026-001'
  );


INSERT INTO evidence_scores (
    candidate_id,
    evidence_type,
    evidence_value,
    confidence,
    explanation
)
SELECT
    id,
    'SPATIAL',
    spatial_score,
    0.8800,
    'Vessel track is spatially consistent with the reconstructed source region.'
FROM candidate_vessels
WHERE vessel_name = 'ALPHA MERIDIAN'
  AND incident_id = (
      SELECT id FROM incidents
      WHERE incident_id = 'CASC-2026-001'
  );


INSERT INTO evidence_scores (
    candidate_id,
    evidence_type,
    evidence_value,
    confidence,
    explanation
)
SELECT
    id,
    'DRIFT',
    drift_score,
    0.9100,
    'Vessel movement is consistent with the estimated backtrack trajectory.'
FROM candidate_vessels
WHERE vessel_name = 'ALPHA MERIDIAN'
  AND incident_id = (
      SELECT id FROM incidents
      WHERE incident_id = 'CASC-2026-001'
  );


-- ============================================================
-- 10. DEMO CASC RUN
-- ============================================================

INSERT INTO casc_runs (
    incident_id,
    candidate_id,
    total_scenarios,
    winner_probability,
    closest_alternate,
    winner_flip_minutes,
    normalized_perturbation,
    stability_status,
    uncertainty_summary
)
SELECT
    i.id,
    c.id,
    5000,
    0.8200,
    'BRAVO TRADER',
    14.00,
    0.8400,
    'ROBUST',
    'Uncertainty bounds: ±30 min spill time, ±5 km origin, ±15% current, ±15% wind and observed AIS gaps.'
FROM incidents i
JOIN candidate_vessels c
    ON c.incident_id = i.id
WHERE i.incident_id = 'CASC-2026-001'
  AND c.vessel_name = 'ALPHA MERIDIAN';


-- ============================================================
-- 11. DEMO CASC SCENARIOS
-- ============================================================

INSERT INTO casc_scenarios (
    casc_run_id,
    scenario_number,
    spill_time_offset_min,
    origin_offset_km,
    current_perturbation_pct,
    wind_perturbation_pct,
    ais_gap_minutes,
    winner_candidate_id,
    winner_score,
    valid
)
SELECT
    cr.id,
    1,
    5.00,
    2.00,
    5.00,
    -5.00,
    3.00,
    cv.id,
    0.8500,
    TRUE
FROM casc_runs cr
JOIN candidate_vessels cv
    ON cv.vessel_name = 'ALPHA MERIDIAN'
WHERE cr.incident_id = (
    SELECT id FROM incidents
    WHERE incident_id = 'CASC-2026-001'
)
AND cv.incident_id = cr.incident_id;


-- ============================================================
-- 12. DEMO CERTIFICATE
-- ============================================================

INSERT INTO certificates (
    incident_id,
    casc_run_id,
    certificate_id,
    leading_vessel,
    stability_status,
    winner_probability,
    closest_alternate,
    winner_flip_minutes,
    normalized_perturbation,
    decision_summary
)
SELECT
    i.id,
    cr.id,
    'CASC-CERT-2026-001',
    'ALPHA MERIDIAN',
    'ROBUST',
    0.8200,
    'BRAVO TRADER',
    14.00,
    0.8400,
    'ALPHA MERIDIAN remains the leading source hypothesis across the evaluated uncertainty scenarios. Attribution should be treated as a robust analytical result, not definitive proof of responsibility.'
FROM incidents i
JOIN casc_runs cr
    ON cr.incident_id = i.id
WHERE i.incident_id = 'CASC-2026-001';


-- ============================================================
-- 13. DEMO AUDIT EVENTS
-- ============================================================

INSERT INTO audit_events (
    incident_id,
    event_type,
    event_description,
    source_module,
    user_name
)
SELECT
    id,
    'DETECTION_COMPLETED',
    'Oil spill detection completed using Sentinel-1 SAR.',
    'Detection',
    'SYSTEM'
FROM incidents
WHERE incident_id = 'CASC-2026-001';

INSERT INTO audit_events (
    incident_id,
    event_type,
    event_description,
    source_module,
    user_name
)
SELECT
    id,
    'DRIFT_BACKTRACK_COMPLETED',
    'Six-hour drift backtracking completed and source region estimated.',
    'Drift',
    'SYSTEM'
FROM incidents
WHERE incident_id = 'CASC-2026-001';


INSERT INTO audit_events (
    incident_id,
    event_type,
    event_description,
    source_module,
    user_name
)
SELECT
    id,
    'VESSEL_RANKING_COMPLETED',
    'Candidate vessels ranked using temporal, spatial, drift, heading/speed and AIS quality evidence.',
    'Vessel Correlation',
    'SYSTEM'
FROM incidents
WHERE incident_id = 'CASC-2026-001';


INSERT INTO audit_events (
    incident_id,
    event_type,
    event_description,
    source_module,
    user_name
)
SELECT
    id,
    'CASC_ANALYSIS_COMPLETED',
    'CASC evaluated 5000 valid uncertainty scenarios and produced a robust attribution result.',
    'CASC',
    'SYSTEM'
FROM incidents
WHERE incident_id = 'CASC-2026-001';


INSERT INTO audit_events (
    incident_id,
    event_type,
    event_description,
    source_module,
    user_name
)
SELECT
    id,
    'CERTIFICATE_GENERATED',
    'Attribution Stability Certificate generated for the leading source hypothesis.',
    'CASC',
    'SYSTEM'
FROM incidents
WHERE incident_id = 'CASC-2026-001';

COMMIT;
