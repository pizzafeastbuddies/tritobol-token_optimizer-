"""Start the local Tritobol web app:  python -m tritobol_app [--port 5000] [--no-browser]"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser

HOST = "127.0.0.1"  # fixed on purpose: the app is local-only


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        return probe.connect_ex((HOST, port)) != 0


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="tritobol-app",
        description="Local Tritobol web interface",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="preferred port (next free port is used if busy)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="do not open a browser window",
    )
    args = parser.parse_args(argv)

    try:
        from .server import create_app
        app = create_app()
    except ImportError as exc:
        print(
            f"tritobol-app: missing dependency: {exc}\n"
            "Install with: pip install -r requirements-app.txt",
            file=sys.stderr,
        )
        return 1

    port = next(
        (p for p in range(args.port, args.port + 20) if _port_free(p)),
        None,
    )

    if port is None:
        print(
            f"tritobol-app: no free port in {args.port}-{args.port + 19}.",
            file=sys.stderr,
        )
        return 1

    url = f"http://{HOST}:{port}/"

    print(
        f"Tritobol is running at {url}\n"
        "Processing stays on this computer. Press Ctrl+C to stop.",
        flush=True,
    )

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    import logging

    class _DropDevWarning(logging.Filter):
        # Flask's development-server notice is noise for a local single-user tool.
        def filter(self, record):
            return "development server" not in record.getMessage()

    logging.getLogger("werkzeug").addFilter(_DropDevWarning())

    try:
        import flask.cli
        flask.cli.show_server_banner = lambda *a, **k: None

        app.run(
            host=HOST,
            port=port,
            threaded=True,
            use_reloader=False,
            debug=False,
        )

    except OSError as exc:
        print(
            f"tritobol-app: could not start the server: {exc}",
            file=sys.stderr,
        )
        return 1

    except KeyboardInterrupt:
        print("\nStopped.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())