#!/usr/bin/env python3
"""Generate DPL (detailed placement legalizer) report tables from OpenROAD JSON logs.

Usage
-----
Mode 1 — logs/ directory (default):
  python 3dpl_report.py [/path/to/logs]

  Expected structure:
    <logs_dir>/<platform>/<design>/<run>/<stage>.json
    <logs_dir>/<platform>/<design>/<run>/<stage>.log

  Master pairing: runs named 'master<N>' are paired against runs named '<N>'.
  CSV and comparison tables are written next to <logs_dir>.

Mode 2 — zip files (one or more .zip arguments, or a directory containing them):
  python 3dpl_report.py master.zip branch.zip [...]
  python 3dpl_report.py /path/to/dir/with/zips/

  Each zip must contain a logs/ directory at its root with the structure:
    logs/<platform>/<design>/<run>/<stage>.json
    logs/<platform>/<design>/<run>/<stage>.log

  The zip filename stem becomes the run label (e.g. master.zip → 'master').
  A zip named 'master.zip' is the baseline for all comparisons.
  CSV and comparison tables are written next to the first zip file.

Mode 3 — sibling directories (no logs/ found and no explicit path given):
  cd /some/dir && python /path/to/3dpl_report.py

  Expected structure:
    <cwd>/master/<platform>/<design>/<run>/<stage>.json   <- baseline
    <cwd>/run51/<platform>/<design>/<run>/<stage>.json    <- candidate
    ...

  Each immediate subdirectory of cwd is treated as a separate labeled run.
  A subdirectory literally named 'master' is the baseline for all comparisons.
  CSV and comparison tables are written to cwd.
"""

import csv
import json
import os
import re
import sys
import tempfile
import zipfile
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
            if suffix == "negotiation__converge__phase_1__iteration":
                current["converged"] = True
                current["phase1_iters"] = val
            elif suffix == "negotiation__converge__phase_2__iteration":
                current["phase2_iters"] = val
            elif suffix == "negotiation__no__converge__final_violations":
                current["converged"] = False
            elif suffix == "dpl__instance__displacement__total":
                current["displacement"] = val
            elif suffix == "dpl__total__moves":
                current["total_moves"] = val
            elif suffix == "dpl__hpwl__delta__percent":
                current["deltaWL"] = val

    if current is not None:
        calls.append(current)

    # Mark calls that had no legalization (displacement 0, no convergence info)
    for call in calls:
        if "converged" not in call and call.get("displacement", None) == 0:
            call["skipped"] = True

    return calls


def extract_dpo_data(entries, caller):
    """Extract DPO (improve_placement) metrics for a given caller.

    Returns a dict with DPO fields, or empty dict if DPO did not run.
    """
    prefix = f"{caller}__dpo__"
    dpo = {}
    for key, val in entries:
        if not key.startswith(prefix):
            continue
        suffix = key[len(prefix):]
        if suffix == "total__attempts":
            dpo["dpo_attempts"] = val
        elif suffix == "relocated__cells":
            dpo["dpo_relocated"] = val
        elif suffix == "design__instance__displacement__total":
            dpo["dpo_displacement"] = val
        elif suffix == "design__instance__displacement__mean":
            dpo["dpo_disp_avg"] = val
        elif suffix == "design__instance__displacement__max":
            dpo["dpo_disp_max"] = val
        elif suffix == "hpwl__delta__percent":
            dpo["dpo_deltaWL"] = val
    return dpo


# Determine which callers can appear in which stage files
STAGE_CALLERS = {
    "place_dp": ["detailedplace"],
    "cts": ["cts"],
    "grt": ["globalroute"],
}


def extract_dpl_log_info(log_file):
    """Extract runtimes, errors, and legalizer type for each DPL call from a log file.

    Detects both explicit Tcl calls (preceded by 'detailed_placement' command echo)
    and internal C++ calls (repair_antennas, GRT congestion) which only emit
    DPL-1101/1102 log lines with no command echo or runtime.

    Returns list of dicts with 'runtime', 'error', and 'legalizer' keys per DPL call.
    'legalizer' is 'negotiation' (DPL-1102) or 'diamond' (DPL-1101).
    """
    calls = []
    current = None
    pending_tcl = False  # saw a "detailed_placement" command echo before next DPL block
    try:
        with open(log_file) as f:
            for line in f:
                if re.search(r'^detailed_placement\b', line):
                    pending_tcl = True
                elif re.search(r'\[INFO DPL-110[12]\]', line):
                    if current is not None:
                        calls.append(current)
                    legalizer = "negotiation" if "DPL-1102" in line else "diamond"
                    current = {"runtime": "", "error": False, "legalizer": legalizer}
                    pending_tcl = False
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


def collect_data(logs_dir, run_label=None):
    """Walk logs_dir and collect all DPL call records.

    If run_label is given it overrides the run directory name in the path,
    used when each top-level sibling directory is itself a logs root.
    """
    rows = []
    logs_path = Path(logs_dir)

    for json_file in sorted(logs_path.rglob("*.json")):
        # Parse path: [platform]/[design]/[run]/[stage].json
        rel = json_file.relative_to(logs_path)
        parts = rel.parts
        if len(parts) != 4:
            continue
        platform, design, run, stage_file = parts
        if run_label is not None:
            run = run_label
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
            dpo = extract_dpo_data(entries, caller)
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
                # DPO runs once per stage after all DPL calls; attach to last call only
                is_last = (i == len(dpl_calls) - 1)
                rows.append({
                    "run": run,
                    "platform": platform,
                    "design": design,
                    "stage_caller": call_label,
                    "legalizer": info.get("legalizer", ""),
                    "start_util": call.get("start_util", ""),
                    "converge": converge,
                    "phase1_iters": call.get("phase1_iters", ""),
                    "phase2_iters": call.get("phase2_iters", ""),
                    "dpl_moves": call.get("total_moves", ""),
                    "dpl_disp": call.get("displacement", ""),
                    "dpl_deltaWL": call.get("deltaWL", ""),
                    "runtime_s": info.get("runtime", ""),
                    "dpo_attempts": dpo.get("dpo_attempts", "") if is_last else "",
                    "dpo_relocated": dpo.get("dpo_relocated", "") if is_last else "",
                    "dpo_displacement": dpo.get("dpo_displacement", "") if is_last else "",
                    "dpo_deltaWL": dpo.get("dpo_deltaWL", "") if is_last else "",
                })
    return rows


def print_table(rows, design=None):
    """Print a formatted table for the given rows."""
    if design:
        rows = [r for r in rows if r["design"] == design]
    if not rows:
        return

    headers = HEADERS
    keys = KEYS

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


HEADERS = ["run", "platform", "design", "stage_caller", "legalizer", "start_util",
           "converge?", "phase1_iters", "phase2_iters", "dpl_moves", "dpl_disp", "dpl_deltaWL%", "runtime_s",
           "dpo_attempts", "dpo_relocated", "dpo_disp", "dpo_deltaWL%"]
KEYS = ["run", "platform", "design", "stage_caller", "legalizer", "start_util",
        "converge", "phase1_iters", "phase2_iters", "dpl_moves", "dpl_disp", "dpl_deltaWL", "runtime_s",
        "dpo_attempts", "dpo_relocated", "dpo_displacement", "dpo_deltaWL"]


def write_csv(rows, output_dir, design=None):
    """Write rows to a CSV file. If design is given, filters to that design."""
    if design is not None:
        rows = [r for r in rows if r["design"] == design]
        filename = f"dpl_report_{design}.csv"
    else:
        filename = "0dpl_report_all.csv"
    if not rows:
        return
    csv_path = os.path.join(output_dir, filename)
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        for r in rows:
            writer.writerow([fmt_val(r[k]) for k in KEYS])
    print(f"Wrote {csv_path}")


NUMERIC_KEYS = ["start_util", "phase1_iters", "phase2_iters", "dpl_moves", "dpl_disp", "dpl_deltaWL", "runtime_s",
                "dpo_attempts", "dpo_relocated", "dpo_displacement", "dpo_deltaWL"]


def fmt_val(v):
    """Format a value for display: 1 decimal for floats, plain for ints/strings."""
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)
PCT_KEYS = ["dpl_disp", "dpl_deltaWL", "runtime_s",
            "dpo_attempts", "dpo_relocated", "dpo_displacement", "dpo_deltaWL"]


def parse_run_id(run):
    """Return (base_id, is_master) for a run name like '51' or 'master51'."""
    m = re.match(r'^master(\d+.*)$', run)
    if m:
        return m.group(1), True
    return run, False


def find_pairs(rows, design):
    """Find (run, master_run) pairs for a design.

    Supports two pairing modes:
    - Named master: a run literally named 'master' is paired against all others.
    - Prefixed master: runs named 'master<N>' are paired against run '<N>'.

    Returns list of (base_id, run_rows, master_rows) sorted by base_id.
    """
    design_rows = [r for r in rows if r["design"] == design]
    groups = defaultdict(list)
    for r in design_rows:
        groups[r["run"]].append(r)

    run_names = sorted(groups.keys())

    # Named-master mode: one run is literally called 'master'
    if "master" in run_names:
        master_rows = groups["master"]
        pairs = []
        for name in run_names:
            if name == "master":
                continue
            pairs.append((name, groups[name], master_rows))
        return pairs

    # Prefixed-master mode: 'master<N>' pairs with '<N>'
    groups2 = defaultdict(list)
    for r in design_rows:
        base_id, is_master = parse_run_id(r["run"])
        groups2[(base_id, is_master)].append(r)

    base_ids = sorted({base_id for base_id, _ in groups2})
    pairs = []
    for base_id in base_ids:
        run_rows = groups2.get((base_id, False), [])
        master_rows = groups2.get((base_id, True), [])
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
    delta["platform"] = run_row.get("platform", "")
    delta["design"] = run_row.get("design", "")
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
    """Print interleaved comparison table and delta table for paired runs.

    Returns list of delta rows for the design (may be empty).
    """
    pairs = find_pairs(rows, design)
    if not pairs:
        return []

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
        delta_headers = ["run", "platform", "design", "stage_caller", "converge?", "start_util", "phase1_iters",
                         "phase2_iters", "dpl_moves", "dpl_disp", "dpl_disp%", "dpl_deltaWL%", "dWL%", "runtime_s", "rt%",
                         "dpo_attempts", "dpo_att%", "dpo_relocated", "dpo_rel%", "dpo_disp", "dpo_disp%", "dpo_deltaWL%", "dDWL%"]
        delta_keys = ["run", "platform", "design", "stage_caller", "converge", "start_util", "phase1_iters",
                      "phase2_iters", "dpl_moves", "dpl_disp", "dpl_disp_pct", "dpl_deltaWL", "dpl_deltaWL_pct", "runtime_s", "runtime_s_pct",
                      "dpo_attempts", "dpo_attempts_pct", "dpo_relocated", "dpo_relocated_pct", "dpo_displacement", "dpo_displacement_pct", "dpo_deltaWL", "dpo_deltaWL_pct"]
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

    return all_deltas


def main():
    cwd = Path.cwd()
    args = sys.argv[1:]

    # Resolve a single directory arg to the zip files inside it
    if len(args) == 1 and Path(args[0]).is_dir():
        zip_files = sorted(Path(args[0]).glob("*.zip"))
        if zip_files:
            args = [str(z) for z in zip_files]

    if args and all(a.endswith(".zip") for a in args):
        # Zip mode — extract each to a temp dir, use stem as run label
        output_dir = Path(args[0]).parent
        for csv_file in output_dir.glob("*.csv"):
            csv_file.unlink()
            print(f"Removed {csv_file}")
        rows = []
        with tempfile.TemporaryDirectory() as tmpdir:
            for zip_arg in args:
                zip_path = Path(zip_arg)
                run_label = zip_path.stem
                extract_root = Path(tmpdir) / run_label
                with zipfile.ZipFile(zip_path) as z:
                    z.extractall(extract_root)
                logs_subdir = extract_root / "logs"
                source = logs_subdir if logs_subdir.is_dir() else extract_root
                rows.extend(collect_data(source, run_label=run_label))
    elif args:
        # Explicit logs directory path
        logs_dir = Path(args[0])
        output_dir = logs_dir.parent
        for csv_file in output_dir.glob("*.csv"):
            csv_file.unlink()
            print(f"Removed {csv_file}")
        rows = collect_data(logs_dir)
    elif (cwd / "logs").is_dir():
        # Mode 1: logs/ subdir found in cwd
        logs_dir = cwd / "logs"
        output_dir = cwd
        for csv_file in output_dir.glob("*.csv"):
            csv_file.unlink()
            print(f"Removed {csv_file}")
        rows = collect_data(logs_dir)
    else:
        # Mode 3: scan cwd subdirs, each is a labeled logs root
        output_dir = cwd
        for csv_file in output_dir.glob("*.csv"):
            csv_file.unlink()
            print(f"Removed {csv_file}")
        subdirs = sorted(p for p in cwd.iterdir() if p.is_dir())
        rows = []
        for subdir in subdirs:
            rows.extend(collect_data(subdir, run_label=subdir.name))

    # Group by design: print table and write CSV
    designs = sorted(set(r["design"] for r in rows))
    all_deltas = []
    for design in designs:
        print(f"=== {design} ===")
        print_table(rows, design)
        write_csv(rows, str(output_dir), design)
        all_deltas.extend(print_comparison(rows, design, str(output_dir)))

    write_csv(rows, str(output_dir))

    # Write all-deltas CSV
    if all_deltas:
        delta_headers = ["run", "platform", "design", "stage_caller", "converge?", "start_util", "phase1_iters",
                         "phase2_iters", "dpl_moves", "dpl_disp", "dpl_disp%", "dpl_deltaWL%", "dWL%", "runtime_s", "rt%",
                         "dpo_attempts", "dpo_att%", "dpo_relocated", "dpo_rel%", "dpo_disp", "dpo_disp%", "dpo_deltaWL%", "dDWL%"]
        delta_keys = ["run", "platform", "design", "stage_caller", "converge", "start_util", "phase1_iters",
                      "phase2_iters", "dpl_moves", "dpl_disp", "dpl_disp_pct", "dpl_deltaWL", "dpl_deltaWL_pct", "runtime_s", "runtime_s_pct",
                      "dpo_attempts", "dpo_attempts_pct", "dpo_relocated", "dpo_relocated_pct", "dpo_displacement", "dpo_displacement_pct", "dpo_deltaWL", "dpo_deltaWL_pct"]
        csv_path = os.path.join(str(output_dir), "0dpl_report_all_deltas.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(delta_headers)
            for r in all_deltas:
                writer.writerow([fmt_val(r.get(k, "")) for k in delta_keys])
        print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
