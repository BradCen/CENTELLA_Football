# CENTELLA Football — third-party UI foundations

This frontend intentionally uses permissively licensed open-source components where they replace infrastructure we should not reinvent.

## Integrated in the shipping React UI

### Norigin Spatial Navigation

- Repository: `NoriginMedia/Norigin-Spatial-Navigation`
- Package: `@noriginmedia/norigin-spatial-navigation` 3.3.0
- License: MIT
- Role in CENTELLA: directional focus engine for keyboard/remote/gamepad-style navigation. CENTELLA's Gamepad API adapter translates D-pad/stick movement into Norigin's `navigateByDirection` instead of maintaining our previous linear focus manager.

### react-soccer-lineup

- Repository: `giustini/react-soccer-lineup`
- Package: `react-soccer-lineup` 1.0.0-beta.12
- License: MIT
- Role in CENTELLA: tactical pitch renderer in Game Plan. CENTELLA adapts its own players/formations/team palette to the library's squad model.

## Studied, not copied

### OpenFootManager

- Repository: `openfootmanager/openfootmanager`
- License: GPL-3.0
- CENTELLA does **not** copy or link its source into the proprietary product UI. It may be studied as an architectural/product-flow reference for future career/management systems only.

## Product rule

Permissive dependencies can provide infrastructure, but CENTELLA's visual identity, football data model, Python bridge and GRF integration remain project-owned. GPL code is not imported into the proprietary application unless the licensing strategy is intentionally changed.
