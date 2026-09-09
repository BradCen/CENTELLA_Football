# CENTELLA Football Intelligence V24

V24 is a standalone analytics layer designed to sit on top of CENTELLA's existing vision/tracking pipeline. It does not replace or mutate the V21 calibration/benchmark code.

## Supported analytics

### Collective tactical
- Directed pass networks: attempts, completions, completion rate, connection frequency, progressive metres, key passes and network density.
- Defensive/offensive block structure: longitudinal compactness, team width, line heights, inter-line gaps, stretch and width indices.
- Post-loss response: time to pressure, time to regain, pressure within 5 seconds and initial nearest-player distance.
- Field tilt and progression indicators.
- Transition timing based on explicit possession-change events.

### Predictive
- xG with a transparent bootstrap prior and a trainable regularized logistic model.
- xA based on auditable pass-to-shot links rather than assigning credit to arbitrary nearby shots.
- Pitch control: confidence-weighted arrival-time influence across a configurable pitch grid.

### Events
- Ground and aerial duels, dribble/tackle outcomes and fouls.
- Corners, free kicks, penalties and throw-ins, including shots/goals/xG and taker volumes.
- Goalkeeper saves, save rate, shot-quality faced, a post-shot xG proxy, claims, aerial exits and distribution.

### Physical / data quality
- Distance, speed, high-speed and sprint observation shares and an explicit external-load proxy.
- Player-specific baseline deviation instead of an invented universal injury score.
- Tracking continuity/confidence diagnostics.

## Data contracts

Tracking CSV requires: `t,player_id,team,x,y`.

Optional tracking columns: `confidence,vx,vy,speed_mps,acceleration_mps2,role,is_goalkeeper`.

Events JSON accepts arrays named `passes`, `shots`, `duels`, `set_pieces` and `possession_changes`, matching the dataclasses in `events.py`.

## Production rules

1. A missing observation is never silently converted to zero.
2. A model estimate is labelled as a model estimate in the report.
3. xG/xGOT accuracy is not claimed until a labelled shot dataset is used for calibration and out-of-sample validation.
4. Workload flags are coaching/medical-review signals, not diagnoses.
5. Youth-player deployments should add role-based access, consent, retention limits and audit logging before production use.

## CLI

```bash
python -m centella_analytics.cli \
  --tracking tracking.csv \
  --events events.json \
  --team home \
  --out report.json
```
