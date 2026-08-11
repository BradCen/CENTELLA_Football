from __future__ import annotations

import os
import sys


def main() -> None:
    # The shipping Windows shell is HTML/CSS/JS hosted by WebView2. Pygame is
    # retained only as a recovery path while the new launcher is rolled out.
    if os.name == "nt" and os.environ.get("CENTELLA_FORCE_PYGAME") != "1":
        try:
            from .web_frontend import main as web_main

            web_main()
            return
        except Exception as exc:
            print(f"CENTELLA web frontend unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
            print("Falling back to the legacy recovery frontend.", file=sys.stderr)

    from .release_frontend import main as fallback_main

    fallback_main()


if __name__ == "__main__":
    main()
