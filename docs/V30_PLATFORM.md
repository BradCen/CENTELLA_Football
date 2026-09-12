# V30 — CENTELLA Football Intelligence Platform

V30 is the integration boundary for the V24–V29 stack. It does not replace the individual analytical layers; it composes them into one auditable result.

## End-to-end contract

`V21 fused vision → V25 bridge → V26 player intelligence → V27 tactical interactions → V28 performance → V29 coach intelligence → V30 platform report`

The platform exposes two entry points:

- `analyze_tracking(...)` for synchronized tracking where events are conservatively inferred;
- `analyze_events(...)` when an external event timeline is supplied.

Both preserve provenance in the final report.

## Provenance rule

Tracking-derived event inference is marked as unvalidated. The platform does not silently convert candidate events into ground truth. Validated datasets, labelled clips and trained models can be introduced later without changing the platform boundary.

## Product boundary

V30 produces machine-readable intelligence suitable for future APIs, dashboards, coach workflows and player reports. It is not a game, simulator, medical system or autonomous coaching authority.

## What remains for the production path

The V24–V30 analytical architecture is now present in code. Production validation still requires real multi-camera/ball datasets, event labels, model training, calibration against ground truth, performance benchmarking, and a real video ingestion/deployment layer. Those are validation and productization steps, not reasons to fabricate metrics in the core.
