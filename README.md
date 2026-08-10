# CENTELLA Football

**Beta Experience v2 — original football-game shell on top of the open Gameplay Football / Google Research Football simulation.**

CENTELLA Football is being built as its own product, not as a PES/FIFA skin. The reference point is what the best football games made *feel* good — fast navigation, readable sports presentation, a direct path to the pitch and football-first controls — while CENTELLA keeps its own identity, data and code.

> **North star:** immediate to command, physical after the command.

Responsiveness must not mean pinball football. Realism must not mean animation lock, delayed passes or arbitrary mistakes.

## What Beta Experience v2 contains

The branch `agent/centella-first-impression` now includes a controller-first product layer above the inherited simulation:

- cinematic CENTELLA startup and **Press any button** flow;
- 1920×1080 logical UI projected responsively to any window size/aspect ratio;
- keyboard, mouse and controller navigation from the first screen;
- persistent controller bindings shared by the menu and the GRF match player;
- **Patada Inicial / Kick Off** connected to the native 11v11 engine;
- **local co-op** wiring for two controllers;
- **Training** connected to existing GRF academy scenarios;
- selectable teams, duration, difficulty and presentation presets;
- persistent local data foundations for **Liga Máster 2.0**, created players, competitions, Street/Futsal presets and set pieces;
- editable team identity data;
- competition creator and set-piece editor;
- video/performance, accessibility and controller pages;
- CENTELLA LAB runtime diagnostics;
- automatic Windows install/repair flow for the native engine;
- a smoke-test workflow that compiles/imports the shell and renders key screens headlessly on every push.

The menu map deliberately exposes the intended product instead of four placeholder cards: Patada Inicial, local co-op, Training, leagues, cups/tournaments, Kings-style special-format architecture, Futsal, Street, penalties, Liga Máster, DT/President co-op, Modo Leyenda, Journey presentation, scouting, club world, press/locker-room architecture, Ranked, friendlies, Clubs, Street Clubs, community cups, Edit Mode, player creator, competition creator, set-piece lab, controls, video, accessibility and Workshop.

Some of those are **product/UI/data foundations rather than finished simulation/network systems**. The shell labels them honestly; it does not fake online matchmaking or claim a career simulation is complete when its deeper core still has to be connected.

## Windows quick start

From your existing source folder:

```powershell
cd F:\CENTELLA_Football\CENTELLA_FOOTBALL_SOURCE
git fetch origin
git switch agent/centella-first-impression
git pull origin agent/centella-first-impression
.\scripts\RUN_BETA.ps1
```

Or double-click:

```text
RUN_CENTELLA_BETA.bat
```

You can still use:

```powershell
python -m centella
```

The new shell intentionally **does not import GRF on startup**. That means a broken/missing native engine can no longer prevent the UI from opening.

## If CENTELLA LAB says `REPAIR REQUIRED`

Run:

```powershell
.\scripts\INSTALL_BETA.ps1
```

The script:

1. looks for the existing `..\TOOLCHAIN\Python310` / `python310` runtime first;
2. requires the Python 3.10 x64 ABI used by this GRF Windows build;
3. reuses an existing vcpkg when possible, or creates an isolated one under `TOOLCHAIN`;
4. installs the shell/runtime Python dependencies, including `absl-py`;
5. builds the native Gameplay Football module;
6. applies the known Boost Atomic compatibility alias only if that specific historical build problem appears;
7. verifies `gfootball_engine` can really be imported before reporting success.

This addresses the failure mode where the shell was started with Python 3.11 and later crashed on `No module named 'absl'` or on an incompatible native engine.

## Controller layout and remapping

Open **CUSTOMIZE → MANDO Y CONTROLES**. The initial SDL-style layout is familiar to modern football games:

- A / Cross — short pass / pressure;
- B / Circle — shot / team pressure;
- X / Square — high pass / sliding tackle;
- Y / Triangle — native GRF long-pass action / goalkeeper rush;
- LB / L1 — switch player;
- RB / R1 — dribble/control action;
- left stick — movement;
- right trigger axis — sprint;
- Menu / Options — shell menu binding.

Button remaps are stored in the user settings directory and the native `gfootball/env/players/gamepad.py` reads the same mapping.

## Native match path

The inherited research entry point remains available:

```powershell
python -m gfootball.play_game --action_set=full
```

CENTELLA's launcher adds configurable native render width and keeps the render target at 16:9. There is also an **experimental low-latency** toggle that reduces `physics_steps_per_frame`; this is an experiment, not a claim that the inherited research-oriented 100 ms human-input limitation is solved. The upstream README explicitly notes that human players share the agent interface and normally report one action per 100 ms.

## Gameplay direction

Read [`docs/GAMEPLAY_DNA.md`](docs/GAMEPLAY_DNA.md). It converts observable lessons from PES/FIFA-era football games into original CENTELLA rules rather than copying proprietary code or assets.

Core principles:

- input intent is sacred;
- the ball remains physically independent;
- animation serves the requested football action;
- mistakes require an understandable football reason;
- defense is primarily manual;
- players must feel individual;
- difficulty improves intelligence rather than cheating;
- tactics and match state should produce emergent stories.

Current response targets live in [`centella/gameplay_profile.py`](centella/gameplay_profile.py).

## Product vision recovered into the branch

The longer-term design represented by the shell includes:

- **Liga Máster 2.0:** DT, President or full-control roles; eventual DT+President co-op; market/scouting/finances/stadium/locker room;
- **Modo Leyenda:** player career plus emergent narrative rather than a rigid scripted campaign;
- **Futsal / Street:** its own ball/rules/tactical profile, mixed teams and configurable barrio surfaces/rules;
- **custom leagues, tournaments and rules**;
- **set-piece creator**;
- **Edit Mode / Workshop** for user-created or properly licensed content;
- **CENTELLA SR integration point** through render scaling rather than coupling the upscaler to simulation logic;
- future tactical AI training and IA Light systems kept separate from the render/input loop.

## Visual identity

The shell uses CENTELLA's technology identity:

- Jet Black `#020203`
- Obsidian `#171717`
- Sapphire `#2359AA`
- Pure White `#FFFFFF`
- Urbanist when installed on the host OS, with normal system sans-serif fallbacks

The visual structure takes inspiration from the *clarity and pacing* of premium sports-game menus, while the actual composition, staging, graphics and branding are original CENTELLA work. See [`docs/FIRST_IMPRESSION_UX.md`](docs/FIRST_IMPRESSION_UX.md).

## Architecture

```text
centella/
  beta_frontend.py              Beta Experience v2 screens and flows
  ui.py                         responsive renderer / original sports staging
  controller.py                 controller-first input and remapping
  settings.py                   persistent user settings
  content.py                    fictional beta teams / user data
  modes.py                      complete product-mode map
  runtime.py                    isolated native-runtime diagnostics/launcher
  brand.py                      CENTELLA design tokens
  gameplay_profile.py           measurable gameplay-feel targets

gfootball/                     Google Research Football Python environment
third_party/gfootball_engine/  Gameplay Football C++ engine
scripts/                        Windows launch / install / repair
.github/workflows/              automated smoke/build validation
docs/                           product, gameplay and clean-room specs
```

## Next core-engine milestones

1. Measure input-to-visible-response latency on Windows and remove the inherited research cadence from local human play properly.
2. Build an intent-first pass/movement/shot pipeline and reduce unexplained unforced errors.
3. Rework manual defending, jockeying, switching and maximum-difficulty AI without hidden boosts.
4. Replace inherited match presentation with native CENTELLA team-select, broadcast intro, pause/tactics and HUD layers.
5. Add persistent career simulation services, true Futsal scenarios and deterministic network synchronization.
6. Connect the graphics modernization / CENTELLA SR path only after the football loop is stable and measurable.

## Legal / provenance

CENTELLA Football may study **observable behavior and general UI/UX patterns** from other football games, but proprietary PES/FIFA code, game assets, faces, stadiums, screenshots or random web images are not automatically free to redistribute commercially. See [`docs/CLEAN_ROOM_REFERENCE_POLICY.md`](docs/CLEAN_ROOM_REFERENCE_POLICY.md).

The Google Research Football project code is distributed under Apache 2.0; existing copyright/license notices remain intact. Every external asset added for a commercial build needs known provenance and appropriate rights.

---

**CENTELLA Football — the football should respond to the player, not fight the controller.**
