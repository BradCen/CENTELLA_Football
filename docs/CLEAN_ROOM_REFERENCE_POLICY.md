# Clean-room reference policy

CENTELLA Football can study the **observable behavior** of football games, but its commercial codebase must remain original and legally clean.

## Allowed design-reference workflow

1. Record or watch ordinary gameplay that the team is entitled to access.
2. Measure behavior: input-to-response timing, player acceleration, pass speed, camera framing, menu flow, defensive spacing, etc.
3. Write a neutral specification that describes the behavior without copying implementation details.
4. Implement that specification independently in CENTELLA's open engine.
5. Use original or properly licensed art, audio, animation, trademarks and data.
6. Keep provenance for third-party code and assets.

## Do not import into CENTELLA

- PES/eFootball executable code or decompiled code;
- `dt18` or other proprietary data files;
- Konami/EA textures, faces, stadiums, commentary, music or animation data;
- club/player/competition trademarks without appropriate rights;
- copied UI screens, logos or proprietary fonts/assets.

## Why Football Life is different

Football Life is a modification/continuation platform around the PES 2021 executable. SmokePatch documents gameplay work in terms of EXE functions plus the external `dt18` gameplay parameter bin. That is useful evidence that PES behavior is tunable, but it is **not** evidence that the PES source code is public or reusable in a new commercial game.

CENTELLA has the better long-term commercial route: own its implementation. The Gameplay Football core included in this repository is open/public-domain at engine level, and Google Research Football wraps it under Apache-2.0-compatible project licensing. Preserve notices and audit every added asset before distribution.

## Practical reverse-engineering boundary

For a commercial release, get jurisdiction-specific legal review before any binary reverse engineering. The project does not need it to reproduce high-level gameplay qualities. Behavioral measurement plus clean-room implementation is enough for our design goals and avoids coupling CENTELLA to someone else's executable forever.
