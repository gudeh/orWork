#!/usr/bin/env python3
"""Generate DPL (detailed placement legalizer) report tables from OpenROAD JSON logs."""

import csv
import json
import os
import re
import sys
from collections import defaultdict
from itertools import zip_longest
from pathlib import Path


def parse_json_preserve_duplicates(filepath):
    """Parse JSON file preserving duplicate keys as ordered list of (key, value) pairs."""
    entries = []
    with open(filepath) as f:
        for line in f:
            line = line.strip().rstrip(",")
            m = re.match(r'^"([^"]+)"\s*:\s*(.+)$', line)
            if m:
                key = m.group(1)
                val_str = m.group(2)
                try:
                    val = json.loads(val_str)
                except json.JSONDecodeError:
                    val = val_str
                entries.append((key, val))
    return entries


def extract_dpl_calls(entries, caller):
    """Extract DPL call records for a given caller from ordered entries.

    Groups entries by splitting on the 'utilizatin__before__dpl' sentinel key.
    """
    prefix = f"{caller}__"
    calls = []
    current = None

    for key, val in entries:
        if not key.startswith(prefix):
            continue
        suffix = key[len(prefix):]

        if suffix == "utilizatin__before__dpl":
            # New DPL call starts
            if current is not None:
                calls.append(current)
            current = {"start_util": val}
        elif current is not None:
            if suffix == "HL__converge__phase_1__iteration":
                current["converged"] = True
                current["phase1_iters"] = val
            elif suffix == "HL__converge__phase_2__iteration":
                current["phase2_iters"] = val
            elif suffix == "HL__no__converge__final_violations":
                current["converged"] = False
            elif suffix == "design__instance__displacement__total":
                current["displacement"] = val
            elif suffix == "dpl__hpwl__delta__percent":
                current["deltaWL"] = val

    if current is not None:
        calls.append(current)

    # Mark calls that had no legalization (displacement 0, no convergence info)
    for call in calls:
        if "converged" not in call and call.get("displacement", None) == 0:
            call["skipped"] = True

    return calls


# Determine which callers can appear in which stage files
STAGE_CALLERS = {
    "place_dp": ["detailedplace"],
    "cts": ["cts"],
    "grt": ["globalroute"],
}


def extract_dpl_log_info(log_file):
    """Extract runtimes and errors for each detailed_placement call from a log file.

    Returns list of dicts with 'runtime' and 'error' keys, one per DPL call.
    """
    calls = []
    current = None
    try:
        with open(log_file) as f:
            for line in f:
                if re.search(r'^detailed_placement\b', line):
                    if current is not None:
                        calls.append(current)
                    current = {"runtime": "", "error": False}
                elif current is not None:
                    m = re.match(r'.*Took\s+(\d+)\s+seconds:\s+detailed_placement', line)
                    if m:
                        current["runtime"] = int(m.group(1))
                    if re.search(r'\[ERROR DPL-\d+\]', line):
                        current["error"] = True
    except FileNotFoundError:
        pass
    if current is not None:
        calls.append(current)
    return calls


def collect_data(logs_dir):
    """Walk logs_dir and collect all DPL call records."""
    rows = []
    logs_path = Path(logs_dir)

    for json_file in sorted(logs_path.rglob("*.json")):
        # Parse path: logs/[platform]/[design]/[run]/[stage].json
        rel = json_file.relative_to(logs_path)
        parts = rel.parts
        if len(parts) != 4:
            continue
        platform, design, run, stage_file = parts
        stage_name = stage_file.replace(".json", "")
        # e.g. "3_5_place_dp" -> extract last part after digit prefixes
        stage_key = None
        for key in STAGE_CALLERS:
            if stage_name.endswith(key):
                stage_key = key
                break
        if stage_key is None:
            continue

        # Extract DPL runtimes and errors from the corresponding .log file
        log_file = json_file.with_suffix(".log")
        log_info = extract_dpl_log_info(log_file)

        entries = parse_json_preserve_duplicates(json_file)
        runtime_idx = 0
        for caller in STAGE_CALLERS[stage_key]:
            dpl_calls = extract_dpl_calls(entries, caller)
            for i, call in enumerate(dpl_calls):
                call_label = caller if len(dpl_calls) == 1 else f"{caller}[{i}]"
                info = log_info[runtime_idx] if runtime_idx < len(log_info) else {}
                runtime_idx += 1
                if info.get("error"):
                    converge = "failed"
                elif call.get("skipped"):
                    converge = "skip"
                elif call.get("converged"):
                    converge = "yes"
                elif call.get("converged") is False:
                    converge = "no"
                elif call.get("displacement") is not None:
                    # Old OR without hybrid legalizer: DPL ran but no convergence keys
                    converge = "yes"
                else:
                    converge = ""
                rows.append({
                    "run": run,
                    "platform": platform,
                    "design": design,
                    "stage_caller": call_label,
                    "start_util": call.get("start_util", ""),
                    "converge": converge,
                    "phase1_iters": call.get("phase1_iters", ""),
                    "phase2_iters": call.get("phase2_iters", ""),
                    "displacement": call.get("displacement", ""),
                    "deltaWL": call.get("deltaWL", ""),
                    "runtime_s": info.get("runtime", ""),
                })
    return rows


def print_table(rows, design=None):
    """Print a formatted table for the given rows."""
    if design:
        rows = [r for r in rows if r["design"] == design]
    if not rows:
        return

    headers = ["run", "platform", "design", "stage_caller", "start_util",
               "converge?", "phase1_iters", "phase2_iters", "displacement", "deltaWL", "runtime_s"]
    keys = ["run", "platform", "design", "stage_caller", "start_util",
            "converge", "phase1_iters", "phase2_iters", "displacement", "deltaWL", "runtime_s"]

    # Compute column widths
    widths = [len(h) for h in headers]
    for r in rows:
        for i, k in enumerate(keys):
            widths[i] = max(widths[i], len(fmt_val(r[k])))

    fmt = " | ".join(f"{{:<{w}}}" for w in widths)
    sep = "-+-".join("-" * w for w in widths)

    print(fmt.format(*headers))
    print(sep)
    for r in rows:
        print(fmt.format(*[fmt_val(r[k]) for k in keys]))
    print()


HEADERS = ["run", "platform", "design", "stage_caller", "start_util",
           "converge?", "phase1_iters", "phase2_iters", "displacement", "deltaWL", "runtime_s"]
KEYS = ["run", "platform", "design", "stage_caller", "start_util",
        "converge", "phase1_iters", "phase2_iters", "displacement", "deltaWL", "runtime_s"]


def write_csv(rows, output_dir, design=None):
    """Write rows to a CSV file. If design is given, filters to that design."""
    if design is not None:
        rows = [r for r in rows if r["design"] == design]
        filename = f"dpl_report_{design}.csv"
    else:
        filename = "dpl_report_all.csv"
    if not rows:
        return
    csv_path = os.path.join(output_dir, filename)
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        for r in rows:
            writer.writerow([fmt_val(r[k]) for k in KEYS])
    print(f"Wrote {csv_path}")


NUMERIC_KEYS = ["start_util", "phase1_iters", "phase2_iters", "displacement", "deltaWL", "runtime_s"]


def fmt_val(v):
    """Format a value for display: 1 decimal for floats, plain for ints/strings."""
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)
PCT_KEYS = ["displacement", "deltaWL", "runtime_s"]


def parse_run_id(run):
    """Return (base_id, is_master) for a run name like '51' or 'master51'."""
    m = re.match(r'^master(\d+.*)$', run)
    if m:
        return m.group(1), True
    return run, False


def find_pairs(rows, design):
    """Find (run, master_run) pairs for a design.

    Returns list of (base_id, run_rows, master_rows) sorted by base_id.
    """
    design_rows = [r for r in rows if r["design"] == design]
    # Group by (base_id, is_master)
    groups = defaultdict(list)
    for r in design_rows:
        base_id, is_master = parse_run_id(r["run"])
        groups[(base_id, is_master)].append(r)

    # Find base_ids that have both a non-master and master variant
    base_ids = set()
    for (base_id, is_master) in groups:
        base_ids.add(base_id)

    pairs = []
    for base_id in sorted(base_ids):
        run_rows = groups.get((base_id, False), [])
        master_rows = groups.get((base_id, True), [])
        if run_rows and master_rows:
            pairs.append((base_id, run_rows, master_rows))
    return pairs


def compute_delta(run_row, master_row):
    """Compute a delta row between run and master for numeric columns.

    For converge, show improvement/regression relative to master.
    """
    delta = {}
    for k in KEYS:
        if k in NUMERIC_KEYS:
            rv = run_row.get(k, "")
            mv = master_row.get(k, "")
            if rv != "" and mv != "" and isinstance(rv, (int, float)) and isinstance(mv, (int, float)):
                diff = rv - mv
                delta[k] = f"{diff:+.1f}" if isinstance(diff, float) else f"{diff:+d}"
                if k in PCT_KEYS and mv != 0:
                    pct = (diff / abs(mv)) * 100
                    delta[f"{k}_pct"] = f"{pct:+.1f}%"
                elif k in PCT_KEYS:
                    delta[f"{k}_pct"] = ""
            else:
                delta[k] = ""
                if k in PCT_KEYS:
                    delta[f"{k}_pct"] = ""
        else:
            delta[k] = ""
    delta["run"] = "delta"
    delta["stage_caller"] = run_row["stage_caller"]

    # Compare convergence: show improvement/degradation vs master
    # Treat "no" (non-convergence) the same as "failed"
    rc = run_row.get("converge", "")
    mc = master_row.get("converge", "")
    if rc == "no":
        rc = "failed"
    if mc == "no":
        mc = "failed"
    if rc == mc and rc == "failed":
        delta["converge"] = "both failed"
    elif rc == mc:
        delta["converge"] = "same"
    elif mc in ("failed",) and rc in ("yes", "skip"):
        delta["converge"] = "fixed"
    elif rc in ("failed",) and mc in ("yes", "skip"):
        delta["converge"] = "degraded"
    else:
        delta["converge"] = f"{mc}->{rc}"

    # Blank out numeric deltas when either side failed or skipped — values are not meaningful
    if rc in ("failed", "skip") or mc in ("failed", "skip"):
        for k in NUMERIC_KEYS:
            delta[k] = ""
            if k in PCT_KEYS:
                delta[f"{k}_pct"] = ""

    return delta


def print_generic_table(rows, headers, keys):
    """Print a formatted table from a list of dicts."""
    widths = [len(h) for h in headers]
    for r in rows:
        for i, k in enumerate(keys):
            widths[i] = max(widths[i], len(fmt_val(r.get(k, ""))))

    fmt = " | ".join(f"{{:<{w}}}" for w in widths)
    sep = "-+-".join("-" * w for w in widths)

    print(fmt.format(*headers))
    print(sep)
    for r in rows:
        vals = [fmt_val(r.get(k, "")) for k in keys]
        print(fmt.format(*vals))
    print()


def print_comparison(rows, design, output_dir="."):
    """Print interleaved comparison table and delta table for paired runs."""
    pairs = find_pairs(rows, design)
    if not pairs:
        return

    print(f"=== {design} — comparison ===")
    interleaved = []
    all_deltas = []

    for base_id, run_rows, master_rows in pairs:
        # Match by stage_caller, padding the shorter list
        for run_r, master_r in zip_longest(run_rows, master_rows):
            if run_r is None:
                # Run missing this stage (failed earlier)
                run_r = {k: "" for k in KEYS}
                run_r["run"] = base_id
                run_r["stage_caller"] = master_r["stage_caller"]
                run_r["converge"] = "failed"
            if master_r is None:
                # Master missing this stage (failed earlier)
                master_r = {k: "" for k in KEYS}
                master_r["run"] = f"master{base_id}"
                master_r["stage_caller"] = run_r["stage_caller"]
                master_r["converge"] = "failed"
            interleaved.append(run_r)
            interleaved.append(master_r)
            delta = compute_delta(run_r, master_r)
            delta["run"] = f"Δ{base_id}"
            interleaved.append(delta)
            all_deltas.append(delta)
        # Separator row
        interleaved.append({k: "---" for k in KEYS})

    # Remove trailing separator
    if interleaved and all(v == "---" for v in interleaved[-1].values()):
        interleaved.pop()

    print_generic_table(interleaved, HEADERS, KEYS)

    if all_deltas:
        delta_headers = ["run", "stage_caller", "converge?", "start_util", "phase1_iters",
                         "phase2_iters", "displacement", "disp%", "deltaWL", "dWL%", "runtime_s", "rt%"]
        delta_keys = ["run", "stage_caller", "converge", "start_util", "phase1_iters",
                      "phase2_iters", "displacement", "displacement_pct", "deltaWL", "deltaWL_pct", "runtime_s", "runtime_s_pct"]
        print(f"=== {design} — deltas only (run - master) ===")
        print_generic_table(all_deltas, delta_headers, delta_keys)

        # Write delta CSV
        csv_path = os.path.join(output_dir, f"dpl_report_{design}_deltas.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(delta_headers)
            for r in all_deltas:
                writer.writerow([fmt_val(r.get(k, "")) for k in delta_keys])
        print(f"Wrote {csv_path}")


def main():
    logs_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "logs")
    rows = collect_data(logs_dir)

    # Group by design: print table and write CSV
    designs = sorted(set(r["design"] for r in rows))
    output_dir = os.path.dirname(logs_dir) or "."
    for design in designs:
        print(f"=== {design} ===")
        print_table(rows, design)
        write_csv(rows, output_dir, design)
        print_comparison(rows, design, output_dir)

    write_csv(rows, output_dir)


if __name__ == "__main__":
    main()
