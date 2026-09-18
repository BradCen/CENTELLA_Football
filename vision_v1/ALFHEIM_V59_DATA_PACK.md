# CENTELLA Football — Alfheim V59 native data contract

This benchmark intentionally does **not** bundle the Alfheim dataset. The official dataset license permits non-commercial research and forbids attempts to re-identify players or create individual player/club performance profiles.

## Required native files

For each of cameras 0, 1 and 2, obtain the exact three-second native H.264 segments from the official Alfheim First Half directory:

- `0059_2013-11-03 18:01:23.251115000.h264`
- `0060_2013-11-03 18:01:26.252555000.h264`
- `0061_2013-11-03 18:01:29.253030000.h264`

Ground truth:

- `2013-11-03_tromso_stromsgodset_first.csv`

Expected local layout:

```text
alfheim_v59/
├── cam0/
│   ├── 0059_2013-11-03 18:01:23.251115000.h264
│   ├── 0060_2013-11-03 18:01:26.252555000.h264
│   └── 0061_2013-11-03 18:01:29.253030000.h264
├── cam1/
│   ├── 0059_2013-11-03 18:01:23.251115000.h264
│   ├── 0060_2013-11-03 18:01:26.252555000.h264
│   └── 0061_2013-11-03 18:01:29.253030000.h264
├── cam2/
│   ├── 0059_2013-11-03 18:01:23.251115000.h264
│   ├── 0060_2013-11-03 18:01:26.252555000.h264
│   └── 0061_2013-11-03 18:01:29.253030000.h264
└── zxy/
    └── 2013-11-03_tromso_stromsgodset_first.csv
```

The official Simula index confirms segments 0059–0061 in camera 2 and their timestamps/sizes. The other native camera directories use the same segment numbering/timing convention.

## Reproducible execution

From the repository root:

```bash
python vision_v1/run_alfheim_v59_local.py \
  --data /path/to/alfheim_v59 \
  --out output/alfheim_v59_local
```

This creates joined MP4s only as temporary derived inputs, runs the strict V59 anonymous track-set consensus, and then runs the image-only geometry audit for cameras 0–2.

## Benchmark integrity

V59 constructs anonymous trajectories before loading truth for evaluation. The truth file is therefore never available to candidate generation, path construction, consensus selection, or identity inference.

The separate geometry audit is also image-only: it uses the fixed seed homography and visible pitch markings, not the ZXY file.

Do not copy the numeric checksum values of files from third-party mirrors into the benchmark unless byte-level equivalence with the official native files has been independently established.
