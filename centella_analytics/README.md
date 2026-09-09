# CENTELLA Football Intelligence V24 / V25 bridge

V24 is the analytical core on top of CENTELLA's existing vision/tracking pipeline. V25 adds a thin Vision → Intelligence facade and conservative candidate-event inference. Neither replaces or mutates the V21 calibration/benchmark code.

## Supported analytics

### Collective tactical
- Directed pass networks: attempts, completions, completion rate, connection frequency, progressive metres, key passes and network density.
- Defensive/offensive block structure: longitudinal compactness, team width, line heights, inter-line gaps, stretch and width indices.
- Post-loss response: time to pressure, time to regain, pressure within 5 seconds and initial nearest-player distance.
- Field tilt, progression and transition indicators.

### Predictive
- xG with a transparent bootstrap prior and a trainable regularized logistic model.
- xA based on auditable pass-to-shot links rather than arbitrary proximity.
- Pitch control: confidence-weighted arrival-time influence across a configurable pitch grid.

### Events
- Ground and aerial duels, dribble/tackle outcomes and fouls.
- Corners, free kicks, penalties and throw-ins, including shots/goals/xG and taker volumes.
- Goalkeeper saves, save rate, shot-quality faced, post-shot xG proxy, claims, aerial exits and distribution.
- Candidate pass/shot/possession inference from synchronized player + ball tracking.

### Physical / data quality
- Distance, speed, high-speed and sprint observation shares and an explicit external-load proxy.
- Player-specific baseline deviation instead of an invented universal injury score.
- Tracking continuity/confidence diagnostics.

## Data contracts

Tracking CSV requires player columns: `t,player_id,team,x,y`.

Optional player columns: `confidence,vx,vy,speed_mps,acceleration_mps2,role,is_goalkeeper`.

Optional synchronized ball columns: `ball_x,ball_y,ball_z,ball_confidence,ball_vx,ball_vy,ball_vz`.

The V21 bridge accepts native fused rows with `t,gid,xy` and can additionally consume `ball_xy` plus ball kinematics when the vision pipeline emits them.

Events JSON accepts arrays named `passes`, `shots`, `duels`, `set_pieces` and `possession_changes`, matching `events.py`.

## V25 facade

```python
from centella_analytics import VisionIntelligencePipeline

pipeline = VisionIntelligencePipeline()
report = pipeline.analyze_native_outputs(
    native_rows,
    team="home",
    team_by_gid={"7": "home", "9": "away"},
)
```

Automatically inferred events are marked as candidate data and must be validated against labelled video before being used as official event truth.

## Production rules

1. Missing observations are never silently converted to zero.
2. Model-derived values remain explicitly identified as estimates.
3. xG/xGOT accuracy is not claimed until a labelled shot dataset is calibrated and validated out of sample.
4. Workload flags are review signals, not medical diagnoses.
5. Youth-player deployments need role-based access, consent, retention limits and audit logging before production.

## CLI

```bash
python -m centella_analytics.cli \
  --tracking tracking.csv \
  --events events.json \
  --team home \
  --out report.json
```
