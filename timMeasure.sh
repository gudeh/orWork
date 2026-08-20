#!/usr/bin/env bash
#
# timMeasure.sh -- time a run-me script (or any command) over several runs and
# report its peak memory.
# Lives in ~/workspace/orWork; no need to copy it into each ORFS flow dir.
#
# Usage:
#   timMeasure.sh [-n NUM_RUNS] [run-me-script.sh | name-fragment [out-name] | command args...]
#
# Examples:
#   ~/workspace/orWork/timMeasure.sh ~/workspace/9ORFS/flow/run-me-foo.sh
#       run from anywhere; logs land next to the run-me script
#
#   cd ~/workspace/9ORFS/flow && ~/workspace/orWork/timMeasure.sh -n 5
#       no command: auto-detects the single run-me-*.sh in the current dir
#
#   cd ~/workspace/9ORFS/flow && ~/workspace/orWork/timMeasure.sh gcd
#       name fragment: uses the single ./run-me-*gcd*.sh; refuses if several match
#
#   cd ~/workspace/9ORFS/flow && ~/workspace/orWork/timMeasure.sh gcd baseline
#       trailing name after the script/fragment: runtimes go to baseline.txt
#       (only in run-me mode; for arbitrary commands the default name is used)
#
#   ~/workspace/orWork/timMeasure.sh openroad -no_init -threads 1 test.tcl
#       arbitrary command; runs in the current dir, logs land there
#
# Output file (written into the flow dir under test, so runs in several
# ORFS copies at once never clash):
#   timeTest.txt    -- measurements first (header, per-iteration real/user/sys
#                      and maxrss, summary, and any internal tool runtimes found
#                      in the logs grouped by message code, e.g.
#                      [INFO DPL-0500] Runtime: ...), then the full program
#                      output of all iterations
#                      (or <out-name>.txt if a trailing name was given)
#
# maxrss is the peak resident set size of the run (the largest any single
# process in the tree reached, so for a run-me it is essentially openroad's
# peak).  It needs GNU time (/usr/bin/time); without it only times are
# reported.
#
# stdin is redirected from /dev/null, so openroad exits at EOF: run-me
# scripts no longer need -exit added by hand.

set -u
export LC_NUMERIC=C  # keep 'time' output using '.' as decimal separator

NUM_RUNS=3
while getopts "n:h" opt; do
  case $opt in
    n) NUM_RUNS=$OPTARG ;;
    h) grep -E '^#( |$)' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) exit 2 ;;
  esac
done
shift $((OPTIND - 1))

if [ $# -eq 0 ]; then
  # No command given: expect exactly one run-me-*.sh in the current dir.
  shopt -s nullglob
  candidates=(./run-me-*.sh)
  shopt -u nullglob
  if [ ${#candidates[@]} -ne 1 ]; then
    echo "error: no command given and ${#candidates[@]} run-me-*.sh found in $PWD" >&2
    [ ${#candidates[@]} -gt 0 ] && printf '  %s\n' "${candidates[@]}" >&2
    echo "usage: timMeasure.sh [-n NUM_RUNS] [run-me-script | name-fragment | command args...]" >&2
    exit 2
  fi
  set -- "${candidates[0]}"
elif [ ! -f "$1" ]; then
  # Not a file: try it as a fragment of a run-me name in the current dir,
  # e.g. 'gcd' picks the single ./run-me-*gcd*.sh.
  shopt -s nullglob
  candidates=(./run-me-*"$1"*.sh)
  shopt -u nullglob
  if [ ${#candidates[@]} -eq 1 ]; then
    shift
    set -- "${candidates[0]}" "$@"
  elif [ ${#candidates[@]} -gt 1 ]; then
    echo "error: '$1' matches ${#candidates[@]} run-me scripts in $PWD, be more specific:" >&2
    printf '  %s\n' "${candidates[@]}" >&2
    exit 2
  elif ! command -v "$1" > /dev/null 2>&1; then
    echo "error: '$1' is not a file, matches no ./run-me-*.sh name in $PWD, and is not a command" >&2
    exit 2
  fi
  # else: $1 is a command in PATH; fall through and run it as-is in $PWD.
fi

OUT_NAME=timeTest
if [ -f "$1" ]; then
  # First arg is a script: resolve it so it can be launched from anywhere,
  # and keep the logs next to it (run-me scripts cd to their own dir anyway).
  script=$(readlink -f "$1")
  RUN_DIR=$(dirname "$script")
  echo "timing: $script"
  # Optional trailing arg: base name for the runtimes file (.txt appended).
  if [ $# -gt 2 ]; then
    echo "error: too many arguments after the run-me script: ${*:3}" >&2
    exit 2
  elif [ $# -eq 2 ]; then
    OUT_NAME=${2%.txt}
  fi
  set -- "$script"
else
  RUN_DIR=$PWD
fi

OUT=$RUN_DIR/$OUT_NAME.txt
# Full program output is buffered in a temp log during the run, then appended
# after the measurements so the single output file reads: measurements first,
# full logs afterwards.
LOG=$(mktemp "$RUN_DIR/.timMeasure.log.XXXXXX") || { echo "error: mktemp failed" >&2; exit 1; }
# GNU time reports peak memory (%M), the shell builtin does not, so use it when
# present.  Its report goes to a file of its own (-o) to keep it out of the
# program output.
GNU_TIME=$(command -v /usr/bin/time || true)
RUSAGE=
if [ -n "$GNU_TIME" ]; then
  RUSAGE=$(mktemp "$RUN_DIR/.timMeasure.rusage.XXXXXX") ||
    { echo "error: mktemp failed" >&2; exit 1; }
else
  echo "warning: /usr/bin/time not found, memory will not be measured" >&2
fi
trap 'rm -f "$LOG" ${RUSAGE:+"$RUSAGE"}' EXIT

{
  echo "# $(date '+%Y-%m-%d %H:%M:%S')  host=$(hostname)  runs=$NUM_RUNS"
  echo "# cmd: $*"
} | tee "$OUT"

for i in $(seq 1 "$NUM_RUNS"); do
  echo "=== iteration $i ===" | tee -a "$OUT" "$LOG"
  # The command's own output goes to the temp log; only the resource report is kept.
  if [ -n "$GNU_TIME" ]; then
    "$GNU_TIME" -f $'real\t%e\nuser\t%U\nsys\t%S\nmaxrss_kb\t%M' -o "$RUSAGE" \
      "$@" < /dev/null >> "$LOG" 2>&1
    status=$?
    # %M is in KB; MB is the readable scale for a place-and-route run.
    times=$(awk -F'\t' '$1 == "maxrss_kb" { printf "maxrss\t%.1f MB\n", $2 / 1024; next }
                        { print }' "$RUSAGE")
  else
    TIMEFORMAT=$'real\t%R\nuser\t%U\nsys\t%S'
    times=$( { time "$@" < /dev/null >> "$LOG" 2>&1; } 2>&1 )
    status=$?
  fi
  echo "$times" | tee -a "$OUT"
  [ "$status" -ne 0 ] &&
    echo "iteration $i FAILED (exit $status), see full logs below" | tee -a "$OUT"
done

awk '/^real/   { n++; s += $2; if ($2 > mx) mx = $2; if (mn == "" || $2 < mn) mn = $2 }
     /^maxrss/ { rn++; rs += $2; if ($2 > rmx) rmx = $2; if (rmn == "" || $2 < rmn) rmn = $2 }
     /FAILED/  { f++ }
     END { if (n) printf "=== summary ===\nreal avg %.3f s  (min %.3f, max %.3f, n=%d)\n", s/n, mn, mx, n
           if (rn) printf "maxrss avg %.1f MB  (min %.1f, max %.1f, n=%d)\n", rs/rn, rmn, rmx, rn
           if (f) printf "WARNING: %d iteration(s) FAILED -- times above are not trustworthy\n", f }' \
  "$OUT" | tee -a "$OUT"

# Internal tool runtimes: OpenROAD tools log "[INFO <TOOL>-<CODE>] Runtime: <sec>s"
# (DPL-0500, GPL-500, CTS-500, DRT-501, RSZ-504..507, IFP-500/501, ...). Scan the
# full log for every such line, group by message code, and summarise -- independent
# of which stage the run-me ran, so a full-flow run shows one line per stage.
awk '/Runtime:/ {
       code = "?"
       if (match($0, /[A-Za-z]+-[0-9]+/)) code = substr($0, RSTART, RLENGTH)
       rest = $0; sub(/.*Runtime:[ \t]*/, "", rest); val = rest + 0
       if (!(code in n)) order[++nc] = code
       n[code]++; sum[code] += val
       if (!(code in mx) || val > mx[code]) mx[code] = val
       if (!(code in mn) || val < mn[code]) mn[code] = val
       vals[code] = vals[code] (n[code] > 1 ? " " : "") sprintf("%g", val)
     }
     END {
       if (!nc) exit
       print "=== internal runtimes ==="
       for (i = 1; i <= nc; i++) { c = order[i]
         printf "%-10s avg %.2f s  (min %.2f, max %.2f, n=%d)  [%s]\n", \
                c, sum[c]/n[c], mn[c], mx[c], n[c], vals[c] } }' \
  "$LOG" | tee -a "$OUT"

# Append the full program output after the measurements.
{
  echo
  echo "=== full logs ==="
  cat "$LOG"
} >> "$OUT"

echo "results: $OUT"
