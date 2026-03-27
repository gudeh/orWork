#!/usr/bin/env python3
"""Generate DPL (detailed placement legalizer) report tables from OpenROAD JSON logs."""

import csv
import json
import os
import re
import sys
from collections import defaultdict
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


def extract_dpl_runtimes(log_file):
    """Extract runtimes (in seconds) for each detailed_placement call from a log file."""
    runtimes = []
    try:
        with open(log_file) as f:
            for line in f:
                m = re.match(r'.*Took\s+(\d+)\s+seconds:\s+detailed_placement', line)
                if m:
                    runtimes.append(int(m.group(1)))
    except FileNotFoundError:
        pass
    return runtimes


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

        # Extract DPL runtimes from the corresponding .log file
        log_file = json_file.with_suffix(".log")
        runtimes = extract_dpl_runtimes(log_file)

        entries = parse_json_preserve_duplicates(json_file)
        runtime_idx = 0
        for caller in STAGE_CALLERS[stage_key]:
            dpl_calls = extract_dpl_calls(entries, caller)
            for i, call in enumerate(dpl_calls):
                call_label = caller if len(dpl_calls) == 1 else f"{caller}[{i}]"
                runtime = runtimes[runtime_idx] if runtime_idx < len(runtimes) else ""
                runtime_idx += 1
                rows.append({
                    "run": run,
                    "platform": platform,
                    "design": design,
                    "stage_caller": call_label,
                    "start_util": call.get("start_util", ""),
                    "converge": "skip" if call.get("skipped") else "yes" if call.get("converged") else "no" if call.get("converged") is False else "",
                    "phase1_iters": call.get("phase1_iters", "") if call.get("converged") else "",
                    "phase2_iters": call.get("phase2_iters", "") if call.get("converged") else "",
                    "displacement": call.get("displacement", ""),
                    "deltaWL": call.get("deltaWL", ""),
                    "runtime_s": runtime,
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
            widths[i] = max(widths[i], len(str(r[k])))

    fmt = " | ".join(f"{{:<{w}}}" for w in widths)
    sep = "-+-".join("-" * w for w in widths)

    print(fmt.format(*headers))
    print(sep)
    for r in rows:
        print(fmt.format(*[str(r[k]) for k in keys]))
    print()


HEADERS = ["run", "platform", "design", "stage_caller", "start_util",
           "converge?", "phase1_iters", "phase2_iters", "displacement", "deltaWL", "runtime_s"]
KEYS = ["run", "platform", "design", "stage_caller", "start_util",
        "converge", "phase1_iters", "phase2_iters", "displacement", "deltaWL", "runtime_s"]


def write_csv(rows, output_dir, design):
    """Write rows for a design to a CSV file."""
    design_rows = [r for r in rows if r["design"] == design]
    if not design_rows:
        return
    csv_path = os.path.join(output_dir, f"dpl_report_{design}.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        for r in design_rows:
            writer.writerow([r[k] for k in KEYS])
    print(f"Wrote {csv_path}")


def main():
    logs_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "logs")
    rows = collect_data(logs_dir)

    # Group by design: print table and write CSV
    designs = sorted(set(r["design"] for r in rows))
    for design in designs:
        print(f"=== {design} ===")
        print_table(rows, design)
        write_csv(rows, os.path.dirname(logs_dir) or ".", design)


if __name__ == "__main__":
    main()
