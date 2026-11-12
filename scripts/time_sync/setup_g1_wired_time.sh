#!/usr/bin/env bash
# Run as the desktop user: bash scripts/time_sync/setup_g1_wired_time.sh
# Stop robot control before running: initial clock correction can step time.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
KEY="$ROOT/.local/robot/orin_g1_ed25519"
SSH=(env -u LD_LIBRARY_PATH -u LD_PRELOAD /usr/bin/ssh -i "$KEY"
     -o BatchMode=yes -o ConnectTimeout=8 agi@10.42.0.101)

python3 - <<'PY'
import json, urllib.request
from urllib.error import URLError
try:
    with urllib.request.urlopen('http://127.0.0.1:9002/api/client/status', timeout=4) as r:
        s = json.load(r)['data']
except URLError as e:
    raise SystemExit('Cannot verify client status; start the client UI with control stopped, then retry: '+str(e))
if any(s.get(k) for k in ('control_running', 'control_requested', 'inference_running')):
    raise SystemExit('Stop Control and Infer in the UI before configuring time sync.')
PY
"${SSH[@]}" 'sudo -n /usr/bin/bash -c "true"'
sudo -v
sudo /usr/bin/bash -s <<'HOST'
set -euo pipefail
backup="/var/backups/g1-wired-time-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$backup"
cp -a /etc/systemd/timesyncd.conf "$backup/"
if [[ -d /etc/chrony ]]; then cp -a /etc/chrony "$backup/"; fi
if ! command -v chronyd >/dev/null; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y chrony
fi
cat > /etc/chrony/chrony.conf <<'CONF'
# Desktop is the time authority for the directly connected G1.
pool ntp.ubuntu.com iburst maxsources 4 maxpoll 8
driftfile /var/lib/chrony/chrony.drift
rtcsync
makestep 1.0 3
# Serve the desktop clock even when no Internet source is available.
local stratum 10
allow 10.42.0.101/32
logdir /var/log/chrony
CONF
chronyd -p -f /etc/chrony/chrony.conf >/dev/null
systemctl disable --now systemd-timesyncd.service 2>/dev/null || true
if command -v ufw >/dev/null && LC_ALL=C ufw status | grep -q '^Status: active'; then
    ufw allow in on eno2 from 10.42.0.101 to 10.42.0.102 port 123 proto udp
fi
systemctl enable chrony.service
systemctl restart chrony.service
systemctl is-active --quiet chrony.service
echo "Host configuration backup: $backup"
chronyc tracking
HOST

# Verify NTP over the actual robot-to-PC cable BEFORE changing its time source.
"${SSH[@]}" python3 - <<'PY'
import socket, struct, time
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(4)
s.connect(('10.42.0.102', 123))
packet = bytearray(48); packet[0] = 0x23
now = time.time() + 2208988800
struct.pack_into('!II', packet, 40, int(now), int((now % 1)*2**32))
s.send(packet); data = s.recv(512)
if len(data) < 48 or data[0] >> 6 == 3 or not 1 <= data[1] <= 15 or data[24:32] != packet[40:48]:
    raise SystemExit('Host NTP is not ready; robot configuration was NOT changed. Retry shortly.')
print('Robot received valid NTP response from 10.42.0.102; stratum:', data[1])
PY
"${SSH[@]}" 'sudo -n /usr/bin/bash -s' <<'ROBOT'
set -euo pipefail
backup="/var/backups/g1-wired-time-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$backup" /etc/systemd/timesyncd.conf.d
cp -a /etc/systemd/timesyncd.conf "$backup/"
cp -a /etc/systemd/timesyncd.conf.d "$backup/"
cat > /etc/systemd/timesyncd.conf.d/zz-g1-wired-host.conf <<'CONF'
[Time]
NTP=
NTP=10.42.0.102
FallbackNTP=
PollIntervalMinSec=16
PollIntervalMaxSec=32
CONF
systemctl enable systemd-timesyncd.service
systemctl restart systemd-timesyncd.service
echo "Robot configuration backup: $backup"
ROBOT
for attempt in {1..12}; do
    state="$("${SSH[@]}" 'timedatectl show-timesync --all; timedatectl show -p NTPSynchronized')"
    if grep -q 'ServerAddress=10.42.0.102' <<< "$state" && grep -q 'NTPSynchronized=yes' <<< "$state"; then
        "${SSH[@]}" 'timedatectl timesync-status'
        echo 'Wired time source selected. Restart the Open-RAIL client to discard old timestamped data.'
        exit 0
    fi
    echo "Waiting for robot synchronization ($attempt/12)..."
    sleep 5
done
echo 'Configuration installed, but synchronization was not confirmed. Check robot timedatectl timesync-status.' >&2
exit 1
