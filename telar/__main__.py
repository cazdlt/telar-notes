"""CLI entrypoint for running Telar Notes with Uvicorn."""

from __future__ import annotations

import argparse
import pathlib
import threading
import time

import uvicorn

from telar.app import create_app
from telar.config import CONFIG_DIR, TelarConfig


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and serve Telar Notes over Uvicorn."""
    parser = argparse.ArgumentParser(description="Telar Notes server")
    parser.add_argument("--vault", required=True, help="Path to vault directory")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)"
    )
    parser.add_argument("--port", type=int, default=7731)
    parser.add_argument(
        "--idle-timeout",
        type=int,
        default=900,
        help="Auto-shutdown after N seconds with no requests (0 = never)",
    )
    args = parser.parse_args(argv)

    vault_path = str(pathlib.Path(args.vault).expanduser().resolve())
    cfg = TelarConfig()
    session_path = str(CONFIG_DIR / ".session")
    activity = {"t": time.time()}
    app = create_app(
        vault_path=vault_path,
        config=cfg,
        session_path=session_path,
        activity=activity,
    )

    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        access_log=False,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    print(f"Telar Notes server running at http://{args.host}:{args.port}", flush=True)

    # Auto-shutdown after inactivity so forgotten background processes don't linger.
    if args.idle_timeout > 0:

        def _watchdog() -> None:
            while not server.should_exit:
                time.sleep(30)
                if time.time() - activity["t"] > args.idle_timeout:
                    server.should_exit = True
                    return

        threading.Thread(target=_watchdog, daemon=True).start()

    server.run()


if __name__ == "__main__":
    main()
