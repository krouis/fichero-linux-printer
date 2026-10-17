#!/bin/sh
# Destructive lifecycle tests: only run inside the disposable test container.
set -eu
[ -f /.dockerenv ] || { echo 'Refusing to test package lifecycle on the host' >&2; exit 1; }
server=/run/cups/cups.sock
lpadmin -h "$server" -p KEEP_ME -E -v socket://127.0.0.1:9 -m raw
lpadmin -h "$server" -d KEEP_ME
dpkg -i /tmp/package.deb
fichero-printer-setup --serial EXAMPLE123
lpoptions -h "$server" -p FICHERO_USB -l | grep -q '14x30mm'
test -f /var/lib/fichero-linux-printer/queue-uri
cupstestppd -q /usr/share/ppd/custom/FICHERO-D11s.ppd
# A paused queue and its density choice must survive a genuine package upgrade.
cupsdisable -h "$server" FICHERO_USB
lpadmin -h "$server" -p FICHERO_USB -o FicheroDensity=1
dpkg-deb -R /tmp/package.deb /tmp/upgrade
sed -i '/^Version:/s/$/+test1/' /tmp/upgrade/DEBIAN/control
dpkg-deb --root-owner-group --build /tmp/upgrade /tmp/upgrade.deb
dpkg -i /tmp/upgrade.deb
lpstat -h "$server" -p FICHERO_USB | grep -q disabled
lpoptions -h "$server" -p FICHERO_USB -l | grep -q 'FicheroDensity.*\*1'
lpstat -h "$server" -d | grep -q KEEP_ME
# Exercise the installed backend and renderer as CUPS user lp, offline.
runuser -u lp -- /usr/lib/cups/backend/fichero
runuser -u lp -- /usr/lib/fichero-linux-printer/app/bin/python -I -B - <<'PY'
from pathlib import Path
import tempfile
from PIL import Image
from fichero_linux_printer.backend import render_pdf, printhead_image
with tempfile.TemporaryDirectory() as name:
    root = Path(name)
    Image.new('RGB', (112, 240), 'white').save(root/'label.pdf', resolution=203)
    pages = render_pdf(root/'label.pdf', root)
    assert len(pages) == 1
    assert printhead_image(pages[0]).size == (96, 240)
PY
# Normal remove/purge must clean only the owned queue and package files.
dpkg --remove fichero-linux-printer
if lpstat -h "$server" -p FICHERO_USB >/dev/null 2>&1; then exit 1; fi
lpstat -h "$server" -p KEEP_ME
lpstat -h "$server" -d | grep -q KEEP_ME
test ! -e /usr/lib/cups/backend/fichero
test ! -e /usr/lib/fichero-linux-printer
dpkg --purge fichero-linux-printer
test ! -e /var/lib/fichero-linux-printer
# Refuse to overwrite an unmanaged source install; its contents must survive.
printf 'manual-install\n' > /usr/lib/cups/backend/fichero
if dpkg -i /tmp/package.deb; then echo 'Unmanaged backend was overwritten' >&2; exit 1; fi
grep -qx manual-install /usr/lib/cups/backend/fichero
rm /usr/lib/cups/backend/fichero
dpkg --purge fichero-linux-printer
# Clean reinstall and purge are supported too.
dpkg -i /tmp/package.deb
fichero-printer-setup --serial EXAMPLE123
dpkg --purge fichero-linux-printer
lpstat -h "$server" -p KEEP_ME
printf '\nPackage install, offline upgrade/render, remove, purge, conflict protection, and reinstall: PASS\n'
