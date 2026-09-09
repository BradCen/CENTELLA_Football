# Project boundaries

## Purpose

CENTELLA Football is organized as a separation between a **vision/perception layer** and a **football-intelligence layer**. The historical football game is archived independently.

## Active software

### `vision_v1/`
Responsible for visual perception and tracking:

- camera calibration and geometry;
- native camera timing and synchronization;
- multi-camera fusion;
- player/ball observations and tracking;
- V21 benchmark and truth-alignment tooling.

V21 is a compatibility foundation. Analytics work must not rewrite its benchmark logic merely to add higher-level football metrics.

### `centella_analytics/`
Responsible for football semantics and intelligence:

- event schemas and event inference;
- possession and transition semantics;
- tactical structure and interactions;
- xG/xA and other model-based measures;
- pitch control;
- goalkeeper, duel and set-piece analysis;
- workload/data-quality metrics;
- player intelligence and future coaching interfaces.

This layer consumes observations; it does not become a second camera-tracking implementation.

### `docs/`
Documents interfaces, validation rules, provenance and architectural decisions.

## Archived software

The historical football game/environment is preserved on:

`archive/football-game`

It is not a dependency of the intelligence stack and must not be reintroduced into the active analytics branch.

## Explicit exclusions for the active intelligence branch

Do not introduce:

- gameplay loops or playable match environments;
- simulator-specific APIs;
- game-engine build systems;
- unrelated reinforcement-learning/gameplay dependencies;
- documentation presenting the repository as a game or simulator.

## Provenance

The active intelligence branch may reference the **internal V21 vision contract** because it consumes those native fused observations. External game/simulator projects are not part of its identity or scientific validation basis.

## Validation principle

A metric is only elevated from analytical estimate to validated football event truth when the underlying observations and labels have an explicit validation path. Tracking-derived candidate events must retain their provenance and uncertainty.
