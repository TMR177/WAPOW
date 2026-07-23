#!/usr/bin/env bash
# deploy_dash.sh — push the dash to the Pi and relaunch it. Run from any dev
# machine (PC or laptop, Git Bash). Pass a different IP for hotspot sessions:
#   ./deploy_dash.sh              # home (192.168.1.66)
#   ./deploy_dash.sh 172.20.10.4  # field (read IP off the PARKED screen)
set -e
PI="track177@${1:-192.168.1.66}"
scp wapow_dash.py "$PI":~/
ssh "$PI" "pkill -f '[w]apow_dash' || true"
sleep 2
ssh "$PI" 'DISPLAY=:0 setsid nohup python3 -u /home/track177/wapow_dash.py > /home/track177/wapow_run.log 2>&1 < /dev/null & echo relaunched'
sleep 4
ssh "$PI" "pgrep -f '[w]apow_dash' >/dev/null && echo 'DASH UP' || echo 'DASH FAILED - check ~/wapow_run.log'; grep -v 'pygame community\|^pygame ' /home/track177/wapow_run.log | head -4"
