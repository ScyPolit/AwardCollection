#!/bin/sh
set -eu
test "$(id -u)" -eq 0
project=/opt/awardcollection-v1-test/app
test -f "$project/deploy/maintenance.sh"
mkdir -p "$project/runtime"
cat >/etc/systemd/system/awardcollection-maintenance.service <<'UNIT'
[Unit]
Description=AwardCollection local backup and temporary-file cleanup
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/bin/sh /opt/awardcollection-v1-test/app/deploy/maintenance.sh all
TimeoutStartSec=3600
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
StandardOutput=append:/opt/awardcollection-v1-test/app/runtime/maintenance.log
StandardError=append:/opt/awardcollection-v1-test/app/runtime/maintenance.log
UNIT
cat >/etc/systemd/system/awardcollection-maintenance.timer <<'UNIT'
[Unit]
Description=Daily AwardCollection maintenance at 02:30 Asia Shanghai

[Timer]
OnCalendar=*-*-* 02:30:00 Asia/Shanghai
RandomizedDelaySec=5m
Persistent=true
Unit=awardcollection-maintenance.service

[Install]
WantedBy=timers.target
UNIT
systemd-analyze verify /etc/systemd/system/awardcollection-maintenance.service /etc/systemd/system/awardcollection-maintenance.timer
systemctl daemon-reload
systemctl enable --now awardcollection-maintenance.timer
systemctl list-timers awardcollection-maintenance.timer --no-pager
