# CENTELLA Football — Vision & Football Intelligence

CENTELLA Football is the football-analysis software stack built around **computer vision, multi-camera tracking, event semantics, and football intelligence**.

This branch is intentionally **not a football game or simulator**. Its purpose is to turn synchronized visual observations into auditable football metrics and higher-level tactical, physical, and predictive intelligence.

## Architecture

```text
Video / cameras
      ↓
vision_v1/
  V21 vision, calibration, synchronization and tracking
      ↓
centella_analytics/
  event semantics + football intelligence
      ↓
reports / APIs / future coach & player interfaces
```

### `vision_v1/` — Vision layer

The vision layer contains the existing V21 work: calibration, camera synchronization, multi-camera fusion, tracking and benchmark tooling. V21 remains a verified foundation and is not replaced by the analytics work.

### `centella_analytics/` — Intelligence layer

The analytics package consumes tracking and synchronized ball observations and provides:

- collective tactical structure: pass networks, block geometry, compactness, width, line heights and post-loss response;
- predictive models: xG bootstrap/model fitting, auditable xA, and confidence-weighted pitch control;
- event semantics: passes, shots, possession changes and extensible football event schemas;
- goalkeeper, duel, set-piece, progression and transition analytics;
- physical workload and data-quality diagnostics;
- player passports and development-oriented analytical signals;
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
6. Production deployments for player data must add appropriate access control, consent, retention and audit mechanisms.

## Development status

The current development line is the **Vision → Football Intelligence** stack. Version labels (V24, V25 and later) describe the evolution of this software layer, while the V21 vision benchmark remains a separate compatibility foundation.

See `centella_analytics/README.md` for the analytics module contract and `docs/PROJECT_BOUNDARIES.md` for the repository separation rules.

## Validation

GitHub Actions runs the analytics regression suite on this branch, covering the existing V24 core plus the event-inference and V25 bridge tests.
