#!/usr/bin/env bash
set -euo pipefail

/usr/local/bin/forte -c 0.0.0.0:61499 &
FORTE_PID=$!

/usr/local/bin/sine-mqtt &
SINE_PID=$!

cleanup() {
  kill "$SINE_PID" "$FORTE_PID" 2>/dev/null || true
  wait "$SINE_PID" 2>/dev/null || true
  wait "$FORTE_PID" 2>/dev/null || true
}

trap cleanup INT TERM

wait -n "$SINE_PID" "$FORTE_PID"
STATUS=$?
cleanup
exit $STATUS
