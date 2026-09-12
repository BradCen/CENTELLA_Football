# CENTELLA Football — Vision & Football Intelligence

CENTELLA Football is the football-analysis software stack built around **computer vision, multi-camera tracking, event semantics, and football intelligence**.

This branch is intentionally **not a football game or simulator**. Its purpose is to turn synchronized visual observations into auditable football metrics and higher-level tactical, physical, predictive, player and coach intelligence.

## Architecture

```text
Video / cameras
      ↓
vision_v1/
  V21 vision, calibration, synchronization and V62 causal tracking
      ↓
centella_analytics/
  V24 analytics → V25 event bridge → V26 player → V27 tactical
  → V28 performance → V29 coach → V30 platform → V31 extended intelligence
      ↓
reports / APIs / future coach & player interfaces
```

### `vision_v1/` — Vision layer

The vision layer contains the existing V21 work plus the later OOS-tracked refinements: calibration, camera synchronization, multi-camera fusion, player/ball observations, causal track-set selection and benchmark tooling. V21 remains a compatibility foundation; higher-level analytics do not rewrite its benchmark contract.

### `centella_analytics/` — Intelligence layer

The analytics package consumes tracking and synchronized ball observations and provides:

- collective tactical structure: pass networks, block geometry, compactness, width, line heights, transitions and post-loss response;
- predictive models: xG bootstrap/model fitting, auditable xA, and confidence-weighted pitch control;
- event semantics: passes, shots, possession changes and extensible football event schemas;
- goalkeeper, duel, set-piece, progression and transition analytics;
- physical workload and data-quality diagnostics;
- V26 player intelligence: observation quality, movement, spatial occupation, technical rates and participation;
- V27 tactical intelligence: player interactions, local numerical advantage and repeatable observed structures;
- V28 performance intelligence: external-load and movement exposure derived from tracking;
- V29 coach intelligence: ranked, evidence-backed review prompts with explicit uncertainty;
- V30 platform orchestration: one auditable contract from synchronized tracking to coach-facing intelligence;
- V31 extended intelligence: pitch-zone occupation, territorial value, ball progression, numerical superiority, rest-defence geometry, defensive-line geometry, ball-side pressure proximity and a chronological event index;
- the V25 Vision → Intelligence bridge for native V21-style fused rows.

## Separation from the legacy football game

The repository previously contained a separate football game/environment project. That code is **not part of the new Vision & Football Intelligence stack**.

The legacy game has been preserved on the dedicated Git branch:

`archive/football-game`

That archive exists so the historical game work remains recoverable without contaminating the analytics branch with simulator code, game dependencies, build scripts or unrelated documentation.

**Do not add gameplay/simulation code to this branch.** New functionality should belong to one of these boundaries:

- `vision_v1/` — perception, calibration, synchronization and tracking;
- `centella_analytics/` — football events, metrics, models and intelligence;
- `docs/` — contracts, architecture, provenance and validation rules.

## Data contract

Player tracking rows use the canonical fields:

` t, player_id, team, x, y `

Optional player fields include confidence, velocity, speed, acceleration, role and goalkeeper status. Synchronized ball observations can additionally provide position, confidence and velocity.

Automatically inferred events are **candidate observations**, not ground truth. Official event truth requires labelled video validation.

## Model and data integrity rules

1. Missing observations are never silently converted to zero.
2. Model-derived values remain explicitly identified as estimates.
3. xG/xA/xGOT performance is not claimed without appropriate labelled-data calibration and out-of-sample validation.
4. Candidate event inference is never presented as manually validated event truth.
5. Workload outputs are performance/review signals, not medical diagnoses.
6. V29 coaching insights are evidence-backed review prompts, not autonomous coaching decisions.
7. Production deployments for player data must add appropriate access control, consent, retention and audit mechanisms.

## Development status

The current development line contains the **V24 → V31 Vision → Football Intelligence architecture**. V24-V28 provide the analytical substrate, V29 turns measurements into explainable coaching observations, V30 provides the unified platform boundary, and V31 adds transparent advanced tactical/spatial indicators. The V21/V62 vision layer remains the observation foundation.

See `centella_analytics/README.md`, `docs/V26_PLAYER_INTELLIGENCE.md`, `docs/V30_PLATFORM.md`, `docs/V31_EXTENDED_INTELLIGENCE.md` and `docs/PROJECT_BOUNDARIES.md` for module contracts, provenance and validation rules.

## Validation

GitHub Actions runs the analytics regression suite plus dedicated Alfheim OOS validation. The final V60/V61/V62 benchmark completed successfully with ground-truth-blind inference and an integrity guard. Unit tests and public OOS benchmarks do not replace real-match validation.

The production path still requires labelled multi-camera/ball datasets, event-truth alignment, model calibration, broader benchmark coverage, hardened video ingestion and a validated coach/player presentation layer.
