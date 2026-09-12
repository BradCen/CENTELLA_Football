# CENTELLA Football V31 — Extended Intelligence

V31 adds a deterministic, auditable layer on top of the V24–V30 stack. It consumes synchronized player/ball tracking plus the existing event timeline and does not introduce a second tracking implementation.

## Included signals

- 6×5 pitch-zone occupation and per-player spatial footprints;
- transparent territorial-value prior based on longitudinal advancement and lateral centrality;
- ball progression, net advancement and peak observed forward speed;
- local numerical superiority/disadvantage around the ball;
- rest-defence proxy: players behind the ball while the team is observed in possession context;
- defensive-line geometry proxy and line span;
- ball-side defensive proximity as a pressure-proximity signal;
- chronological event timeline for report/UI layers.

## Provenance

The module is explicitly marked as non-learned and ground-truth independent. These metrics are observations or transparent priors, not claims about intent, tactical causality, or an offside-law decision.

The territorial-value signal is intentionally not named xT/OBV because it is not trained on event-outcome data. Production xG/xA claims remain governed by the existing labelled-data requirements.

## Product boundary

V31 strengthens the analytics substrate. The remaining production work is to connect the V62 vision output directly to the V25 bridge, event inference, V24–V31 report generation, and a coach/player-facing interface, then validate the complete video-to-report path on labelled match footage.
