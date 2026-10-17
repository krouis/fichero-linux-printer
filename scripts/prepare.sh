#!/bin/sh
# Run as the desktop user, from any directory. Requires uv and system Python 3.12.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/.." && pwd)
destination=${1:-/tmp/fichero-cups-install}
case "$destination" in /*) ;; *) echo 'Use an absolute destination path' >&2; exit 1 ;; esac
[ ! -e "$destination" ] || { echo 'Destination already exists; use a new directory' >&2; exit 1; }
mkdir -p "$destination"
cp "$here/install.sh" "$repo/resources/backend" "$repo/resources/FICHERO-D11s.ppd" "$repo/resources/71-fichero-cups.rules" "$destination/"
cd "$repo"
uv build --wheel --out-dir "$destination/wheels"
uv export --frozen --no-default-groups --no-emit-project \
    --format requirements-txt --output-file "$destination/requirements.txt" >/dev/null
uv venv --python /usr/bin/python3 --relocatable "$destination/app"
uv pip install --python "$destination/app/bin/python" --link-mode copy -r "$destination/requirements.txt"
for wheel in "$destination"/wheels/*.whl; do
    uv pip install --python "$destination/app/bin/python" --link-mode copy --no-deps "$wheel"
done
printf '\nPrepared %s\nInstall with: sudo sh %s/install.sh USB_SERIAL\n' "$destination" "$destination"
