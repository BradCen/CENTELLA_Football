# CENTELLA Football

**Alpha 0.1 — a modern, responsive football game built on the open Gameplay Football / Google Research Football foundation.**

CENTELLA Football is not a PES, FIFA or eFootball mod. The long-term goal is an original commercial football platform with immediate controls, believable physicality, deep offline modes, fair manual-first defending, scalable graphics, online play and community-created content.

> **North star:** immediate to command, physical after the command.

Responsiveness must not mean pinball football. Realism must not mean animation lock, delayed passes or arbitrary mistakes.

## First product layer

The repository now contains an early CENTELLA shell above the inherited simulation engine:

- cinematic CENTELLA startup and **Press any button** flow;
- controller/keyboard/mouse-ready home interface;
- **Quick Match** connected to the existing 11v11 engine;
- **Training** connected to the existing pass-and-shoot academy scenario;
- honest placeholders for Career, Online, Club and Settings instead of fake finished features;
- CENTELLA brand tokens and official logo artwork;
- measurable gameplay-response targets;
- design and clean-room reference documentation.

Launch the CENTELLA shell after installing the project dependencies:

```bash
python -m centella
```

The inherited research-game entry point remains available:

```bash
python -m gfootball.play_game --action_set=full
```

## Why this foundation is valuable

Google Research Football is an RL environment built on the open-source Gameplay Football game. This repository includes the C++ simulation source for the ball, players, human controller, AI, match rules, animation system and rendering pipeline rather than treating football as a black box.

That gives CENTELLA something unusually useful: we can change the actual football behavior and automatically test it with agents. The inherited human-play path does, however, have a known research-oriented limitation: human actions are reported to the environment at a coarse 100 ms cadence. Removing that bottleneck for local play is one of the first core-engine milestones.

## Gameplay direction

Read [`docs/GAMEPLAY_DNA.md`](docs/GAMEPLAY_DNA.md). It converts lessons from PES 6/2013/2018/2019/2021 and FIFA 14/17/19/22 into original CENTELLA rules instead of copying another game's implementation.

The short version:

- input intent is sacred;
- the ball remains physically independent;
- animation serves the requested football action;
- mistakes require an understandable football reason;
- defense is primarily manual;
- players must feel individual;
- difficulty improves intelligence rather than cheating;
- tactics and match state should produce emergent stories.

Current response targets live in [`centella/gameplay_profile.py`](centella/gameplay_profile.py).

## First-impression UX

The product shell is intentionally modern rather than retro/arcade. It uses CENTELLA's technology identity:

- Jet Black `#020203`
- Obsidian Black `#171717`
- Sapphire Blue `#2359AA`
- Pure White `#FFFFFF`
- Urbanist when available on the host OS, with system sans-serif fallbacks

The startup uses restrained stadium light, perspective pitch geometry and CENTELLA motion rather than pixels, CRT effects or copied FIFA screens. See [`docs/FIRST_IMPRESSION_UX.md`](docs/FIRST_IMPRESSION_UX.md).

## Architecture

```text
centella/                       Product/UI layer
  frontend.py                   Splash, home, navigation, game launch
  brand.py                      CENTELLA design tokens
  gameplay_profile.py           Measurable feel targets
  assets/                       Approved CENTELLA artwork

gfootball/                     Google Research Football Python environment
third_party/gfootball_engine/  Gameplay Football C++ engine
  src/onthepitch/ball.cpp       Ball simulation
  src/onthepitch/match.cpp      Match simulation
  src/onthepitch/player/        Player/controller/animation behavior

docs/                           Product, gameplay and clean-room specs
```

## Development priorities

1. Instrument input-to-visible-response latency, then decouple local human input from the RL environment cadence.
2. Build an intent-first pass/movement/shot pipeline and tune unexplained unforced errors out of elite players.
3. Rework manual defending, jockeying, player switching and maximum-difficulty AI without hidden physical boosts.
4. Modernize locomotion/IK/animation blending while retaining a low-cost rendering path for integrated graphics.
5. Replace inherited research presentation with native CENTELLA team select, match intro, pause/tactics and settings screens.
6. Add persistent Career/Player Journey data, true futsal rules, online architecture and a controlled community workshop.

## Legal / provenance

CENTELLA Football studies **observable football-game behavior**, not proprietary PES/FIFA implementation code or assets. See [`docs/CLEAN_ROOM_REFERENCE_POLICY.md`](docs/CLEAN_ROOM_REFERENCE_POLICY.md).

The Google Research Football project code is distributed under Apache 2.0; the included original Gameplay Football engine also carries its upstream public-domain/Unlicense notice. Existing copyright, license and attribution notices must remain intact. Every new external asset must have recorded provenance before a commercial release.

---

**CENTELLA Football — the football should respond to the player, not fight the controller.**
