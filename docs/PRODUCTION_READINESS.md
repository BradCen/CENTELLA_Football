# CENTELLA Football — Production Readiness / Hardware Benchmark

## Purpose

This benchmark converts the current validated software path into an engineering baseline for a real field installation.

It measures:

1. Vision / V62 on the real Alfheim OOS multi-camera video.
2. Analytics V24–V32 on the real V62 tracking output.
3. 90-minute Analytics capacity using a synthetic volume stress test built by repeating the real tracking fixture.

The 90-minute stress test is a capacity measurement only. Repeated observations are not treated as a real football match.

## Current validated reference workload

The present OOS vision benchmark uses three fixed camera streams, decodes the native video at 25 FPS, and samples the tracker at 8 FPS. Ground truth is kept out of inference and used only for post-hoc evaluation.

The benchmark records:

- host CPU count and RAM;
- vision wall time and peak memory;
- Analytics wall time, throughput and real-time factor;
- 90-minute Analytics capacity wall time and real-time factor;
- native camera bitrate, resolution and storage load;
- projected processing time for a 90-minute match.

## Requirements baseline

### Analytics workstation

Pilot floor: 6 physical CPU cores, 16 GB RAM, 500 GB SSD.

Recommended: 8+ physical CPU cores, 32 GB RAM, 1 TB NVMe SSD.

The current V24–V32 Analytics engine does not require a GPU.

### Vision node

Pilot baseline: 8 physical CPU cores, 32 GB RAM, 1 TB NVMe for system/runtime plus dedicated video storage.

For multi-camera field deployment, use a discrete NVIDIA GPU with at least 8 GB VRAM as the provisional baseline. The exact GPU SKU is intentionally not hard-coded yet: it must be locked by running this same benchmark on candidate hardware and comparing full 90-minute turnaround.

### Cameras and network

The current validated reference is 3 fixed cameras with known geometry and synchronized timing. The final camera count must be decided by site coverage/overlap, not by an arbitrary number.

The benchmark derives aggregate camera ingest bandwidth and 90-minute storage from the native source media instead of assuming a generic bitrate.

Formula used:

90-minute storage (GB) ≈ aggregate camera bitrate (Mbps) × 67.5

Add headroom for filesystem overhead, metadata, retained matches and other software assets.

### Internet

The core processing path is intended to run locally once the runtime/models are installed.

Internet is useful for software updates, remote dashboard access, backups and telemetry, but continuous cloud access is not required by the current local analytics path.

## What is locked vs provisional

Locked by the benchmark: the workload, data path, software integrity checks, 3-camera OOS reference, V62 real-video execution, V24–V32 execution and 90-minute Analytics volume test.

Still to be locked on deployment hardware: exact CPU SKU, exact GPU SKU, final camera model/resolution/bitrate, storage retention capacity, PoE/network topology and measured full-match vision turnaround.

The commercial field installation should use this benchmark as the acceptance test: run it on the proposed PC/GPU before purchasing the hardware.

## Acceptance targets

The report exposes two Analytics targets:

- 1.0× real-time factor: approximately 90 minutes to process a 90-minute match.
- 2.0× real-time factor: approximately 45 minutes.

The vision stage is reported separately because detector/inference cost dominates and must be validated on the final GPU.

## Output

GitHub Actions artifact: `centella-production-readiness`.

It contains host inventory, measured command timings, the V62 report, Analytics benchmark, media inventory and the assembled `production_readiness.json`.
