#!/bin/sh
# Install the prebuilt, relocatable bundle. No network commands run as root.
set -eu
if [ "$(id -u)" -ne 0 ]; then
    echo 'Run with sudo: sudo sh /tmp/fichero-cups-install/install.sh USB_SERIAL' >&2
    exit 1
fi
serial=${1:?USB serial number is required}
case "$serial" in
    ''|*[!A-Za-z0-9]*) echo 'USB serial must be alphanumeric' >&2; exit 1 ;;
esac
bundle=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
server=/run/cups/cups.sock
[ -S "$server" ] || { echo 'System CUPS socket is missing' >&2; exit 1; }
[ -x /usr/bin/gs ] || { echo 'Install ghostscript first' >&2; exit 1; }
[ -x "$bundle/app/bin/python" ] || { echo 'Prepared app environment is missing' >&2; exit 1; }
if [ -e /opt/fichero-cups ] || lpstat -h "$server" -p FICHERO_USB >/dev/null 2>&1; then
    echo 'FICHERO_USB or /opt/fichero-cups already exists; refusing to overwrite it' >&2
    exit 1
fi
cupstestppd -q "$bundle/FICHERO-D11s.ppd"
install -d -m 755 /opt/fichero-cups
cp -a "$bundle/app" /opt/fichero-cups/app
chown -hR root:root /opt/fichero-cups
chmod -R go-w /opt/fichero-cups
install -o root -g root -m 755 "$bundle/backend" /usr/lib/cups/backend/fichero
install -d -m 755 /usr/share/ppd/custom
install -o root -g root -m 644 "$bundle/FICHERO-D11s.ppd" /usr/share/ppd/custom/FICHERO-D11s.ppd
install -o root -g root -m 644 "$bundle/71-fichero-cups.rules" /etc/udev/rules.d/71-fichero-cups.rules
udevadm control --reload-rules
udevadm trigger --action=change --subsystem-match=usb --attr-match=idVendor=09c5 --attr-match=idProduct=0200
udevadm settle --timeout=10
lpadmin -h "$server" -p FICHERO_USB -E \
    -v "fichero://usb?serial=$serial" \
    -P /usr/share/ppd/custom/FICHERO-D11s.ppd \
    -D 'FICHERO D11s USB' -L '14 x 30 mm gap labels' \
    -o printer-is-shared=false -o printer-error-policy=stop-printer \
    -o job-sheets-default=none,none -o PageSize=14x30mm
lpstat -h "$server" -p FICHERO_USB -v
printf '\nInstalled FICHERO_USB. Existing printers and system default are unchanged.\n'
