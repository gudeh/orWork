import glob
import os
import re
import csv
import zipfile
import json
from collections import defaultdict
import matplotlib.pyplot as plt
import numpy as np

UNZIP_DIR = './unzipped_runs/'


def unzip_runs(base_path, unzip_dir):
    if not os.path.exists(unzip_dir):
        os.makedirs(unzip_dir)
    for file in os.listdir(base_path):
        if file.endswith('.zip'):
            zip_path = os.path.join(base_path, file)
            dest_dir = os.path.join(unzip_dir, os.path.splitext(file)[0])
            if not os.path.exists(dest_dir):
                print(f"Unzipping {file}...")
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(dest_dir)


def collect_log_paths(unzip_dir):
    log_paths = []

    for root, dirs, files in os.walk(unzip_dir):
        path_parts = root.split(os.sep)

        # Match: logs/<platform>/<design>
        if len(path_parts) >= 4 and path_parts[-3] == 'logs':
            run = path_parts[-4]
            platform = path_parts[-2]
            design = path_parts[-1]

            # Find all .log files recursively in this design folder
            all_logs = sorted(glob.glob(os.path.join(root, '**', '*.log'), recursive=True))

            # Target output path: inside base/<design>.log
            base_dir = os.path.join(root, 'base')
            os.makedirs(base_dir, exist_ok=True)
            merged_log_path = os.path.join(base_dir, f"{design}.log")

            # Avoid including the output file itself
            all_logs = [f for f in all_logs if os.path.abspath(f) != os.path.abspath(merged_log_path)]

            if not all_logs:
                continue

            with open(merged_log_path, 'w') as out:
                for log_file in all_logs:
                    with open(log_file, 'r') as src:
                        out.write(src.read())
                        out.write('\n')

            log_paths.append((run, platform, design, merged_log_path))

    return log_paths


def collect_json_paths_and_merge(unzip_dir):
    for root, dirs, files in os.walk(unzip_dir):
        path_parts = root.split(os.sep)

        # Match: logs/<platform>/<design>
        if len(path_parts) >= 4 and path_parts[-3] == 'logs':
            design = path_parts[-1]

            # Find all .json files under this folder recursively
            all_jsons = sorted(glob.glob(os.path.join(root, '**', '*.json'), recursive=True))

            if not all_jsons:
                continue

            base_dir = os.path.join(root, 'base')
            os.makedirs(base_dir, exist_ok=True)
            merged_json_path = os.path.join(base_dir, f"{design}.json")

            merged_data = []

            for json_file in all_jsons:
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            merged_data.extend(data)
                        else:
                            merged_data.append(data)
                except json.JSONDecodeError as e:
                    print(f"Warning: Skipping invalid JSON file {json_file}: {e}")

            with open(merged_json_path, 'w') as out_file:
                json.dump(merged_data, out_file, indent=2)


def process_log_file(log_file_path):
    iteration_number = None
    metadata_status = "ERROR"
    drt_cpu_time = None
    drt_internal_time = None
    first_iteration_violations = None
    gpl_cpu_time = None
    gpl_elapsed_time = None
    internal_gpl_time = None
    last_routability = None
    gpl_iterations = None
    rudy = None

    iteration_pattern = r"(\d+)(st|nd|rd|th) optimization iteration"
    metadata_pass_pattern = "All metadata rules passed"
    metadata_fail_pattern = "Failed metadata check"
    cpu_time_pattern = re.compile(r"\[INFO (DRT-\d{4})\] cpu time = ([0-9]{2}:[0-9]{2}:[0-9]{2})")
    violation_pattern = re.compile(r"Number of violations = (\d+)")
    global_placer_start_pattern = re.compile(r"global place report_design_area")
    cpu_time_global_placer_pattern = re.compile(r"CPU time: user ([0-9.]+)")
    elapsed_time_pattern = re.compile(r"Elapsed time:\s+([0-9:.]+)\[h:\]min:sec")
    routability_pattern = re.compile(r"Routability iteration: (\d+)")
    gpl_iterations_pattern = re.compile(r"\[INFO GPL-\d{4}\]\s+Global placement finished at iteration\s+(\d+)")
    rudy_pattern = re.compile(r"\[INFO GPL-\d{4}\]\s+Routability final weighted congestion:\s+([0-9.]+)")

    # Normal GPL internal time (no -skip_io specifically required)
    internal_gpl_time_pattern = re.compile(r"Took\s+([0-9.]+)\s+seconds:\s+global_placement\b(?!.*-skip_io)")
    # GPL internal time for the -skip_io variant
    internal_gpl_skipio_pattern = re.compile(r"Took\s+([0-9.]+)\s+seconds:\s+global_placement\b.*-skip_io\b")

    # DRT internal time
    internal_drt_time_pattern = re.compile(r"Took\s+([0-9.]+)\s+seconds:\s+detailed_route\b")

    with open(log_file_path, 'r') as file:
        lines = file.readlines()
        in_first_iteration = False

        for line in lines:
            if 'Start 0th optimization iteration.' in line:
                in_first_iteration = True
            elif 'Start' in line and 'optimization iteration' in line and '0th' not in line:
                in_first_iteration = False

            if in_first_iteration and first_iteration_violations is None:
                match = violation_pattern.search(line)
                if match:
                    first_iteration_violations = match.group(1)

        # --- Scan from the end to pick the last-seen values ---
        for line in reversed(lines):
            if iteration_number is None:
                match = re.search(iteration_pattern, line)
                if match:
                    iteration_number = match.group(1)

            if metadata_pass_pattern in line:
                metadata_status = "OK"
            elif metadata_fail_pattern in line:
                metadata_status = "FAIL"

            if drt_cpu_time is None:
                cpu_match = cpu_time_pattern.search(line)
                if cpu_match:
                    h, m, s = map(int, cpu_match.group(2).split(':'))
                    drt_cpu_time = '{:.2f}'.format(h * 60 + m + s / 60.0)

            if last_routability is None:
                match = routability_pattern.search(line)
                if match:
                    last_routability = match.group(1)

            if gpl_iterations is None:
                match = gpl_iterations_pattern.search(line)
                if match:
                    gpl_iterations = match.group(1)

            if rudy is None:
                match = rudy_pattern.search(line)
                if match:
                    rudy = match.group(1)

            if gpl_elapsed_time is None:
                match = elapsed_time_pattern.search(line)
                if match:
                    time_str = match.group(1)
                    parts = time_str.split(":")
                    if len(parts) == 2:  # mm:ss
                        minutes = int(parts[0])
                        seconds = float(parts[1])
                        gpl_elapsed_time = "{:.2f}".format(minutes + seconds / 60.0)
                    elif len(parts) == 3:  # hh:mm:ss
                        hours = int(parts[0])
                        minutes = int(parts[1])
                        seconds = float(parts[2])
                        gpl_elapsed_time = "{:.2f}".format(hours * 60 + minutes + seconds / 60.0)

            # Last seen "normal" GPL internal time (no -skip_io)
            if internal_gpl_time is None:
                match = internal_gpl_time_pattern.search(line)
                if match:
                    seconds = float(match.group(1))
                    internal_gpl_time = "{:.2f}".format(seconds / 60.0)

            if drt_internal_time is None:
                match = internal_drt_time_pattern.search(line)
                if match:
                    seconds = float(match.group(1))
                    drt_internal_time = "{:.2f}".format(seconds / 60.0)

        # --- Accumulate any -skip_io GPL internal times (can be multiple) ---
        skipio_seconds = 0.0
        for line in lines:
            m = internal_gpl_skipio_pattern.search(line)
            if m:
                skipio_seconds += float(m.group(1))

        # If we have a normal GPL internal time, add the -skip_io component to it
        if internal_gpl_time is not None and skipio_seconds > 0.0:
            base_minutes = float(internal_gpl_time)
            internal_gpl_time = "{:.2f}".format(base_minutes + (skipio_seconds / 60.0))

        # GPL CPU time (scan forward after entering GPL section)
        in_global_placer_section = False
        for line in lines:
            if global_placer_start_pattern.search(line):
                in_global_placer_section = True
            elif in_global_placer_section:
                match = cpu_time_global_placer_pattern.search(line)
                if match:
                    seconds = float(match.group(1))
                    gpl_cpu_time = '{:.2f}'.format(seconds / 60)
                    break

    return (
        iteration_number,
        metadata_status,
        drt_cpu_time,
        drt_internal_time,
        gpl_cpu_time,
        gpl_elapsed_time,
        internal_gpl_time,
        last_routability,
        first_iteration_violations,
        gpl_iterations,
        rudy,
    )


def aggregate_data(log_paths):
    data = defaultdict(lambda: defaultdict(lambda: {
        '0th DRT Iteration Violations': None,
        'DRT Iterations': None,
        'Status': None,
        'DRT CPU Time': None,
        'DRT internal time': None,
        'GPL CPU Time': None,
        'GPL Elapsed Time': None,
        'internal GPL time': None,
        'Routability iters': None,
        'GPL iterations': None,
        'RUDY': None,
        'DPL JSON Wirelength': None,
        'GPL JSON inst count': None,
        'Finish TNS': None,
        'finish__timing__fmax': None                # NEW
    }))
    for run, platform, design, log_path in log_paths:
        vals = process_log_file(log_path)

        # Look for the JSON file in the same base directory
        json_path = os.path.join(os.path.dirname(log_path), f"{design}.json")
        wirelength, finish_tns, inst_count, wns_pct, fmax = extract_metrics_from_json(json_path)

        data[(design, platform)][run] = {
            '0th DRT Iteration Violations': vals[8],
            'DRT Iterations': vals[0],
            'Status': vals[1],
            'DRT CPU Time': vals[2],
            'DRT internal time': vals[3],
            'GPL CPU Time': vals[4],
            'GPL Elapsed Time': vals[5],
            'internal GPL time': vals[6],
            'Routability iters': vals[7],
            'GPL iterations': vals[9],
            'RUDY': vals[10],
            'DPL JSON Wirelength': wirelength,
            'GPL JSON inst count': inst_count,
            'Finish TNS': finish_tns,
            'finish__timing__fmax': fmax                    # NEW
        }
    return data

def extract_metrics_from_json(json_path):
    wirelength = None
    finish_tns = None
    inst_count = None
    wns_percent_delay = None
    fmax = None
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)

            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict):
                        if wirelength is None and "detailedplace__route__wirelength__estimated" in entry:
                            wirelength = entry["detailedplace__route__wirelength__estimated"]
                        if finish_tns is None and "finish__timing__setup__tns" in entry:
                            finish_tns = entry["finish__timing__setup__tns"]
                        if inst_count is None and "globalplace__design__instance__count" in entry:
                            inst_count = entry["globalplace__design__instance__count"]
                        if fmax is None and "finish__timing__fmax" in entry:
                            fmax = entry["finish__timing__fmax"]
                        if (wirelength is not None and finish_tns is not None and
                                inst_count is not None and wns_percent_delay is not None and fmax is not None):
                            break
            elif isinstance(data, dict):
                wirelength = data.get("detailedplace__route__wirelength__estimated")
                finish_tns = data.get("finish__timing__setup__tns")
                inst_count = data.get("globalplace__design__instance__count")
                fmax = data.get("finish__timing__fmax")

    except Exception as e:
        print(f"Failed to parse JSON from {json_path}: {e}")

    return wirelength, finish_tns, inst_count, wns_percent_delay, fmax


def write_to_csv(data, output_file):
    with open(output_file, 'w', newline='') as file:
        writer = csv.writer(file)
        run_configs = sorted({rc for d in data.values() for rc in d})

        # First header row: run names repeated (now 16 metrics per run)
        writer.writerow([''] * 3 + [rc for rc in run_configs for _ in range(16)])

        # Second header row (order preserved, with GPL iterations before Routability iters)
        writer.writerow(['Design Name', 'Technology', 'Name'] + [
            '0th DRT Iteration Violations',
            'DRT Iterations',
            'Status',
            'DRT CPU Time',
            'DRT internal time',
            'GPL CPU Time',
            'GPL Elapsed Time',
            'internal GPL time',
            'GPL iterations',
            'Routability iters',
            'RUDY',
            'DPL JSON Wirelength',
            'GPL JSON inst count',
            'Finish TNS',
            'finish__timing__fmax'                # NEW
        ] * len(run_configs))

        # Data rows
        for (design, tech), runs in data.items():
            name_val = f"{tech}/{design}"
            row = [design, tech, name_val]
            for rc in run_configs:
                info = runs.get(rc, {})
                row.extend([
                    info.get('0th DRT Iteration Violations', ''),
                    info.get('DRT Iterations', ''),
                    info.get('Status', ''),
                    info.get('DRT CPU Time', ''),
                    info.get('DRT internal time', ''),
                    info.get('GPL CPU Time', ''),
                    info.get('GPL Elapsed Time', ''),
                    info.get('internal GPL time', ''),
                    info.get('GPL iterations', ''),
                    info.get('Routability iters', ''),
                    info.get('RUDY', ''),
                    info.get('DPL JSON Wirelength', ''),
                    info.get('GPL JSON inst count', ''),
                    info.get('Finish TNS', ''),
                    info.get('finish__timing__fmax', '')                # NEW
                ])
            writer.writerow(row)


def save_plots(data, out_dir="plots", clip_pct=0):
    import os
    import numpy as np
    import matplotlib.pyplot as plt

    os.makedirs(out_dir, exist_ok=True)

    # Improved helper: returns None if missing, ensuring we don't plot 0.0 for missing data
    def get_valid_val(val):
        if val in (None, ""):
            return None
        try:
            return float(val)
        except ValueError:
            return None

    def clip_symmetric(y, pct):
        # Filter out NaNs before calculating percentiles
        valid_y = y[~np.isnan(y)]
        if pct is None or pct <= 0 or len(valid_y) == 0:
            return None
        lo, hi = np.percentile(valid_y, [pct, 100 - pct])
        lim = max(abs(lo), abs(hi))
        return (-lim, lim) if lim > 0 else None

    def stats_text(arr, fmt="{:+.2f}"):
        # Filter out NaNs for stats calculation
        valid_arr = arr[~np.isnan(arr)]
        if len(valid_arr) == 0:
            return ""
        mean = np.mean(valid_arr)
        median = np.median(valid_arr)
        std = np.std(valid_arr)
        return f"mean={fmt.format(mean)}, median={fmt.format(median)}, std={fmt.format(std)}"

    # ---------- collect diffs (other - master) ----------
    gpl_time, gpl_iters = {}, {}
    rudy, drt_iters, drt0_pct, drt_internal = {}, {}, {}, {}
    wirelength_pct, finish_tns_pct, fmax_pct = {}, {}, {}

    for (design, tech), runs in data.items():
        if len(runs) == 2 and "master" in runs:
            other = next(r for r in runs if r != "master")
            name = f"{tech}/{design}"

            # Helper to safely get vars
            m_data = runs["master"]
            o_data = runs[other]

            # --- GPL ---
            m_gpl_t = get_valid_val(m_data.get("internal GPL time"))
            o_gpl_t = get_valid_val(o_data.get("internal GPL time"))
            if m_gpl_t is not None and o_gpl_t is not None:
                gpl_time[name] = ((o_gpl_t - m_gpl_t) / max(m_gpl_t, 1.0)) * 100.0

            m_gpl_i = get_valid_val(m_data.get("GPL iterations"))
            o_gpl_i = get_valid_val(o_data.get("GPL iterations"))
            if m_gpl_i is not None and o_gpl_i is not None:
                gpl_iters[name] = ((o_gpl_i - m_gpl_i) / max(m_gpl_i, 1.0)) * 100.0

            # --- RUDY / DRT ---
            m_rudy = get_valid_val(m_data.get("RUDY"))
            o_rudy = get_valid_val(o_data.get("RUDY"))
            if m_rudy is not None and o_rudy is not None:
                rudy[name] = o_rudy - m_rudy

            m_drt_i = get_valid_val(m_data.get("DRT Iterations"))
            o_drt_i = get_valid_val(o_data.get("DRT Iterations"))
            if m_drt_i is not None and o_drt_i is not None:
                drt_iters[name] = o_drt_i - m_drt_i

            m_v0 = get_valid_val(m_data.get("0th DRT Iteration Violations"))
            o_v0 = get_valid_val(o_data.get("0th DRT Iteration Violations"))
            if m_v0 is not None and o_v0 is not None:
                drt0_pct[name] = ((o_v0 - m_v0) / max(m_v0, 1.0)) * 100.0

            m_drt_t = get_valid_val(m_data.get("DRT internal time"))
            o_drt_t = get_valid_val(o_data.get("DRT internal time"))
            if m_drt_t is not None and o_drt_t is not None:
                # Calculating diff here, not %
                drt_internal[name] = o_drt_t - m_drt_t

            # --- Wirelength / Timing ---
            m_wl = get_valid_val(m_data.get("DPL JSON Wirelength"))
            o_wl = get_valid_val(o_data.get("DPL JSON Wirelength"))
            if m_wl is not None and o_wl is not None:
                wirelength_pct[name] = ((o_wl - m_wl) / max(m_wl, 1.0)) * 100.0

            m_tns = get_valid_val(m_data.get("Finish TNS"))
            o_tns = get_valid_val(o_data.get("Finish TNS"))
            if m_tns is not None and o_tns is not None:
                finish_tns_pct[name] = ((o_tns - m_tns) / max(abs(m_tns), 1.0)) * 100.0

            m_fmax = get_valid_val(m_data.get("finish__timing__fmax"))
            o_fmax = get_valid_val(o_data.get("finish__timing__fmax"))
            if m_fmax is not None and o_fmax is not None:
                fmax_pct[name] = ((o_fmax - m_fmax) / max(m_fmax, 1.0)) * 100.0

    # ---------- Figure 1: GPL runtime ----------
    gpl_designs = [d for d in gpl_time if abs(gpl_time[d]) > 1e-12]
    if gpl_designs:
        gpl_designs.sort(key=lambda d: gpl_time[d], reverse=True)
        x = np.arange(len(gpl_designs))
        
        # Use np.nan for missing values so they don't plot as 0
        y1 = np.array([gpl_time.get(d, np.nan) for d in gpl_designs])
        y2 = np.array([gpl_iters.get(d, np.nan) for d in gpl_designs])

        fig, axs = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

        lim1 = clip_symmetric(y1, clip_pct)
        axs[0].scatter(x, y1, s=28, color="#4e79a7", edgecolor="black", linewidths=0.5)
        axs[0].axhline(0, color="black", lw=0.8, ls="--")
        axs[0].set_ylabel("Internal GPL time (%diff)")
        if lim1: axs[0].set_ylim(*lim1)
        axs[0].grid(True, axis="y", alpha=0.2)
        axs[0].text(0.99, 0.98, stats_text(y1), ha="right", va="top", transform=axs[0].transAxes,
                    fontsize=11, bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))

        lim2 = clip_symmetric(y2, clip_pct)
        axs[1].scatter(x, y2, s=28, color="#f28e2b", edgecolor="black", linewidths=0.5)
        axs[1].axhline(0, color="black", lw=0.8, ls="--")
        axs[1].set_ylabel("GPL iterations (%diff)")
        if lim2: axs[1].set_ylim(*lim2)
        axs[1].grid(True, axis="y", alpha=0.2)
        axs[1].text(0.99, 0.98, stats_text(y2), ha="right", va="top", transform=axs[1].transAxes,
                    fontsize=11, bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))

        axs[1].set_xticks(x)
        axs[1].set_xticklabels(gpl_designs)
        for lbl in axs[1].get_xticklabels():
            lbl.set_rotation(60)
            lbl.set_ha("right")

        fig.suptitle("GPL runtime", y=0.995)
        fig.subplots_adjust(bottom=0.28, hspace=0.18)
        out_png = os.path.join(out_dir, "GPL_runtime.png")
        fig.savefig(out_png, dpi=150, bbox_inches=None)
        plt.close(fig)
        print(f"Saved plot: {out_png}")
    else:
        print("No designs with non-zero Internal GPL time diff to plot.")

    # ---------- Figure 2: Routability ----------
    if drt0_pct:
        designs = sorted(drt0_pct.keys(), key=lambda d: drt0_pct[d], reverse=True)
        x = np.arange(len(designs))
        
        # Use np.nan if key is missing
        y_rudy   = np.array([rudy[d] if d in rudy else np.nan for d in designs])
        y_iters  = np.array([drt_iters[d] if d in drt_iters else np.nan for d in designs])
        y_v0pct  = np.array([drt0_pct[d] if d in drt0_pct else np.nan for d in designs])
        
        # Recalculate DRT internal time pct diff here to handle missing values safely
        y_drtint_pct = []
        for d in designs:
            # Need to re-access raw data because drt_internal dict stores ABS diff, 
            # but the plot usually wants % diff, or consistent logic.
            # Based on previous logic, let's stick to what we stored:
            # We stored ABS diff in `drt_internal`. 
            # If you want % diff for the plot:
            parts = d.split('/') # tech/design
            run_key = (parts[1], parts[0]) 
            runs = data.get(run_key)
            val = np.nan
            if runs:
                 other = next((r for r in runs if r != "master"), None)
                 if other:
                     m_t = get_valid_val(runs["master"].get("DRT internal time"))
                     o_t = get_valid_val(runs[other].get("DRT internal time"))
                     if m_t is not None and o_t is not None:
                         val = ((o_t - m_t) / max(m_t, 1.0)) * 100.0
            y_drtint_pct.append(val)
        y_drtint_pct = np.array(y_drtint_pct)

        fig, axs = plt.subplots(4, 1, figsize=(14, 12), sharex=True)

        # Panel 1: RUDY
        lim = clip_symmetric(y_rudy, clip_pct)
        axs[0].scatter(x, y_rudy, s=28, color="#4e79a7", edgecolor="black", linewidths=0.5)
        axs[0].axhline(0, color="black", lw=0.8, ls="--")
        axs[0].set_ylabel("RUDY (abs-diff)")
        if lim: axs[0].set_ylim(*lim)
        axs[0].grid(True, axis="y", alpha=0.2)
        axs[0].text(0.99, 0.98, stats_text(y_rudy), ha="right", va="top", transform=axs[0].transAxes,
                    fontsize=11, bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))

        # Panel 2: DRT Iters
        lim = clip_symmetric(y_iters, clip_pct)
        axs[1].scatter(x, y_iters, s=28, color="#f28e2b", edgecolor="black", linewidths=0.5)
        axs[1].axhline(0, color="black", lw=0.8, ls="--")
        axs[1].set_ylabel("DRT iters (abs-diff)")
        if lim: axs[1].set_ylim(*lim)
        axs[1].grid(True, axis="y", alpha=0.2)
        axs[1].text(0.99, 0.98, stats_text(y_iters), ha="right", va="top", transform=axs[1].transAxes,
                    fontsize=11, bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))

        # Panel 3: Violations
        lim = clip_symmetric(y_v0pct, clip_pct)
        axs[2].scatter(x, y_v0pct, s=28, color="#59a14f", edgecolor="black", linewidths=0.5, marker="x")
        axs[2].axhline(0, color="black", lw=0.8, ls="--")
        axs[2].set_ylabel("0th viol. (%diff)")
        if lim: axs[2].set_ylim(*lim)
        axs[2].grid(True, axis="y", alpha=0.2)
        axs[2].text(0.99, 0.98, stats_text(y_v0pct), ha="right", va="top", transform=axs[2].transAxes,
                    fontsize=11, bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))

        # Panel 4: DRT Time
        lim = clip_symmetric(y_drtint_pct, clip_pct)
        axs[3].scatter(x, y_drtint_pct, s=28, color="#9c755f", edgecolor="black", linewidths=0.5)
        axs[3].axhline(0, color="black", lw=0.8, ls="--")
        axs[3].set_ylabel("DRT internal time (%diff)")
        if lim: axs[3].set_ylim(*lim)
        axs[3].grid(True, axis="y", alpha=0.2)
        axs[3].text(0.99, 0.98, stats_text(y_drtint_pct), ha="right", va="top", transform=axs[3].transAxes,
                fontsize=11, bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))

        axs[3].set_xticks(x)
        axs[3].set_xticklabels(designs)
        for lbl in axs[3].get_xticklabels():
            lbl.set_rotation(60)
            lbl.set_ha("right")

        fig.suptitle("Routability metrics", y=0.995)
        fig.subplots_adjust(bottom=0.28, hspace=0.18)
        out_png = os.path.join(out_dir, "Routability_metrics.png")
        fig.savefig(out_png, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"Saved plot: {out_png}")
    else:
        print("No DRT data to plot.")

    # ---------- Figure 3: Wirelength and timing ----------
    if wirelength_pct:
        designs = sorted(wirelength_pct.keys(), key=lambda d: wirelength_pct[d], reverse=True)
        x = np.arange(len(designs))
        
        y_wl   = np.array([wirelength_pct.get(d, np.nan) for d in designs])
        y_tns  = np.array([finish_tns_pct.get(d, np.nan) for d in designs])
        y_fmax = np.array([fmax_pct.get(d, np.nan) for d in designs])

        fig, axs = plt.subplots(3, 1, figsize=(14, 9), sharex=True)

        axs[0].scatter(x, y_wl, s=28, color="#e15759", edgecolor="black", linewidths=0.5)
        axs[0].axhline(0, color="black", lw=0.8, ls="--")
        axs[0].set_ylabel("DPL Wirelength (%diff)")
        axs[0].set_ylim(-100, 100) 
        axs[0].grid(True, axis="y", alpha=0.2)
        axs[0].text(0.99, 0.98, stats_text(y_wl), ha="right", va="top", transform=axs[0].transAxes,
                    fontsize=11, bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))

        axs[1].scatter(x, y_tns, s=28, color="#76b7b2", edgecolor="black", linewidths=0.5)
        axs[1].axhline(0, color="black", lw=0.8, ls="--")
        axs[1].set_ylabel("finish setup tns (%diff)")
        axs[1].set_ylim(-100, 100) 
        axs[1].grid(True, axis="y", alpha=0.2)
        axs[1].text(0.99, 0.98, stats_text(y_tns), ha="right", va="top", transform=axs[1].transAxes,
                    fontsize=11, bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))

        axs[2].scatter(x, y_fmax, s=28, color="#b07aa1", edgecolor="black", linewidths=0.5)
        axs[2].axhline(0, color="black", lw=0.8, ls="--")
        axs[2].set_ylabel("finish fmax (%diff)")
        axs[2].set_ylim(-100, 100) 
        axs[2].grid(True, axis="y", alpha=0.2)
        axs[2].text(0.99, 0.98, stats_text(y_fmax), ha="right", va="top", transform=axs[2].transAxes,
                    fontsize=11, bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))

        axs[2].set_xticks(x)
        axs[2].set_xticklabels(designs)
        for lbl in axs[2].get_xticklabels():
            lbl.set_rotation(60)
            lbl.set_ha("right")

        fig.suptitle("Wirelength and timing", y=0.995)
        fig.subplots_adjust(bottom=0.28, hspace=0.18)
        out_png = os.path.join(out_dir, "WL_timing.png")
        fig.savefig(out_png, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"Saved plot: {out_png}")
    else:
        print("No Wirelength/TNS/fmax data to plot.")



if __name__ == "__main__":
    base_path = '.'  # current dir with .zip files
    unzip_runs(base_path, UNZIP_DIR)
    logs = collect_log_paths(UNZIP_DIR)
    collect_json_paths_and_merge(UNZIP_DIR)
    data = aggregate_data(logs)
    write_to_csv(data, 'output.csv')

    save_plots(data)

    
