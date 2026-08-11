# CENTELLA Football — Gameplay DNA v0.1

This document is the feel contract for the project. It is deliberately written as measurable behavior instead of "make it feel like PES/FIFA".

## North star

**Immediate to command, physical after the command.**

CENTELLA Football should react quickly to intent while preserving believable inertia, body orientation, ball momentum and tactical consequences. Responsiveness must not mean pinball speed; realism must not mean animation lock or delayed controls.

## What we learn from the classics — without copying their code/assets

| Reference | Keep | Avoid |
|---|---|---|
| PES 6 | direct inputs, readable dribbling, unpredictable ball, strong 1v1s, long-lived Master League | dated presentation, repetitive commentary, licensing dependence |
| PES 2013 | technical control, manual modifiers, Player ID / individuality, tactical satisfaction | overly complex command barrier, stale modes/presentation |
| FIFA 14 | fast navigation, coherent mode ecosystem, scouting loop, polished match flow | excessive automation |
| FIFA 17 | physicality, collision readability, cinematic world-building, story as motivation | AI run inconsistencies, defense feeling too assisted/physical |
| FIFA 19 | competition atmosphere, responsive attacking, presentation identity, narrative continuity | shallow career refresh, systems that reward one meta |
| PES 2018 | weight + responsiveness, contextual passing, shielding, tactical control | goalkeeper inconsistency, presentation gap |
| PES 2019 | independent-feeling ball, player individuality, contextual animation, lighting/grass, fatigue readability | old UI, commentary, under-evolved Master League |
| PES 2021 | faces, animation blending, ball physics, broadcast-like visuals | sluggish input/animation commitment, avoidable unforced errors |
| FIFA 22 | smooth animation language, strong front-end UX, visual clarity, Volta/futsal variety | defensive automation / difficulty that feels unfair |

## Eight rules of feel

1. **Input intent is sacred.** The game should acknowledge a deliberate move/pass/shot command within one to five rendered frames where physically plausible.
2. **Animation serves simulation.** A pretty animation may never override a valid football decision for hundreds of milliseconds merely to finish its clip.
3. **The ball is an object, not a leash.** First touches, rebounds and passes are physically simulated and can create unscripted situations.
4. **Errors need a reason.** Pressure, weak foot, posture, fatigue, surface, ball speed and player skill may create error. Elite players should not miss simple five-metre passes because of arbitrary RNG.
5. **Defense is mainly manual.** Good positioning, jockey angle, timing and body contact win the ball. AI supports shape; it does not play the tackle for the user.
6. **Players are individuals.** Turning radius, acceleration curve, touch radius, preferred foot, pass technique, balance and signature motion matter more than only overall rating.
7. **Tactics change what a match feels like.** Opponents should not simply receive hidden speed/accuracy boosts on higher difficulty.
8. **Every match can tell a story.** Weather, fatigue, momentum of play, substitutions, score state and tactical adaptation create variety without scripted winners.

## Responsiveness targets

Defined in `centella/gameplay_profile.py`:

- target input sampling: **60 Hz or better**;
- visible input response target: **<= 85 ms** for ordinary movement intent;
- quick pass intent: **~110 ms** target before the action pipeline has committed;
- quick shot intent: **~140 ms** target;
- direction-change commitment: **~70 ms** target before the movement solver begins the new requested arc;
- short action buffer: **~260 ms** so an intended pass is not lost during a recoverable animation.

These are design targets. The inherited Google Research Football human interface currently reports actions at a much coarser cadence, so the first core-engine milestone is to decouple local human input from the reinforcement-learning step cadence.

## Passing

### Goal
PES 6 immediacy + PES 2019 ball behavior + modern contextual animation.

### Rules

- Tapping pass should trigger a fast, low-windup action if body position allows it.
- The animation system chooses *how* the player executes the requested pass; it should not decide *whether* the user requested one.
- A professional under no pressure must reliably execute trivial passes.
- Assistance is a continuum, not an on/off cheat: it may help target selection while preserving user direction and power.
- Backheels, outside-foot passes, stretched contacts and improvised touches are contextual solutions, not random flourishes.
- Receiver selection should evaluate direction, lane, interception risk, teammate movement and user power.

## Dribbling and movement

### Goal
PES 6 directness without skating; FIFA 22 animation fluidity without animation lock.

- Separate **input direction**, **desired body direction**, and **actual velocity**.
- Small stick changes produce micro-adjustments; 180-degree changes invoke braking/planting appropriate to speed.
- Sprint has a real first-touch trade-off.
- Close control reduces touch distance and speed, not responsiveness.
- Players can shield using body orientation and strength without a magnetic two-player animation.
- Signature acceleration and turning characteristics distinguish players.

## Shooting

- Shot result is driven by contact point, body orientation, foot, balance, ball velocity, technique and input.
- Fast shots must still be possible from good preparation; do not add theatrical wind-up solely for visual fidelity.
- Finishing assistance may correct a plausible line, never teleport the ball toward goal.
- The same input should not always produce the same animation/result.

## Defending

### Goal
Fix the two common extremes: FIFA-style automation and frustrating input ambiguity.

- Left stick controls defensive body positioning.
- Jockey is controlled containment, not an invisible tackle radius.
- Standing tackle is an explicit commitment with recovery cost.
- Shoulder contact is contextual and strength/balance based.
- Teammate contain protects a zone and delays; it should not steal automatically at elite accuracy.
- Player switching prioritizes threat + ball trajectory + user direction and previews the next candidate.
- Legendary/maximum difficulty must improve reading, spacing, reaction and tactical adjustment — **not** hidden pace, tackle magnetism or input-reading cheats.

## AI and tactics

CENTELLA should exploit its GRF heritage instead of discarding it. The engine already exists inside an RL-oriented environment, which is unusually useful for automated gameplay testing.

AI layers:

1. role/formation constraints;
2. local football heuristics;
3. match-state strategy;
4. optional learned policy for decisions;
5. deterministic safety rules for laws of football and obvious positioning failures.

Difficulty changes decision horizon, pressure recognition, tactical coordination and risk appetite. It should not simply alter physics or give the CPU impossible technical execution.

## Ball and surface

- Keep ball simulation independent from player locomotion.
- Tune rolling resistance, bounce, spin and air drag by surface/weather profile.
- Wet grass changes roll/skid and footing subtly, not by multiplying random errors.
- Net physics and grass response are presentation layers; they must remain scalable for modest hardware.

## Animation architecture target

Long term, replace clip-first behavior with an intent-first stack:

`input intent -> football action planner -> contact solution -> locomotion/IK -> animation blend -> physics contact`

Use motion matching or a searchable animation database when practical, but preserve a low-cost fallback for integrated graphics. IK should solve feet/ball/body contact corrections instead of requiring an animation for every exact centimeter.

## Modes that protect the core

- Quick Match: shortest path to football.
- Career / Master-style mode: team building, finances, scouting, youth, player aging and deep customization.
- Player Journey: story emerges from performance and choices; cinematic authored chapters can be layered later.
- Futsal: smaller pitch and different tactical rhythm; not a cosmetic 11v11 resize.
- Online: same physics/controls as offline, rollback/prediction designed around football actions.
- Community: user-created teams, kits, competitions and data packages installed from a controlled workshop flow.

## Definition of "fun simulation"

A match passes the bar when a loss makes the player think *"I chose badly / they played better"*, not *"the animation ignored me"* or *"the CPU cheated"*.
