First installable release for **Ubuntu 24.04 amd64 (x86-64)**.

Print from normal Linux applications to AiYin D11s/FICHERO USB printers
(`09c5:0200`) using 14 × 30 mm gap-separated labels.

### Install

Download the `.deb` and `SHA256SUMS`, verify the checksum, then run:

```sh
sha256sum -c SHA256SUMS
sudo apt install ./fichero-linux-printer_0.1.0-1_amd64.deb
```

One connected printer is configured automatically. If it was disconnected,
connect/power it on and run `sudo fichero-printer-setup`. Select FICHERO_USB in
the application's print dialog. Git, uv, pip, and a source checkout are not needed.

### Included

- Private, pinned Python runtime dependencies and system dependencies managed by apt.
- Scoped USB permissions, 203 DPI label definition, and an unprivileged CUPS backend.
- Install/upgrade/remove lifecycle support without changing the default printer.
- Tag-triggered automated builds, lifecycle validation, and release checksums.

### Validation and limits

Backend tests use mocks plus the real Ubuntu PDF filter/rendering chain.
Package install, offline upgrade/render, removal/purge, reinstall, and conflict
protection are exercised in a disposable Ubuntu container. The underlying USB
printing path was hardware-verified for text, QR, and captioned QR labels; a PDF
through the prototype CUPS queue also printed correctly.

This package targets distribution CUPS 2.x, not Snap CUPS or CUPS 3. ARM and other
Ubuntu versions are not supported by this build. Physical completion and paper/
cover status are not reported by the USB protocol. Failed writes stop the queue
instead of automatically retrying.

**Prototype users:** the package deliberately refuses to overwrite an unmanaged
source installation. Follow the README migration steps first; existing source
installations are not silently replaced.
