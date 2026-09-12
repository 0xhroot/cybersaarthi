#!/usr/bin/env bash
# LAN discovery: advertise the Docker-hosted CyberSaarthi backend over mDNS/DNS-SD
# so the Android Field Agent's LanDiscoveryScreen (NSD, _cybersaarthi._tcp) can find it.
#
#   ./scripts/mdns_advertise.sh [PORT] [SERVICE_NAME]
#
# Defaults: PORT=8000, SERVICE_NAME=CyberSaarthi
#
# Requires one of:
#   * avahi-publish  (host installation; recommended on Debian/Ubuntu)
#   * python3 with the `zeroconf` package (used as a fallback)
#
# mDNS is link-local UDP (5353): it cannot be routed through an isolated docker
# network. Run this on the host or in a container attached to host networking
# (see the `discovery` profile in docker-compose.yml). Gate entries online for
# your firewall but DO NOT forward UDP 5353 across subnets — LAN discovery is
# meant to stay private to the local network segment.

set -euo pipefail

PORT="${1:-8000}"
NAME="${2:-CyberSaarthi}"
TYPE="_cybersaarthi._tcp"

if [ "$PORT" != "8000" ]; then
  echo "mdns_advertise: publishing $NAME on $TYPE:$PORT"
else
  echo "mdns_advertise: publishing $NAME on $TYPE:$PORT (default)"
fi
echo "mdns_advertise: press Ctrl-C to stop. Verify with: avahi-browse -rt $TYPE"

if command -v avahi-publish >/dev/null 2>&1; then
  exec avahi-publish -s "$NAME" "$TYPE" "$PORT" service=cybersaarthi version=0.1.0 proto=v1
elif python3 -c "import zeroconf" >/dev/null 2>&1; then
  exec python3 - "$NAME" "$TYPE" "$PORT" service=cybersaarthi version=0.1.0 proto=v1 <<'PY'
import sys
from zeroconf import ServiceInfo, Zeroconf

name, stype, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
full_type = stype if stype.endswith(".local.") else stype.rstrip(".") + ".local."
txt = {kv.split("=", 1)[0].encode(): kv.split("=", 1)[1].encode() for kv in sys.argv[4:]}
info = ServiceInfo(full_type, f"{name}.{full_type}", addresses=[b"\x00\x00\x00\x00"], port=port, properties=txt)
zc = Zeroconf()
zc.register_service(info)
try:
    import time
    while True:
        time.sleep(1)
finally:
    zc.close()
PY
else
  echo "mdns_advertise: could not find avahi-publish or the python 'zeroconf' package." >&2
  echo "Install one of them, e.g.:  sudo apt-get install avahi-daemon" >&2
  exit 127
fi