# CENTELLA Football Intelligence V24 → V31

V24 is the analytical core on top of CENTELLA's vision/tracking pipeline. V25 adds the Vision → Intelligence facade and conservative candidate-event inference. V26–V30 add player, tactical, performance, coach and platform layers. V31 adds deterministic extended tactical/spatial intelligence and coach-readable reporting. None of these layers replaces the V21/V62 vision benchmark contract.

## Supported analytics

### Collective tactical
- Directed pass networks: attempts, completions, completion rate, connection frequency, progressive metres, key passes and network density.
- Defensive/offensive block structure: longitudinal compactness, team width, line heights, inter-line gaps, stretch and width indices.
- Post-loss response: time to pressure, time to regain, pressure within 5 seconds and initial nearest-player distance.
- Field tilt, progression and transition indicators.
- Player interactions, local numerical advantage and repeatable observed structures.

### Extended V31 tactical/spatial
- 6×5 pitch-zone occupation and player spatial footprints.
- Transparent territorial-value prior based on advancement and centrality.
- Ball progression and net advancement.
- Local numerical superiority/disadvantage around the ball.
- Rest-defence and deepest-player geometry proxies.
- Defensive-line geometry and line-span diagnostics.
- Ball-side pressure proximity signals.
- Chronological event index for downstream interfaces.

### Predictive
- xG with a transparent bootstrap prior and a trainable regularized logistic model.
- xA based on auditable pass-to-shot links rather than arbitrary proximity.
- Pitch control: confidence-weighted arrival-time influence across a configurable pitch grid.

### Events
- Ground and aerial duels, dribble/tackle outcomes and fouls.
- Corners, free kicks, penalties and throw-ins, including shots/goals/xG and taker volumes.
- Goalkeeper saves, save rate, shot-quality faced, post-shot xG proxy, claims, aerial exits and distribution.
- Candidate pass/shot/possession inference from synchronized player + ball tracking.

### Physical / player / coach
- Distance, speed, high-speed and sprint observation shares and an explicit external-load proxy.
- Player-specific baseline deviation instead of an invented universal injury score.
- Player passports, spatial occupation, participation and broad role-suitability hypotheses.
- Ranked coach review prompts with evidence and uncertainty.
- Platform orchestration from synchronized observations to coach-facing intelligence.

### Reporting

```python
from centella_analytics import build_match_report
summary, markdown = build_match_report(report)
```

The summary is machine-readable and the Markdown output is designed for coach/analyst review. Both preserve provenance and distinguish candidate/modelled estimates from validated event truth.

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

## CLI

```bash
python -m centella_analytics.cli \
  --tracking tracking.csv \
  --events events.json \
  --team home \
  --out report.json \
  --summary-out summary.json \
  --markdown-out report.md
```

## Production rules

1. Missing observations are never silently converted to zero.
2. Model-derived values remain explicitly identified as estimates.
3. xG/xGOT accuracy is not claimed until a labelled shot dataset is calibrated and validated out of sample.
4. Workload flags are review signals, not medical diagnoses.
5. Youth-player deployments need role-based access, consent, retention limits and audit logging.
6. V31 territorial value is a transparent positional prior, not a trained xT/OBV model.
7. V31 defensive-line output is a geometric proxy, not an offside-law decision.
