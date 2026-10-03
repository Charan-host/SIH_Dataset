# Candidate score and CASC semantics

## Current database input

For incident 1, the database has two AIS rows, one distinct MMSI, and one
distinct AIS observation: ALPHA MERIDIAN. The runtime candidate endpoint groups
observations by MMSI and returns one candidate. The `candidate_vessels` table
contains three rows, but `database/seed.sql` labels these as demo candidate
vessels. BRAVO TRADER and CHARLIE STAR have no corresponding AIS observations
in this incident. They are fixture records, not additional observed vessels,
and are not passed to runtime ranking or CASC.

`GET /candidates/{incident_id}` returns additive `score_semantics` metadata,
including the runtime ranking field, the distinct persisted fixture field,
fixture values by MMSI, and `ais_data_source_type=SEEDED_DEMONSTRATION`. Fixture
scores are traceability metadata only and are excluded from each candidate
object, so they do not affect the ranking inputs or CASC input signature.

## Score meanings

The runtime `combined_score` is the ranking metric:

```text
0.25 * time_score + 0.30 * space_score + 0.25 * drift_score + 0.20 * ais_score
```

For the current ALPHA MERIDIAN observation, it is `0.4375`. Duplicate rows and
multiple observations for one MMSI do not add candidates or sum scores. The
strongest observation is retained.

`candidate_vessels.attribution_score` is a separate persisted seed fixture
metric. ALPHA MERIDIAN's value is `0.8700`; the other fixture rows are `0.7400`
and `0.6100`. The seed stores temporal, spatial, drift, heading/speed, and AIS
quality components, but the application has no documented runtime formula
that derives these fixture values. Runtime ranking and CASC do not use them.
The API and UI label them separately from the runtime combined score.

CASC recomputes a scenario score for every runtime candidate using independent
plus/minus 10% multipliers on that candidate's precomputed time, space, drift,
and AIS scores. It clamps components to [0, 1], then applies the same four
weights. `winner_probability` is the fraction of evaluated scenarios won by
the baseline leading candidate. `ROBUST` means that fraction is at least 0.80;
it does not by itself imply that multiple candidates were available. With one
runtime candidate, a 1.0 share is trivial and is explicitly reported as not
competitive stability evidence.

## Distance score overlap

## Drift source region and candidate screening reference

The two endpoints intentionally report different spatial references. `GET
/drift/{incident_id}` backtracks from the spill-position proxy and returns a
modeled source-region center and its uncertainty radius. `GET
/candidates/{incident_id}` currently ranks AIS observations from the latest
metocean observation location with a temporary operational 5 km radius. The
candidate reference is a screening proxy; it is not the reconstructed source
center or uncertainty radius returned by the drift model. The frontend labels
these roles separately. No vessel coordinates or map geometry are adjusted to
make the references appear coincident.

The runtime `drift_score(distance_km, source_radius_km)` currently calls
`space_score` with the exact same arguments. The ranking code does not provide
a trajectory or backtrack path to an independent drift metric. This appears to
be a distance proxy, not independently validated drift evidence. Consequently
55% of the runtime combined score weights the same distance-derived signal
twice.

The production formula is retained to avoid silently changing ranking behavior
or invalidating existing CASC/certificate records. A mathematically meaningful
replacement needs an actual trajectory-to-backtrack comparison, not merely a
renaming or reweighting of the existing distance. Any future scoring change
should be explicitly versioned and generate a distinct CASC input signature;
the existing persisted records must remain available for audit.

## CASC limits and traceability

CASC varies precomputed evidence-score components only. It does not recompute
AIS features or perturb wind, ocean currents, AIS trajectories, timestamps,
source geometry, or spill geometry. The persisted run response exposes its run
ID, analysis signature, scenario count, runtime candidate count, winner
distribution, perturbation flags, and interpretation. Certificate responses
carry the same run/signature/scenario/candidate metadata.

`winner_flip_minutes` is the score gap multiplied by 60. It is a
minute-equivalent indicator, not a physical time shift or searched threshold.

## Seeded AIS records

`database/seed.sql` contains two identical ALPHA MERIDIAN AIS inserts. They
remain intact. Ranking groups by MMSI, the map renders one marker per MMSI, and
the AIS table hides exact duplicate observations. The current source type is
seeded demonstration data; no external live AIS provider is connected.
