# V26 — Player Intelligence

V26 adds player-level intelligence on top of the V24 analytical core and V25 vision-to-analytics bridge.

## Data flow

`V21 fused tracking → V25 event bridge → V26 player intelligence`

The layer consumes synchronized player tracking and an `EventTimeline`. It does not depend on a particular detector or camera vendor.

## Measurements

For each observed player, V26 reports:

- observation duration, sample count, confidence and tracking coverage;
- mean/max speed, high-speed and sprint shares, and observed acceleration;
- spatial mean position, normalized coordinates and longitudinal/lateral occupancy entropy;
- pass attempts/completions, completion rate, progressive pass distance, key passes, through balls, receptions, shots and duels per 90;
- event participation and the underlying event mix.

## Interpretation boundary

V26 separates measurements from interpretation. It does not claim to infer hidden intent, talent, value, injury status or an objectively correct position from tracking alone.

Role suitability remains a developmental hypothesis and requires football-context validation. Event-derived metrics inherit the provenance of the supplied event timeline. Candidate events inferred from tracking remain explicitly marked as unvalidated.

## Next layer

V27 will consume the same evidence graph to model collective tactical patterns and interactions between players, rather than replacing V26 with another isolated metric collection.
