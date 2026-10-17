"""Local Ubuntu CUPS 2.x PDF backend for 14 x 30 mm D11s gap labels.

CUPS handles application formats, page selection, layout and software copies.
This backend renders its final PDF, crops the physical 96-dot printhead area,
then uses the existing paced USB print pipeline. It never sends PDF to USB.
"""

import asyncio
import contextlib
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, quote, urlsplit

from PIL import Image

from fichero.cli import do_print
from fichero.printer import PrinterError, PrinterNotFound, connect
from fichero.usb import discover_usb

MAX_PAGES = 100
MAX_COPIES = 20
MAX_JOB_BYTES = 32 * 1024 * 1024
# CUPS backend status codes, from cups/backend.h.
BACKEND_FAILED = 1
BACKEND_HOLD = 3
BACKEND_STOP = 4


def parse_uri(uri: str) -> str:
    parts = urlsplit(uri)
    values = parse_qs(parts.query)
    serials = values.get("serial", [])
    if (
        parts.scheme != "fichero"
        or parts.netloc != "usb"
        or parts.path
        or parts.fragment
        or set(values) != {"serial"}
        or len(serials) != 1
    ):
        raise ValueError("Expected fichero://usb?serial=USB_SERIAL")
    serial = serials[0]
    if not serial.isascii() or not serial.isalnum() or len(serial) > 128:
        raise ValueError("Invalid USB serial selector")
    return serial


def parse_density(options: str) -> int:
    values = dict(
        option.split("=", 1) for option in shlex.split(options) if "=" in option
    )
    density = int(values.get("FicheroDensity", "2"))
    if density not in (0, 1, 2):
        raise ValueError("FicheroDensity must be 0, 1, or 2")
    return density


def spool_pdf(source, target: Path) -> None:
    with target.open("xb") as output:
        copied = 0
        while chunk := source.read(65536):
            copied += len(chunk)
            if copied > MAX_JOB_BYTES:
                raise ValueError("Print job exceeds 32 MiB")
            output.write(chunk)
    with target.open("rb") as saved:
        if not saved.read(1024).lstrip().startswith(b"%PDF-"):
            raise ValueError("CUPS adapter expects a PDF after the normal CUPS filters")


def render_pdf(pdf: Path, directory: Path) -> list[Path]:
    gs = shutil.which("gs")
    if not gs:
        raise ValueError("Ghostscript is required (sudo apt install ghostscript)")
    subprocess.run(
        [
            gs,
            "-dSAFER",
            "-dBATCH",
            "-dNOPAUSE",
            "-dQUIET",
            "-dNOPROMPT",
            "-sDEVICE=pnggray",
            "-r203",
            "-dFIXEDMEDIA",
            "-dPDFFitPage",
            "-dAutoRotatePages=/None",
            "-dDEVICEWIDTHPOINTS=39.685039",
            "-dDEVICEHEIGHTPOINTS=85.039370",
            f"-dLastPage={MAX_PAGES + 1}",
            f"-sOutputFile={directory}/page-%04d.png",
            "-f",
            str(pdf),
        ],
        check=True,
        timeout=60,
        stdout=sys.stderr,
    )
    pages = sorted(directory.glob("page-*.png"))
    if not pages or len(pages) > MAX_PAGES:
        raise ValueError(f"Job must contain 1 to {MAX_PAGES} labels")
    return pages


def printhead_image(path: Path) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("L")
    # 14 x 30 mm at 203 dpi is 112 x 240 dots. Do not shrink to 96 dots:
    # crop the unprintable 1 mm margins instead, preserving physical geometry.
    if image.size != (112, 240):
        raise ValueError(f"Unexpected label raster size {image.size}; expected 112x240")
    return image.crop((8, 0, 104, 240))


async def print_pages(
    pages: list[Path], serial: str, density: int, copies: int
) -> None:
    async with connect(usb=True, serial=serial) as printer:
        for copy in range(copies):
            for number, page in enumerate(pages, 1):
                # Library/CLI progress belongs on stderr, not the backend's stdout.
                with contextlib.redirect_stdout(sys.stderr):
                    await do_print(
                        printer, printhead_image(page), density=density, dither=False
                    )
                print(f"PAGE: {copy * len(pages) + number} 1", file=sys.stderr)
    print(
        "INFO: USB transfers completed; physical print completion is unverified.",
        file=sys.stderr,
    )


async def discover() -> None:
    for device in await discover_usb():
        serial = device["serial"]
        if serial:
            uri = "fichero://usb?serial=" + quote(serial, safe="")
            print(
                f'direct {uri} "AiYin D11s" "FICHERO D11s USB ({serial})" '
                '"MFG:AiYin;MDL:D11s;CLS:PRINTER;"'
            )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv if argv is None else argv
    if len(args) == 1:
        try:
            asyncio.run(discover())
            return 0
        except PrinterError as exc:
            print(f"DEBUG: {exc}", file=sys.stderr)
            return 0  # Other CUPS backends must still be discoverable.
    if len(args) not in (6, 7):
        print(
            "ERROR: Expected job-id user title copies options [file]", file=sys.stderr
        )
        return BACKEND_FAILED
    try:
        serial = parse_uri(os.environ.get("DEVICE_URI", ""))
        density = parse_density(args[5])
        # With stdin, upstream pdftopdf generates software copies (PPD requests
        # cupsManualCopies). Repeat only when CUPS passes an unfiltered file.
        copies = int(args[4]) if len(args) == 7 else 1
        if not 1 <= int(args[4]) <= MAX_COPIES:
            raise ValueError(f"Copies must be between 1 and {MAX_COPIES}")
        with tempfile.TemporaryDirectory(prefix="fichero-cups-") as name:
            directory = Path(name)
            pdf = directory / "job.pdf"
            if len(args) == 7:
                with open(args[6], "rb") as source:
                    spool_pdf(source, pdf)
            else:
                spool_pdf(sys.stdin.buffer, pdf)
            pages = render_pdf(pdf, directory)
            if len(pages) * copies > MAX_PAGES:
                raise ValueError(f"Job exceeds {MAX_PAGES} labels including copies")
            asyncio.run(_print_with_signals(pages, serial, density, copies))
        return 0
    except PrinterNotFound as exc:
        print(
            f"ERROR: {exc}. Connect/power on the printer, then resume this job.",
            file=sys.stderr,
        )
        return BACKEND_HOLD
    except PrinterError as exc:
        print(
            f"ERROR: {exc}. Inspect the label before resuming; automatic retry is disabled.",
            file=sys.stderr,
        )
        return BACKEND_STOP
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return BACKEND_HOLD
    except asyncio.CancelledError:
        print(
            "INFO: Print cancelled; any partially transferred label may still print.",
            file=sys.stderr,
        )
        return 0


async def _print_with_signals(*args) -> None:
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, task.cancel)
    try:
        await print_pages(*args)
    finally:
        loop.remove_signal_handler(signal.SIGTERM)


if __name__ == "__main__":
    sys.exit(main())
