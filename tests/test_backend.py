"""CUPS backend tests without printer access; render integration when installed."""

import io
from pathlib import Path
import shutil
import subprocess
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from fichero import PrinterError, PrinterNotFound
from fichero_linux_printer.backend import (
    BACKEND_HOLD,
    BACKEND_STOP,
    main,
    parse_density,
    parse_uri,
    print_pages,
    printhead_image,
    render_pdf,
    spool_pdf,
)


@pytest.mark.parametrize(
    "uri",
    [
        "usb:///D11s",
        "fichero://usb",
        "fichero://usb?serial=x&serial=y",
        "fichero://usb?serial=x&file=/etc/passwd",
        "fichero://usb?serial=../x",
    ],
)
def test_reject_invalid_uri(uri):
    with pytest.raises(ValueError):
        parse_uri(uri)


def test_serial_and_density():
    assert parse_uri("fichero://usb?serial=EXAMPLE123") == "EXAMPLE123"
    assert parse_density("PageSize=14x30mm FicheroDensity=1") == 1
    with pytest.raises(ValueError):
        parse_density("FicheroDensity=3")


def test_spool_rejects_non_pdf_and_oversize(tmp_path):
    with pytest.raises(ValueError, match="expects a PDF"):
        spool_pdf(io.BytesIO(b"not pdf"), tmp_path / "bad.pdf")
    with (
        patch("fichero_linux_printer.backend.MAX_JOB_BYTES", 8),
        pytest.raises(ValueError, match="32 MiB"),
    ):
        spool_pdf(io.BytesIO(b"%PDF-1.4 more"), tmp_path / "big.pdf")


def test_crop_preserves_scale(tmp_path):
    page = Image.new("L", (112, 240), 255)
    page.putpixel((8, 100), 0)
    page.putpixel((103, 100), 0)
    path = tmp_path / "page.png"
    page.save(path)
    image = printhead_image(path)
    assert image.size == (96, 240)
    assert image.getpixel((0, 100)) == image.getpixel((95, 100)) == 0
    assert image.getpixel((1, 100)) == 255


@pytest.mark.parametrize("from_file", [False, True])
def test_backend_copies_are_not_duplicated(tmp_path, monkeypatch, from_file):
    pdf = tmp_path / "input.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    monkeypatch.setenv("DEVICE_URI", "fichero://usb?serial=EXAMPLE")
    args = ["fichero", "1", "user", "label", "2", "FicheroDensity=1"]
    if from_file:
        args.append(str(pdf))
    with (
        patch(
            "fichero_linux_printer.backend.sys.stdin",
            buffer=io.BytesIO(pdf.read_bytes()),
        ),
        patch(
            "fichero_linux_printer.backend.render_pdf",
            return_value=[tmp_path / "page.png"],
        ),
        patch(
            "fichero_linux_printer.backend._print_with_signals", new_callable=AsyncMock
        ) as send,
    ):
        assert main(args) == 0
    assert send.call_args.args[1:] == ("EXAMPLE", 1, 2 if from_file else 1)


@pytest.mark.parametrize(
    "error,code",
    [
        (PrinterNotFound("offline"), BACKEND_HOLD),
        (PrinterError("partial write"), BACKEND_STOP),
    ],
)
def test_backend_never_automatically_retries_uncertain_print(
    tmp_path, monkeypatch, error, code
):
    pdf = tmp_path / "input.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    monkeypatch.setenv("DEVICE_URI", "fichero://usb?serial=EXAMPLE")
    with (
        patch(
            "fichero_linux_printer.backend.render_pdf",
            return_value=[tmp_path / "page.png"],
        ),
        patch(
            "fichero_linux_printer.backend._print_with_signals",
            new_callable=AsyncMock,
            side_effect=error,
        ),
    ):
        assert main(["fichero", "1", "user", "label", "1", "", str(pdf)]) == code


@pytest.mark.asyncio
async def test_pages_use_existing_usb_pipeline(tmp_path):
    path = tmp_path / "page.png"
    Image.new("L", (112, 240), 255).save(path)
    transport = AsyncMock()
    with (
        patch(
            "fichero_linux_printer.backend.connect", return_value=transport
        ) as connect_usb,
        patch(
            "fichero_linux_printer.backend.do_print", new_callable=AsyncMock
        ) as print_label,
    ):
        await print_pages([path], "EXAMPLE", 2, 1)
    connect_usb.assert_called_once_with(usb=True, serial="EXAMPLE")
    assert print_label.call_args.args[1].size == (96, 240)
    assert print_label.call_args.kwargs == dict(density=2, dither=False)
    transport.__aexit__.assert_awaited_once()


@pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("cupsfilter", "gs")),
    reason="CUPS/Ghostscript not installed",
)
def test_real_cups_pipeline_generates_copies(tmp_path):
    source = tmp_path / "label.pdf"
    Image.new("RGB", (112, 240), "white").save(source, resolution=203)
    ppd = Path(__file__).resolve().parents[1] / "resources/FICHERO-D11s.ppd"
    result = subprocess.run(
        [
            "cupsfilter",
            "-p",
            str(ppd),
            "-e",
            "-m",
            "printer/fichero",
            "-i",
            "application/pdf",
            "-n",
            "2",
            "-o",
            "PageSize=14x30mm",
            str(source),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    processed = tmp_path / "processed.pdf"
    processed.write_bytes(result.stdout)
    pages = render_pdf(processed, tmp_path)
    assert len(pages) == 2
    assert all(printhead_image(page).size == (96, 240) for page in pages)
