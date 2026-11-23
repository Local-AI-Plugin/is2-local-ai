#!/bin/sh
# Lock the Rock 5T (RK3588) CPU, memory, NPU and GPU clocks at their maximum,
# or put them back to the board's defaults.
#
#   rock5t-max-clocks.sh apply   # lock at maximum (what the boot service runs)
#   rock5t-max-clocks.sh reset   # back to the defaults (ondemand, lowest minimums)
#   rock5t-max-clocks.sh status  # show the current settings
#
# Needs root. The memory, NPU and GPU have no "performance" governor on this
# kernel, so they are locked by raising their minimum clock to their maximum.
# Measured effect on qwen3.5:4b (CPU, llama.cpp): prompt +12%, generation +6%.
set -eu

CPU=/sys/devices/system/cpu/cpufreq
DEV=/sys/class/devfreq
DEVICES="dmc fdab0000.npu fb000000.gpu"   # memory, NPU, GPU

case "${1:-status}" in
  apply)
    for p in "$CPU"/policy*; do echo performance > "$p/scaling_governor"; done
    for d in $DEVICES; do
      [ -d "$DEV/$d" ] && cat "$DEV/$d/max_freq" > "$DEV/$d/min_freq"
    done
    ;;
  reset)
    for p in "$CPU"/policy*; do echo ondemand > "$p/scaling_governor"; done
    for d in $DEVICES; do
      # The lowest available frequency is the first one listed.
      [ -d "$DEV/$d" ] && awk '{print $1}' "$DEV/$d/available_frequencies" > "$DEV/$d/min_freq"
    done
    ;;
  status) ;;
  *) echo "usage: $0 apply|reset|status" >&2; exit 2 ;;
esac

for p in "$CPU"/policy*; do
  echo "$(basename "$p"): $(cat "$p/scaling_governor") $(cat "$p/scaling_cur_freq") kHz"
done
for d in $DEVICES; do
  [ -d "$DEV/$d" ] && echo "$d: min $(cat "$DEV/$d/min_freq") cur $(cat "$DEV/$d/cur_freq") Hz"
done
