#!/bin/sh
# Build on Ubuntu 24.04 amd64 as an ordinary user. No sudo or network at install time.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/.." && pwd)
cd "$repo"
. /etc/os-release
[ "$ID" = ubuntu ] && [ "$VERSION_ID" = 24.04 ] || { echo 'Build on Ubuntu 24.04' >&2; exit 1; }
arch=$(dpkg --print-architecture)
[ "$arch" = amd64 ] || { echo 'Only amd64 packages are validated for this release' >&2; exit 1; }
/usr/bin/python3 -c 'import sys; assert sys.version_info[:2] == (3, 12)'
version=$(/usr/bin/python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')
case "$version" in *[!0-9.]*) echo 'Use a numeric release version' >&2; exit 1 ;; esac
out=${1:-"$repo/dist"}
mkdir -p "$out"
out=$(CDPATH= cd -- "$out" && pwd)
work=$(mktemp -d /tmp/fichero-deb.XXXXXX)
trap 'rm -rf "$work"' EXIT HUP INT TERM
sh scripts/prepare.sh "$work/bundle"
root="$work/root"
install -d "$root/DEBIAN" "$root/usr/lib/fichero-linux-printer" \
    "$root/usr/lib/cups/backend" "$root/usr/sbin" "$root/usr/share/ppd/custom" \
    "$root/usr/lib/udev/rules.d" "$root/usr/share/doc/fichero-linux-printer" \
    "$root/var/lib/fichero-linux-printer"
cp -a "$work/bundle/app" "$root/usr/lib/fichero-linux-printer/app"
# Bytecode is generated at runtime if allowed; build-directory paths aren't shipped.
find "$root" -type d -name __pycache__ -prune -exec rm -r '{}' +
sed -e 's@/opt/fichero-cups/app@/usr/lib/fichero-linux-printer/app@' -e 's/python -I /python -I -B /' resources/backend > "$root/usr/lib/cups/backend/fichero"
printf '%s\n' '#!/bin/sh' 'exec /usr/lib/fichero-linux-printer/app/bin/python -I -B -m fichero_linux_printer.setup "$@"' > "$root/usr/sbin/fichero-printer-setup"
chmod 755 "$root/usr/lib/cups/backend/fichero" "$root/usr/sbin/fichero-printer-setup"
install -m 644 resources/FICHERO-D11s.ppd "$root/usr/share/ppd/custom/FICHERO-D11s.ppd"
install -m 644 resources/71-fichero-cups.rules "$root/usr/lib/udev/rules.d/71-fichero-cups.rules"
install -m 644 LICENSE "$root/usr/share/doc/fichero-linux-printer/copyright"
install -m 644 README.md "$root/usr/share/doc/fichero-linux-printer/README.md"
cp "$work/bundle/requirements.txt" "$root/usr/share/doc/fichero-linux-printer/bundled-requirements.txt"
for script in preinst postinst prerm postrm; do
    install -m 755 "packaging/debian/$script" "$root/DEBIAN/$script"
done
size=$(du -sk "$root/usr" | cut -f1)
cat > "$root/DEBIAN/control" <<CONTROL
Package: fichero-linux-printer
Version: $version-1
Architecture: $arch
Maintainer: krouis <krouis@users.noreply.github.com>
Section: utils
Priority: optional
Installed-Size: $size
Depends: python3 (>= 3.12), python3 (<< 3.13), cups (>= 2.4), cups (<< 3.0), cups-client, cups-filters, ghostscript, libusb-1.0-0, udev, libc6 (>= 2.35), libgcc-s1, libstdc++6
Homepage: https://github.com/krouis/fichero-linux-printer
Description: USB printing for AiYin D11s/FICHERO label printers
 Ubuntu 24.04 amd64 CUPS adapter for 14 x 30 mm gap labels.
 Bundles its Python libraries; no Git, uv, pip, or network downloads are
 needed by the package's maintainer scripts. Use fichero-printer-setup
 after connecting the printer. Does not change the default printer.
CONTROL
chmod -R go-w "$root"
dpkg-deb --root-owner-group --build "$root" "$out/fichero-linux-printer_${version}-1_${arch}.deb"
(cd "$out" && sha256sum "fichero-linux-printer_${version}-1_${arch}.deb" > SHA256SUMS)
