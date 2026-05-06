#!/bin/sh
set -eu

if pgrep -f '[m]ock_robotiq_gripper.py' >/dev/null 2>&1; then
  exit 0
fi

nohup python3 /opt/uram/mock_robotiq_gripper.py >/tmp/mock_robotiq_gripper.log 2>&1 &
sleep 1

if ! pgrep -f '[m]ock_robotiq_gripper.py' >/dev/null 2>&1; then
  cat /tmp/mock_robotiq_gripper.log >&2 2>/dev/null || true
  exit 1
fi
