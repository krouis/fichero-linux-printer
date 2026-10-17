# fichero-linux-printer

Print to the AiYin D11s/FICHERO USB label printer from ordinary Linux applications.

[![Tests](https://github.com/krouis/fichero-linux-printer/actions/workflows/tests.yml/badge.svg)](https://github.com/krouis/fichero-linux-printer/actions/workflows/tests.yml)

Experimental adapter for Ubuntu 24.04's distribution CUPS 2.x. It adds a separate
`FICHERO_USB` queue usable through Ubuntu Settings, ordinary application print
dialogs, `lp`, and `lpstat`. It does not change the default printer, the old D11s
queue, other printers, Snap CUPS, or the USB firmware. This is a legacy PPD-based
integration for CUPS 2.x, not an IPP-over-USB or future CUPS 3 driver.

The device is USB Printer Class protocol 2, and requires the D11s raster command
stream; generic PDF/PostScript/HP drivers cannot drive it directly. Applications
send their normal jobs to CUPS, which converts them to PDF, applies layout and
software copies, then hands them to the `fichero` backend. Ghostscript renders
112 x 240 pixels at 203 DPI. The backend crops the 8-dot side margins to the
96-dot printhead and prints through the existing paced USB library. Only
14 x 30 mm gap-separated labels are supported.

## Install the release package

The first release supports **Ubuntu 24.04, amd64 (x86-64), system CUPS 2.x,
and 14 x 30 mm gap labels**. It is not a Snap CUPS, ARM, or CUPS 3 package.
Python libraries are bundled privately; no Git, uv, pip, or source checkout is
needed. `apt` installs the required system printing libraries.

Download the `.deb` and `SHA256SUMS` from
[Releases](https://github.com/krouis/fichero-linux-printer/releases/latest), then:

```sh
sha256sum -c SHA256SUMS
sudo apt install ./fichero-linux-printer_0.1.0-1_amd64.deb
```

Installation automatically configures one connected, powered-on D11s when CUPS
is running. If it was disconnected, connect it and run:

```sh
sudo fichero-printer-setup
# Select explicitly when more than one printer is connected:
sudo fichero-printer-setup --serial YOUR_USB_SERIAL
```

Setup creates `FICHERO_USB`; it never changes the default printer or overwrites
a queue pointing at another device. Existing queue options and a paused state
are preserved on upgrades. If CUPS was stopped during installation, start the
system CUPS service and run setup afterward. Setup does not print a test label.
USB permissions are scoped to `09c5:0200`, with access for CUPS group `lp` and
active-seat users. Avoid simultaneous direct CLI and CUPS access.

### Migrating the prototype/source installation

The package refuses to overwrite an unmanaged `/usr/lib/cups/backend/fichero`.
If you used our earlier source installer, save any desired queue settings, clear
or cancel pending FICHERO jobs, and remove only that prototype before installing
the `.deb`:

```sh
sudo lpadmin -h /run/cups/cups.sock -x FICHERO_USB
sudo rm /usr/lib/cups/backend/fichero /usr/share/ppd/custom/FICHERO-D11s.ppd \
  /etc/udev/rules.d/71-fichero-cups.rules
sudo rm -r /opt/fichero-cups
sudo udevadm control --reload-rules
```

This leaves other queues and the optional desktop `70-fichero-usb.rules` intact.
The installed prototype is not automatically modified by building a package.

### Install from source (development)

```sh
sudo apt install cups cups-client cups-filters ghostscript libusb-1.0-0
git clone https://github.com/krouis/fichero-linux-printer.git
cd fichero-linux-printer
sh scripts/prepare.sh /tmp/fichero-cups-install
sudo sh /tmp/fichero-cups-install/install.sh YOUR_USB_SERIAL
```

The source path additionally requires uv and Python 3.12. Build as the normal
user; the privileged step uses only the prepared bundle. Source installs live
under `/opt/fichero-cups`; Debian packages use `/usr/lib/fichero-linux-printer`.

## Print

Select **FICHERO D11s USB** / **FICHERO_USB** in the application's print dialog.
Choose **14 x 30 mm**, single-sided grayscale, and landscape for a horizontal
30 x 14 mm design. The printable width is approximately 12 mm because the head
has 96 dots. Start with one page and one copy. A normal A4 test page will be tiny
or cropped; use a document designed for the label size.

```sh
lpstat -h /run/cups/cups.sock -p FICHERO_USB -v
lp -h /run/cups/cups.sock -d FICHERO_USB label.pdf
lp -h /run/cups/cups.sock -d FICHERO_USB -n 2 -o FicheroDensity=1 label.pdf
lpstat -h /run/cups/cups.sock -o FICHERO_USB
```

Jobs are limited to 32 MiB, 100 labels including copies, and a copies argument of
1–20. Standard CUPS filters apply page selection, orientation and copy expansion.
Failed USB transfers stop the queue rather than automatically replaying the job.
Inspect the label, cancel or release the held job as appropriate, and resume
with `cupsenable FICHERO_USB`. CUPS “completed” means the data was transferred,
not that paper sensors or physical completion were verified; USB queries remain
unsupported. Keep distribution and Snap queues distinct when troubleshooting.

## Validate without printing

```sh
cupstestppd -v resources/FICHERO-D11s.ppd
uv sync --locked --group test
uv run --no-sync python -m pytest -q
cupsfilter -p resources/FICHERO-D11s.ppd -e -m printer/fichero \
  -i application/pdf -o PageSize=14x30mm label.pdf > processed.pdf
```

The automated CUPS/Ghostscript integration test runs when those tools are
installed and otherwise skips; all other backend tests use mocks and temporary
files, never hardware. Hardware validation: Ubuntu 24.04, D11s firmware 2.4.9, 14 x 30 mm gap labels;
a PDF submitted through the normal CUPS queue printed correctly. Firmware is
not restricted in software. Other distributions and label sizes are unverified.

## Upgrade or remove the Debian package

```sh
sudo apt install ./fichero-linux-printer_NEW-VERSION_amd64.deb
sudo apt remove fichero-linux-printer
# Or remove all package state:
sudo apt purge fichero-linux-printer
```

Removal deletes only the queue whose URI still matches the package's ownership
record. A queue reassigned to a different printer is preserved. Other printers
and their defaults are unchanged. Keep CUPS running during removal so the queue
can be deleted; if it was stopped, remove any leftover `FICHERO_USB` queue later
with `sudo lpadmin -x FICHERO_USB`. Removing the package does not remove a separate
prototype installation under `/opt`.

## Build and publish

Build on Ubuntu 24.04 amd64 with uv, system Python 3.12, and `dpkg-deb`:

```sh
sh scripts/build-deb.sh
sh scripts/test-deb.sh dist/*.deb
```

The second command uses a disposable Ubuntu Docker container, never the host
print server. It checks install, genuine version upgrade, PDF rendering, remove,
purge, reinstall, unmanaged-install conflicts, and preservation of another queue
and its default. Network access is disconnected before package installation;
maintainer scripts never download dependencies. The ordinary backend unit tests
use mocked USB devices. No lifecycle test needs printer hardware.

The **Debian package and release** workflow builds/tests every push to `main`
and pull request, saving the `.deb` and checksums as an Actions artifact. To
publish, update the version in `pyproject.toml` and `RELEASE_NOTES.md`, merge the
change, and push a matching `vX.Y.Z` tag. The tag workflow verifies the version,
repeats the checks, and publishes the tested artifacts to GitHub Releases.
No separate switch is needed to enable Releases.

References: [CUPS filter/backend programming](https://openprinting.github.io/cups/doc/api-filter.html),
[CUPS PPD extensions](https://openprinting.github.io/cups/doc/spec-ppd.html).


## Architecture and dependency

The [fichero-printer](https://github.com/0xMH/fichero-printer) project owns the
printer protocol, image encoding, and USB/Bluetooth transports. This repository
owns the Linux print adapter, PPD, permissions, and installation lifecycle; it
does not copy or fork the printer protocol. The adapter calls the core library's
existing USB print pipeline, currently via `fichero.cli.do_print`.

Until upstream publishes a release containing USB support, the dependency is
pinned to commit `7948e5867600c152034e03c99ced51ea8ef41de7` of the
[krouis fork](https://github.com/krouis/fichero-printer). `uv.lock` records the
resolved dependencies. Updating this pin should be explicit and tested. The
current dependency also installs the core library's Bluetooth dependencies even
though this adapter uses USB only. The source preparation/package build downloads dependencies; the privileged
install step operates entirely on bundled files. System dependencies are
installed by apt.

## Roadmap

- Broader distribution testing and additional verified label sizes.
- Evaluate a PAPPL-based Printer Application to expose the device over IPP and
  support CUPS 3, rather than relying on legacy PPD drivers indefinitely.

## License and attribution

MIT. Built on the MIT-licensed fichero-printer project by 0xMH and contributors.
The USB transport and Python CI were contributed separately in
[upstream PR #24](https://github.com/0xMH/fichero-printer/pull/24).
