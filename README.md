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
  → V28 performance → V29 coach → V30 platform → V31 extended
  → V32 player evolution/similarity/contribution
      ↓
reports / APIs / future coach & player interfaces
```

### `vision_v1/` — Vision layer

The vision layer contains the V21 foundation plus later OOS-tested refinements for calibration, camera synchronization, multi-camera fusion, player/ball observations, causal track-set selection and benchmark tooling.

### `centella_analytics/` — Intelligence layer

The stack provides collective tactical structure, predictive models, football event semantics, goalkeeper/duel/set-piece analytics, workload and data-quality diagnostics, player intelligence, tactical intelligence, performance intelligence, coach intelligence, unified platform orchestration, extended spatial indicators and player evolution/similarity/on-off-ball observation.

Detailed contracts are documented in `centella_analytics/README.md`, `docs/V26_PLAYER_INTELLIGENCE.md`, `docs/V30_PLATFORM.md` and `docs/V31_EXTENDED_INTELLIGENCE.md`.

## Data integrity

Missing observations are never silently converted to zero. Model-derived values remain estimates. Candidate event inference is not labelled event truth. Workload outputs are performance/review signals, not medical diagnoses. Production player deployments require appropriate access control, consent, retention and audit controls.

## Validation

GitHub Actions runs the analytics regression suite and dedicated Alfheim OOS benchmarks. The V60/V61/V62 final tracking benchmark completed successfully with ground-truth-blind inference and an integrity guard. The analytics production path still requires labelled real-match validation, production video-ingestion hardening, production model calibration, and a validated coach/player UI before it should be described as a finished commercial deployment.
