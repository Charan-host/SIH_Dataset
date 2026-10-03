CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- 1. INCIDENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS incidents (
    id SERIAL PRIMARY KEY,

    incident_id VARCHAR(50) UNIQUE NOT NULL,

    incident_type VARCHAR(100) NOT NULL,

    location_name VARCHAR(150),

    detected_at TIMESTAMPTZ NOT NULL,

    satellite_source VARCHAR(100),

    status VARCHAR(50) DEFAULT 'ACTIVE',

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);




-- ============================================================
-- 2. SATELLITE OBSERVATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS satellite_observations (
    id SERIAL PRIMARY KEY,

    incident_id INTEGER NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,

    satellite_name VARCHAR(100),

    sensor_name VARCHAR(100),

    observation_time TIMESTAMPTZ,

    image_path TEXT,

    footprint GEOMETRY(POLYGON, 4326),

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);




-- ============================================================
-- 3. SPILL DETECTIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS spill_detections (
    id SERIAL PRIMARY KEY,

    incident_id INTEGER NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,

    detection_time TIMESTAMPTZ,

    confidence NUMERIC(5,4),

    spill_mask_path TEXT,

    spill_polygon GEOMETRY(POLYGON, 4326),

    centroid GEOMETRY(POINT, 4326),

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);






-- ============================================================
-- 4. SPILL CHARACTERISTICS
-- ============================================================

CREATE TABLE IF NOT EXISTS spill_characteristics (
    id SERIAL PRIMARY KEY,

    incident_id INTEGER NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,

    area_km2 NUMERIC(10,3),

    perimeter_km NUMERIC(10,3),

    morphology VARCHAR(100),

    length_km NUMERIC(10,3),

    width_km NUMERIC(10,3),

    boundary_confidence NUMERIC(5,4),

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);




-- ============================================================
-- 5. METOCEAN OBSERVATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS metocean_observations (
    id SERIAL PRIMARY KEY,

    incident_id INTEGER NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,

    observation_time TIMESTAMPTZ,

    latitude NUMERIC(10,6),

    longitude NUMERIC(10,6),

    wind_u NUMERIC(10,4),

    wind_v NUMERIC(10,4),

    current_u NUMERIC(10,4),

    current_v NUMERIC(10,4),

    source VARCHAR(100),

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);




-- ============================================================
-- 6. DRIFT RUNS
-- ============================================================

CREATE TABLE IF NOT EXISTS drift_runs (
    id SERIAL PRIMARY KEY,

    incident_id INTEGER NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,

    start_time TIMESTAMPTZ,

    end_time TIMESTAMPTZ,

    duration_hours NUMERIC(8,2),

    direction VARCHAR(50),

    distance_km NUMERIC(10,3),

    uncertainty_km NUMERIC(10,3),

    source_region GEOMETRY(POLYGON, 4326),

    trajectory GEOMETRY(LINESTRING, 4326),

    model_name VARCHAR(100),

    model_confidence NUMERIC(5,4),

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Keep this schema safe to reapply to databases created before uncertainty_km
-- was added. distance_km is modeled displacement; uncertainty_km is the
-- uncertainty radius around the reconstructed source estimate.
ALTER TABLE drift_runs
    ADD COLUMN IF NOT EXISTS uncertainty_km NUMERIC(10,3);






-- ============================================================
-- 7. AIS POSITIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS ais_positions (
    id SERIAL PRIMARY KEY,

    incident_id INTEGER NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,

    mmsi VARCHAR(20) NOT NULL,

    vessel_name VARCHAR(150),

    imo_number VARCHAR(20),

    vessel_type VARCHAR(100),

    position_time TIMESTAMPTZ NOT NULL,

    latitude NUMERIC(10,6),

    longitude NUMERIC(10,6),

    sog NUMERIC(8,2),

    cog NUMERIC(8,2),

    heading NUMERIC(8,2),

    position GEOMETRY(POINT, 4326),

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);



-- ============================================================
-- 8. CANDIDATE VESSELS
-- ============================================================

CREATE TABLE IF NOT EXISTS candidate_vessels (
    id SERIAL PRIMARY KEY,

    incident_id INTEGER NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,

    mmsi VARCHAR(20) NOT NULL,

    vessel_name VARCHAR(150),

    vessel_type VARCHAR(100),

    candidate_rank INTEGER,

    attribution_score NUMERIC(6,4),

    temporal_score NUMERIC(6,4),

    spatial_score NUMERIC(6,4),

    drift_score NUMERIC(6,4),

    heading_speed_score NUMERIC(6,4),

    ais_quality_score NUMERIC(6,4),

    evidence_summary TEXT,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);




-- ============================================================
-- 9. EVIDENCE SCORES
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_scores (
    id SERIAL PRIMARY KEY,

    candidate_id INTEGER NOT NULL
        REFERENCES candidate_vessels(id)
        ON DELETE CASCADE,

    evidence_type VARCHAR(100) NOT NULL,

    evidence_value NUMERIC(8,4),

    confidence NUMERIC(5,4),

    explanation TEXT,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);








-- ============================================================
-- 10. CASC RUNS
-- ============================================================

CREATE TABLE IF NOT EXISTS casc_runs (
    id SERIAL PRIMARY KEY,

    incident_id INTEGER NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,

    candidate_id INTEGER
        REFERENCES candidate_vessels(id)
        ON DELETE SET NULL,

    leading_vessel VARCHAR(150),

    winner_distribution JSONB NOT NULL DEFAULT '{}'::jsonb,

    analysis_signature VARCHAR(64),

    total_scenarios INTEGER NOT NULL,

    winner_probability NUMERIC(6,4),

    closest_alternate VARCHAR(150),

    winner_flip_minutes NUMERIC(8,2),

    normalized_perturbation NUMERIC(6,4),

    stability_status VARCHAR(50),

    uncertainty_summary TEXT,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE casc_runs
    ADD COLUMN IF NOT EXISTS leading_vessel VARCHAR(150);
ALTER TABLE casc_runs
    ADD COLUMN IF NOT EXISTS winner_distribution JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE casc_runs
    ADD COLUMN IF NOT EXISTS analysis_signature VARCHAR(64);
UPDATE casc_runs cr
SET leading_vessel = cv.vessel_name
FROM candidate_vessels cv
WHERE cr.candidate_id = cv.id
  AND cr.leading_vessel IS NULL;






-- ============================================================
-- 11. CASC SCENARIOS
-- ============================================================

CREATE TABLE IF NOT EXISTS casc_scenarios (
    id SERIAL PRIMARY KEY,

    casc_run_id INTEGER NOT NULL
        REFERENCES casc_runs(id)
        ON DELETE CASCADE,

    scenario_number INTEGER NOT NULL,

    spill_time_offset_min NUMERIC(8,2),

    origin_offset_km NUMERIC(8,3),

    current_perturbation_pct NUMERIC(6,2),

    wind_perturbation_pct NUMERIC(6,2),

    ais_gap_minutes NUMERIC(8,2),

    winner_candidate_id INTEGER
        REFERENCES candidate_vessels(id)
        ON DELETE SET NULL,

    winner_score NUMERIC(6,4),

    valid BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);





-- ============================================================
-- 12. CERTIFICATES
-- ============================================================

CREATE TABLE IF NOT EXISTS certificates (
    id SERIAL PRIMARY KEY,

    incident_id INTEGER NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,

    casc_run_id INTEGER
        REFERENCES casc_runs(id)
        ON DELETE SET NULL,

    certificate_id VARCHAR(100) UNIQUE NOT NULL,

    leading_vessel VARCHAR(150),

    stability_status VARCHAR(50),

    winner_probability NUMERIC(6,4),

    closest_alternate VARCHAR(150),

    winner_flip_minutes NUMERIC(8,2),

    normalized_perturbation NUMERIC(6,4),

    decision_summary TEXT,

    generated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);





-- ============================================================
-- 13. AUDIT EVENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_events (
    id SERIAL PRIMARY KEY,

    incident_id INTEGER NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,

    event_type VARCHAR(100) NOT NULL,

    event_description TEXT,

    source_module VARCHAR(100),

    user_name VARCHAR(100),

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
