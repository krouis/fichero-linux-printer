"""Configure only the package's CUPS queue, without changing global defaults."""

import argparse
import asyncio
import os
from pathlib import Path
import subprocess
import sys

from fichero.printer import PrinterError
from fichero.usb import discover_usb
from fichero_linux_printer.backend import parse_uri

SERVER = "/run/cups/cups.sock"
QUEUE = "FICHERO_USB"
MARKER = Path("/var/lib/fichero-linux-printer/queue-uri")
PPD = "/usr/share/ppd/custom/FICHERO-D11s.ppd"


def command(*args):
    return subprocess.run(
        args,
        text=True,
        capture_output=True,
        env={**os.environ, "LC_ALL": "C"},
        check=False,
    )


def existing_uri():
    result = command("lpstat", "-h", SERVER, "-v", QUEUE)
    if result.returncode:
        return None
    prefix = f"device for {QUEUE}: "
    if not result.stdout.startswith(prefix):
        raise ValueError("Could not identify the existing FICHERO_USB queue")
    return result.stdout[len(prefix) :].strip()


def configure(serial):
    uri = f"fichero://usb?serial={serial}"
    parse_uri(uri)
    current = existing_uri()
    if current is not None and current != uri:
        raise ValueError(
            "FICHERO_USB already refers to another device; no changes made"
        )
    if current is None:
        result = command(
            "lpadmin",
            "-h",
            SERVER,
            "-p",
            QUEUE,
            "-E",
            "-v",
            uri,
            "-P",
            PPD,
            "-D",
            "FICHERO D11s USB",
            "-L",
            "14 x 30 mm gap labels",
            "-o",
            "printer-is-shared=false",
            "-o",
            "printer-error-policy=stop-printer",
            "-o",
            "job-sheets-default=none,none",
            "-o",
            "PageSize=14x30mm",
        )
        if result.returncode:
            raise ValueError(result.stderr.strip() or "CUPS queue creation failed")
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(uri + "\n")
    print(
        "FICHERO_USB is configured. Existing defaults and queue settings are preserved."
    )


def remove_managed():
    if not MARKER.exists():
        return
    if existing_uri() == MARKER.read_text().strip():
        result = command("lpadmin", "-h", SERVER, "-x", QUEUE)
        if result.returncode:
            raise ValueError(result.stderr.strip() or "Could not remove FICHERO_USB")
    MARKER.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Configure the FICHERO USB label printer"
    )
    parser.add_argument(
        "--serial", help="USB serial (allows configuration while disconnected)"
    )
    parser.add_argument(
        "--auto", action="store_true", help="Noninteractive installation-time discovery"
    )
    parser.add_argument("--remove-managed", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        parser.error("Run with sudo to configure the system print queue")
    if not Path(SERVER).exists():
        print(
            "CUPS is not running. Start system CUPS, then run sudo fichero-printer-setup."
        )
        return 0 if args.auto or args.remove_managed else 1
    try:
        if args.remove_managed:
            remove_managed()
            return 0
        serial = args.serial
        if serial is None:
            devices = asyncio.run(discover_usb())
            if len(devices) != 1 or not devices[0]["serial"]:
                print(
                    "Connect one powered-on D11s, then run sudo fichero-printer-setup. "
                    "For multiple printers use --serial USB_SERIAL."
                )
                return 0 if args.auto else 1
            serial = devices[0]["serial"]
        configure(serial)
        return 0
    except (PrinterError, ValueError, OSError) as exc:
        print(f"FICHERO setup: {exc}", file=sys.stderr)
        return 0 if args.auto else 1


if __name__ == "__main__":
    sys.exit(main())
