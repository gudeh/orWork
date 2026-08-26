#!/bin/bash
#
# utilizationSweep.sh -- find the highest CORE_UTILIZATION that still completes
# the full ORFS flow, and report the timing achieved at each value.
#
# Runs each utilization as a separate FLOW_VARIANT so runs never clobber each
# other, then collects final TNS/WNS + completion status into a summary table.
#
# Usage:
#   ./utilizationSweep.sh [options] [-- extra make args]
#
# Options:
#   -f FLOW_DIR    ORFS flow/ directory       (default: autodetect, see below)
#   -d CONFIG      design config.mk, relative to FLOW_DIR or absolute
#   -u "LIST"      space/comma separated utilization values
#   -j N           run N sweeps concurrently  (default: 1)
#   -p PREFIX      FLOW_VARIANT prefix        (default: util)
#   -m PLAT_HOME   PLATFORM_HOME passed to make (default: unset, or $PLATFORM_HOME)
#   -r             report only: re-collect results, run nothing
#   -h             help
#
# Examples:
#   ./utilizationSweep.sh -d designs/nangate45/bp_fe_top/config.mk -u "20 30 40 45"
#   ./utilizationSweep.sh -d designs/sky130hd/aes/config.mk -u "15,20,25" -j 3
#   ./utilizationSweep.sh -d designs/rapidus2hp/gcd/config.mk -m /platforms -u "50 55"
#   ./utilizationSweep.sh -d designs/nangate45/bp_fe_top/config.mk -r
#
set -u
set -o pipefail

# ---------------------------------------------------------------- defaults --
FLOW_DIR=""
DESIGN_CONFIG=""
UTIL_LIST=""
JOBS=1
PREFIX="util"
REPORT_ONLY=0
PLAT_HOME="${PLATFORM_HOME:-}"   # inherit from env if already exported

DEFAULT_UTILS="20 30 40 50 60 70 75 80 85"

usage() { sed -n '2,27p' "$0" | sed -n 's/^#\( \|$\)\{0,1\}//p'; exit "${1:-0}"; }

# ------------------------------------------------------------------- parse --
while getopts ":f:d:u:j:p:m:rh" opt; do
  case "$opt" in
    f) FLOW_DIR="$OPTARG" ;;
    d) DESIGN_CONFIG="$OPTARG" ;;
    u) UTIL_LIST="$OPTARG" ;;
    j) JOBS="$OPTARG" ;;
    p) PREFIX="$OPTARG" ;;
    m) PLAT_HOME="$OPTARG" ;;
    r) REPORT_ONLY=1 ;;
    h) usage 0 ;;
    \?) echo "ERROR: unknown option -$OPTARG" >&2; usage 1 ;;
    :)  echo "ERROR: -$OPTARG needs an argument" >&2; usage 1 ;;
  esac
done
shift $((OPTIND - 1))
EXTRA_MAKE_ARGS=("$@")   # anything after `--` is passed straight to make

# ------------------------------------------------- locate the flow/ folder --
# Order: -f flag > $ORFS_FLOW_DIR > walk up from $PWD > walk up from script dir.
find_flow_dir() {
  local d="$1"
  while [[ "$d" != "/" && -n "$d" ]]; do
    [[ -f "$d/flow/Makefile" && -d "$d/flow/designs" ]] && { echo "$d/flow"; return 0; }
    [[ -f "$d/Makefile"      && -d "$d/designs"      ]] && { echo "$d";      return 0; }
    d="$(dirname "$d")"
  done
  return 1
}

if [[ -z "$FLOW_DIR" ]]; then
  FLOW_DIR="${ORFS_FLOW_DIR:-}"
fi
if [[ -z "$FLOW_DIR" ]]; then
  FLOW_DIR="$(find_flow_dir "$PWD")" || true
fi
if [[ -z "$FLOW_DIR" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  FLOW_DIR="$(find_flow_dir "$SCRIPT_DIR")" || true
fi
if [[ -z "$FLOW_DIR" || ! -f "$FLOW_DIR/Makefile" ]]; then
  cat >&2 <<EOF
ERROR: could not locate an ORFS flow/ directory.
       Pass one with  -f /path/to/ORFS/flow
       or export ORFS_FLOW_DIR=/path/to/ORFS/flow
EOF
  exit 1
fi
FLOW_DIR="$(cd "$FLOW_DIR" && pwd)"

# ------------------------------------------------------ resolve the design --
if [[ -z "$DESIGN_CONFIG" ]]; then
  echo "ERROR: no design given. Use -d designs/<platform>/<design>/config.mk" >&2
  exit 1
fi
# accept absolute, flow-relative, or cwd-relative
if   [[ -f "$DESIGN_CONFIG"           ]]; then CFG="$(cd "$(dirname "$DESIGN_CONFIG")" && pwd)/$(basename "$DESIGN_CONFIG")"
elif [[ -f "$FLOW_DIR/$DESIGN_CONFIG" ]]; then CFG="$FLOW_DIR/$DESIGN_CONFIG"
else
  echo "ERROR: design config not found: $DESIGN_CONFIG" >&2
  echo "       looked in \$PWD and $FLOW_DIR" >&2
  exit 1
fi

# PLATFORM / DESIGN_NICKNAME drive the results/logs paths we must read back.
get_mk_var() { sed -n "s/^[[:space:]]*export[[:space:]]\+$1[[:space:]]*=[[:space:]]*//p" "$CFG" | tail -1 | sed 's/[[:space:]]*$//'; }
PLATFORM="$(get_mk_var PLATFORM)"
DESIGN_NAME="$(get_mk_var DESIGN_NAME)"
DESIGN_NICKNAME="$(get_mk_var DESIGN_NICKNAME)"
[[ -z "$DESIGN_NICKNAME" ]] && DESIGN_NICKNAME="$DESIGN_NAME"
if [[ -z "$PLATFORM" || -z "$DESIGN_NICKNAME" ]]; then
  echo "ERROR: could not read PLATFORM/DESIGN_NAME from $CFG" >&2
  exit 1
fi

# warn if the config pins the die explicitly -- CORE_UTILIZATION is then ignored
if grep -qE '^[[:space:]]*export[[:space:]]+DIE_AREA' "$CFG" && \
   grep -qE '^[[:space:]]*export[[:space:]]+CORE_AREA' "$CFG"; then
  echo "WARNING: $CFG sets both DIE_AREA and CORE_AREA."
  echo "         floorplan.tcl prefers those, so CORE_UTILIZATION will be IGNORED."
  echo "         Comment them out for this sweep to mean anything."
  echo
fi

# ------------------------------------------------------ utilization values --
if [[ -n "$UTIL_LIST" ]]; then
  IFS=', ' read -r -a UTILS <<< "$UTIL_LIST"
else
  read -r -a UTILS <<< "$DEFAULT_UTILS"
fi
# drop empties, sort numerically
CLEAN=()
for u in "${UTILS[@]}"; do [[ -n "$u" ]] && CLEAN+=("$u"); done
IFS=$'\n' UTILS=($(printf '%s\n' "${CLEAN[@]}" | sort -n -u)); unset IFS
if [[ ${#UTILS[@]} -eq 0 ]]; then
  echo "ERROR: empty utilization list" >&2; exit 1
fi

SWEEP_LOG_DIR="$FLOW_DIR/logs/$PLATFORM/$DESIGN_NICKNAME"
mkdir -p "$SWEEP_LOG_DIR"

# ============================================================== run phase ===
run_one() {
  local util="$1"
  local variant="${PREFIX}${util}"
  local drv="$SWEEP_LOG_DIR/sweep_${variant}.log"

  echo "  [util=${util}] starting  -> $drv"
  # PLATFORM_HOME only passed when set -- an empty one breaks stock platforms.
  local plat_arg=()
  [[ -n "$PLAT_HOME" ]] && plat_arg=(PLATFORM_HOME="$PLAT_HOME")
  ( cd "$FLOW_DIR" && \
    make DESIGN_CONFIG="$CFG" \
         FLOW_VARIANT="$variant" \
         CORE_UTILIZATION="$util" \
         "${plat_arg[@]}" \
         "${EXTRA_MAKE_ARGS[@]}" \
  ) >"$drv" 2>&1
  local rc=$?
  if [[ $rc -eq 0 ]]; then echo "  [util=${util}] make OK"
  else                     echo "  [util=${util}] make FAILED (rc=$rc)"; fi
  return 0   # never abort the sweep; a failure is a data point
}

if [[ $REPORT_ONLY -eq 0 ]]; then
  echo "=========================================================="
  echo " ORFS core utilization sweep"
  echo "   flow dir : $FLOW_DIR"
  echo "   design   : $DESIGN_NICKNAME ($DESIGN_NAME) on $PLATFORM"
  echo "   config   : $CFG"
  echo "   values   : ${UTILS[*]}"
  echo "   parallel : $JOBS"
  [[ -n "$PLAT_HOME" ]] && echo "   plat home: $PLAT_HOME"
  [[ ${#EXTRA_MAKE_ARGS[@]} -gt 0 ]] && echo "   make args: ${EXTRA_MAKE_ARGS[*]}"
  echo "=========================================================="
  echo

  running=0
  for util in "${UTILS[@]}"; do
    run_one "$util" &
    running=$((running + 1))
    if [[ $running -ge $JOBS ]]; then wait -n 2>/dev/null || wait; running=$((running - 1)); fi
  done
  wait
  echo
  echo "All runs finished. Collecting results..."
  echo
fi

# =========================================================== report phase ===
# Pull final metrics out of each variant's 6_report.json (full precision, and
# it only exists if the flow actually reached the end).
collect() {
  local util="$1" variant="${PREFIX}${util}"
  local ldir="$FLOW_DIR/logs/$PLATFORM/$DESIGN_NICKNAME/$variant"
  local rdir="$FLOW_DIR/reports/$PLATFORM/$DESIGN_NICKNAME/$variant"
  local drv="$SWEEP_LOG_DIR/sweep_${variant}.log"

  UTIL="$util" LDIR="$ldir" RDIR="$rdir" DRV="$drv" python3 - <<'PY'
import json, os, re, glob

util = os.environ["UTIL"]
ldir, rdir, drv = os.environ["LDIR"], os.environ["RDIR"], os.environ["DRV"]

# ---- did it finish? 6_report.json is written by the last stage ----
final = os.path.join(ldir, "6_report.json")
done  = os.path.isfile(final)

# ---- where did it stop / why ----
stage, err = "-", ""
if not done:
    # last stage log that exists tells us how far it got
    logs = sorted(glob.glob(os.path.join(ldir, "[0-9]_*.log")))
    if logs:
        stage = os.path.basename(logs[-1]).replace(".log", "")
    # first ERROR line is the most useful cause
    for f in ([drv] if os.path.isfile(drv) else []) + logs[::-1]:
        try:
            txt = open(f, errors="replace").read()
        except OSError:
            continue
        m = re.search(r"\[ERROR ([A-Z]{3}-\d+)\]\s*(.*)", txt)
        if m:
            err = f"{m.group(1)}: {m.group(2).strip()[:60]}"
            break
        if not err and "Error" in txt:
            m2 = re.search(r"^Error:.*$", txt, re.M)
            if m2:
                err = m2.group(0)[:70]
    if not err:
        err = "no 6_report.json (incomplete)"

def fmt(v, p=4):
    return "-" if v is None else f"{v:.{p}f}"

row = dict(util=util, status="FAIL", stage=stage, note=err,
           wns="-", tns="-", hold_wns="-", hold_tns="-",
           drc="-", inst="-", area="-", real_util="-")

if done:
    try:
        m = json.load(open(final))
    except Exception as e:
        row["note"] = f"unreadable 6_report.json: {e}"
    else:
        row["status"]   = "PASS"
        row["stage"]    = "finish"
        row["wns"]      = fmt(m.get("finish__timing__setup__ws"))
        row["tns"]      = fmt(m.get("finish__timing__setup__tns"), 2)
        row["hold_wns"] = fmt(m.get("finish__timing__hold__ws"))
        row["hold_tns"] = fmt(m.get("finish__timing__hold__tns"), 2)
        iu = m.get("finish__design__instance__utilization")
        row["real_util"] = "-" if iu is None else f"{iu*100:.1f}"
        ic = m.get("finish__design__instance__count")
        row["inst"] = "-" if ic is None else str(int(ic))
        da = m.get("finish__design__die__area")
        row["area"] = "-" if da is None else f"{da:.0f}"

        # DRC: prefer the route drc report; empty file == clean
        n = None
        for cand in ("5_route_drc.rpt", "5_route_drc.rpt-5.rpt"):
            p = os.path.join(rdir, cand)
            if os.path.isfile(p):
                try:
                    txt = open(p, errors="replace").read()
                except OSError:
                    continue
                n = len(re.findall(r"violation type", txt, re.I)) or (0 if not txt.strip() else None)
                if n is not None:
                    break
        if n is None:
            n = m.get("detailedroute__route__drc_errors")
        row["drc"] = "-" if n is None else str(int(n))

        notes = []
        try:
            if float(row["wns"]) < 0: notes.append("setup viol")
        except ValueError: pass
        try:
            if float(row["hold_wns"]) < 0: notes.append("hold viol")
        except ValueError: pass
        if row["drc"] not in ("-", "0"): notes.append(f"{row['drc']} DRC")
        row["note"] = ", ".join(notes) if notes else "clean"

print("\t".join([row["util"], row["status"], row["stage"], row["wns"], row["tns"],
                 row["hold_wns"], row["hold_tns"], row["drc"], row["real_util"],
                 row["inst"], row["area"], row["note"]]))
PY
}

SUMMARY="$SWEEP_LOG_DIR/utilization_sweep_summary.tsv"
{
  printf "util\tstatus\tstage\twns\ttns\thold_wns\thold_tns\tdrc\treal_util%%\tinsts\tdie_area\tnote\n"
  for util in "${UTILS[@]}"; do collect "$util"; done
} > "$SUMMARY"

echo "=============================================================================="
echo " RESULTS -- $DESIGN_NICKNAME on $PLATFORM"
echo "=============================================================================="
column -t -s $'\t' "$SUMMARY"
echo
echo "TSV: $SUMMARY"
echo

# ------------------------------------------- headline: tightening progress ---
# Goal is to TIGHTEN the design until timing goes negative -- so the interesting
# points are where slack first turns negative and where the flow stops closing.
BEST="$(awk -F'\t' 'NR>1 && $2=="PASS" {print $1}' "$SUMMARY" | sort -n | tail -1)"
SLACK_OK="$(awk -F'\t' 'NR>1 && $2=="PASS" && $4!="-" && $4+0>=0 {print $1}' "$SUMMARY" | sort -n | tail -1)"
FIRST_NEG="$(awk -F'\t' 'NR>1 && $2=="PASS" && $4!="-" && $4+0<0 {print $1}' "$SUMMARY" | sort -n | head -1)"
FIRST_FAIL="$(awk -F'\t' 'NR>1 && $2=="FAIL" {print $1}' "$SUMMARY" | sort -n | head -1)"

show_row() {  # $1 = util value, $2 = label
  awk -F'\t' -v b="$1" -v lbl="$2" 'NR>1 && $1==b {
    printf "%-46s: %s%%\n", lbl, $1
    printf "     setup WNS %-9s TNS %-8s  real_util %-6s  DRC %s\n", $4, $5, $9, $8 }' "$SUMMARY"
}

if [[ -z "$BEST" && -z "$FIRST_FAIL" ]]; then
  echo "No results found. Did the runs happen?"
elif [[ -z "$BEST" ]]; then
  echo "No utilization value completed the full flow."
  echo "Try lower values, e.g.  -u \"15 20 25\""
else
  if [[ -n "$FIRST_NEG" ]]; then
    show_row "$FIRST_NEG" "Lowest util with NEGATIVE setup slack"
    echo "  -> timing is now the binding constraint; this is the tightening you want."
  else
    echo "Setup slack is still POSITIVE at every value tested (best ${BEST}%)."
    echo "  -> the design is not tight yet. Push higher:  -u \"$((BEST + 5)) $((BEST + 10)) $((BEST + 15))\""
    echo "  -> if util stops moving real_util%, the die is floorplan-bound, not"
    echo "     utilization-bound -- tighten the clock period in the SDC instead."
  fi
  [[ -n "$SLACK_OK" ]] && { echo; show_row "$SLACK_OK" "Highest util still meeting timing (WNS >= 0)"; }
  echo
  show_row "$BEST" "Highest util completing the full flow"
  [[ -n "$FIRST_FAIL" ]] && echo "First util that FAILED to complete            : ${FIRST_FAIL}%  (see note column)"
fi
echo
echo "Columns:"
echo "  util       requested CORE_UTILIZATION (sizes the die at floorplan)."
echo "  real_util% ACHIEVED instance utilization at 6_report -- macros + std cells,"
echo "             excluding fill. Sits above 'util' because the die is fixed at"
echo "             floorplan while CTS and the resizer keep inserting buffers into it."
echo "             Watch the GAP: a widening real_util% - util gap means repair cells"
echo "             are eating the space you freed, which is what pushes slack negative."
echo "  wns/tns    final setup slack. NEGATIVE is the goal here -- that is the design"
echo "             tightened to the point where timing, not area, is what binds."
