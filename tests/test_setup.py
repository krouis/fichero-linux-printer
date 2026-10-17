"""Queue management must preserve unrelated queues and operator choices."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from fichero_linux_printer import setup


def result(code=0, text=""):
    return SimpleNamespace(returncode=code, stdout=text, stderr="")


def test_creates_only_its_queue_and_records_ownership(tmp_path, monkeypatch):
    marker = tmp_path / "queue-uri"
    monkeypatch.setattr(setup, "MARKER", marker)
    with patch.object(setup, "command", side_effect=[result(1), result()]) as run:
        setup.configure("EXAMPLE")
    args = run.call_args.args
    assert args[:5] == ("lpadmin", "-h", setup.SERVER, "-p", "FICHERO_USB")
    assert "-d" not in args  # Never set a global default.
    assert "printer-is-shared=false" in args
    assert marker.read_text().strip() == "fichero://usb?serial=EXAMPLE"


def test_existing_queue_preserves_pause_and_options(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "MARKER", tmp_path / "queue-uri")
    with patch.object(
        setup,
        "command",
        return_value=result(
            text="device for FICHERO_USB: fichero://usb?serial=EXAMPLE\n"
        ),
    ) as run:
        setup.configure("EXAMPLE")
    assert run.call_count == 1  # No lpadmin -E, no resetting PPD/settings.


def test_name_collision_never_overwrites_other_printer(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "MARKER", tmp_path / "queue-uri")
    with patch.object(
        setup,
        "command",
        return_value=result(text="device for FICHERO_USB: socket://other\n"),
    ) as run:
        with pytest.raises(ValueError, match="another device"):
            setup.configure("EXAMPLE")
    assert run.call_count == 1
    assert not setup.MARKER.exists()


@pytest.mark.parametrize("matches", [True, False])
def test_removes_only_matching_managed_queue(tmp_path, monkeypatch, matches):
    marker = tmp_path / "queue-uri"
    marker.write_text("fichero://usb?serial=EXAMPLE\n")
    monkeypatch.setattr(setup, "MARKER", marker)
    current = "fichero://usb?serial=EXAMPLE" if matches else "socket://replacement"
    with patch.object(
        setup,
        "command",
        side_effect=[result(text=f"device for FICHERO_USB: {current}\n"), result()],
    ) as run:
        setup.remove_managed()
    assert run.call_count == (2 if matches else 1)
    assert not marker.exists()
    if matches:
        assert run.call_args.args == ("lpadmin", "-h", setup.SERVER, "-x", setup.QUEUE)


def test_no_marker_means_no_queue_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "MARKER", tmp_path / "missing")
    with patch.object(setup, "command") as run:
        setup.remove_managed()
    run.assert_not_called()


@pytest.mark.parametrize(
    "devices,expected",
    [
        ([], None),
        ([{"serial": "EXAMPLE"}], "EXAMPLE"),
        ([{"serial": "FIRST"}, {"serial": "SECOND"}], None),
    ],
)
def test_install_discovery_never_guesses_between_devices(
    tmp_path, monkeypatch, devices, expected
):
    from unittest.mock import AsyncMock

    server = tmp_path / "cups.sock"
    server.touch()
    monkeypatch.setattr(setup, "SERVER", str(server))
    monkeypatch.setattr(setup.os, "geteuid", lambda: 0)
    with (
        patch.object(setup, "discover_usb", AsyncMock(return_value=devices)),
        patch.object(setup, "configure") as configure,
    ):
        assert setup.main(["--auto"]) == 0
    if expected:
        configure.assert_called_once_with(expected)
    else:
        configure.assert_not_called()
