#!/bin/sh
# A separate disposable Docker container: never installs the package on the host.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/.." && pwd)
deb=$(realpath "${1:?Pass the .deb path}")
container=$(docker create ubuntu:24.04 sleep infinity)
trap 'docker rm -f "$container" >/dev/null' EXIT HUP INT TERM
docker start "$container" >/dev/null
docker cp "$deb" "$container:/tmp/package.deb"
docker cp "$repo/packaging/test-installed.sh" "$container:/tmp/test-installed.sh"
docker exec -e DEBIAN_FRONTEND=noninteractive "$container" sh -c '
    apt-get update -qq
    apt-get install -y --no-install-recommends python3 cups cups-client cups-filters ghostscript libusb-1.0-0 udev libstdc++6
    mkdir -p /run/cups
    /usr/sbin/cupsd
'
# No downloads are possible during install/upgrade/removal or PDF rendering.
docker network disconnect bridge "$container"
docker exec "$container" sh /tmp/test-installed.sh
