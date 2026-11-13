"""Command line entry point for the WinGetty importer.

Examples
--------
Import a drop folder directly on the WinGetty host (same environment
variables / database as the running app):

    python -m wingetty_import /srv/winget-drops --local

Import through the REST API from any machine:

    python -m wingetty_import /srv/winget-drops \
        --server https://wingetty.internal --username svc-import --password ...

Watch a folder and import new drops every 10 minutes:

    python -m wingetty_import /srv/winget-drops --local --watch 600
"""

import argparse
import getpass
import os
import sys
import time

from .importer import ApiBackend, LocalBackend, print_summary, run_import


def build_parser():
    parser = argparse.ArgumentParser(
        prog="wingetty_import",
        description=(
            "Import installers downloaded with 'winget download' (installer "
            "+ generated YAML manifest) into WinGetty without manual UI work."
        ),
    )
    parser.add_argument(
        "drop_dir",
        help="Folder containing the downloaded installers and their YAML "
        "manifests (scanned recursively).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--local",
        action="store_true",
        help="Write directly to the database. Run on the WinGetty host with "
        "the same WINGETTY_* environment as the app.",
    )
    mode.add_argument(
        "--server",
        default=os.environ.get("WINGETTY_SERVER"),
        help="WinGetty base URL for API mode, e.g. https://wingetty.internal. "
        "Defaults to the WINGETTY_SERVER environment variable.",
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("WINGETTY_USERNAME"),
        help="API mode: user with add:package/version/installer permissions. "
        "Defaults to WINGETTY_USERNAME.",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("WINGETTY_PASSWORD"),
        help="API mode: password. Defaults to WINGETTY_PASSWORD; prompted "
        "interactively if neither is set.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="API mode: skip TLS verification (only for testing).",
    )
    parser.add_argument(
        "--watch",
        type=int,
        metavar="SECONDS",
        help="Re-scan and import every SECONDS (for artifact stores synced "
        "into the drop folder).",
    )
    parser.add_argument(
        "--report",
        help="Write the JSON import report here. Default: "
        "<drop_dir>/wingetty-import-report.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without changing anything.",
    )
    return parser


def make_backend(args):
    if args.server:
        username = args.username
        if not username:
            raise SystemExit("--server mode needs --username (or WINGETTY_USERNAME)")
        password = args.password
        if not password:
            password = getpass.getpass(f"Password for {username}@{args.server}: ")
        return ApiBackend(
            args.server, username, password, verify_tls=not args.insecure
        )
    return LocalBackend()


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not os.path.isdir(args.drop_dir):
        raise SystemExit(f"Drop folder does not exist: {args.drop_dir}")

    backend = make_backend(args)
    had_errors = False
    try:
        while True:
            report_path = args.report or os.path.join(
                args.drop_dir, "wingetty-import-report.json"
            )
            report = run_import(
                args.drop_dir,
                backend,
                dry_run=args.dry_run,
                report_path=report_path,
            )
            print_summary(report)
            print(f"Report written to {report_path}")
            had_errors = report["summary"]["errors"] > 0

            if not args.watch:
                break
            time.sleep(args.watch)
    except KeyboardInterrupt:
        pass
    finally:
        close = getattr(backend, "close", None)
        if close:
            close()

    return 1 if had_errors else 0


if __name__ == "__main__":
    sys.exit(main())
