import shutil
import os
import zipfile
import re
import csv
import matplotlib.pyplot as plt

UNZIP_DIR = './unzipped_runs/'
OUTPUT_DIRS = {
    "3_3_place_gp.log": "./plots/3_3/",
    "3_1_place_gp_skip_io.log": "./plots/3_1/"
}
CSV_SUMMARY = 'summary.csv'

def extract_starting_overflow(log_path):
    with open(log_path, 'r') as file:
        lines = file.readlines()

    for i, line in enumerate(lines):
        if re.match(r'^-+\s*$', line):
            for j in range(i+1, len(lines)):
                if re.match(r'^\s*1\s*\|\s*([\d.]+)', lines[j]):
                    match = re.search(r'^\s*1\s*\|\s*([\d.]+)', lines[j])
                    if match:
                        return float(match.group(1))
                    break
            break
    return None


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

def collect_gp_log_paths(unzip_dir, log_filename):
    log_paths = []
    for root, _, files in os.walk(unzip_dir):
        for file in files:
            if file == log_filename:
                path_parts = root.split(os.sep)
                if len(path_parts) >= 3:
                    platform = path_parts[-3]
                    design = path_parts[-2]
                    stage = "_".join(file.split("_")[:2])
                    log_paths.append(((platform, design, stage), os.path.join(root, file)))
    return log_paths

def extract_gp_data_and_events(log_path):
    data = []
    events = []

    table_pattern = re.compile(
        r"^\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*([\d.eE\+\-]+)\s*\|\s*[\+\-]?[\d.]+%\s*\|\s*([\d.eE\+\-]+)"
    )
    timing_iter_pattern = re.compile(r"Timing-driven iteration.*virtual:\s*(true|false)")
    actual_iter_pattern = re.compile(r"\[INFO GPL-0101\]\s+Iter:\s*(\d+)")
    routability_pattern = re.compile(r"^\[INFO GPL-0040\] Routability iteration")

    with open(log_path, 'r') as file:
        lines = file.readlines()

    pending_timing_type = None

    for i, line in enumerate(lines):
        match = table_pattern.match(line)
        if match:
            iter_num = int(match.group(1))
            overflow = float(match.group(2))
            hpwl = float(match.group(3))
            penalty = float(match.group(4))
            data.append((iter_num, overflow, hpwl, penalty))

        if routability_pattern.search(line):
            for j in range(i - 1, -1, -1):
                m = table_pattern.match(lines[j])
                if m:
                    events.append((int(m.group(1)), "routability"))
                    break

        timing_match = timing_iter_pattern.search(line)
        if timing_match:
            pending_timing_type = (
                "timing_virtual" if timing_match.group(1) == "true" else "timing_actual"
            )

        actual_iter_match = actual_iter_pattern.search(line)
        if actual_iter_match and pending_timing_type:
            events.append((int(actual_iter_match.group(1)), pending_timing_type))
            pending_timing_type = None

    return data, events

def determine_log_status(log_path):
    with open(log_path, 'r') as f:
        content = f.read()
        if "Skipping global placement without IOs" in content:
            return "SKIPPED"
        elif "conjugate gradient" in content:
            return "CG"
        else:
            return "NO CG"

def plot_gp_iterations(data, events, title, filename):
    if not data:
        print(f"No data to plot for {title}.")
        return

    iterations, overflows, hpwls, penalties = zip(*data)

    fig, ax1 = plt.subplots(figsize=(12, 6))

    color1 = 'tab:blue'
    ax1.set_xlabel('Iteration')
    ax1.set_ylabel('Overflow', color=color1)
    ax1.plot(iterations, overflows, color=color1, label='Overflow')
    ax1.tick_params(axis='y', labelcolor=color1)

    ax2 = ax1.twinx()
    color2 = 'tab:orange'
    ax2.set_ylabel('HPWL (um)', color=color2)
    ax2.plot(iterations, hpwls, color=color2, label='HPWL (um)')
    ax2.tick_params(axis='y', labelcolor=color2)

    ax3 = ax1.twinx()
    color3 = 'tab:green'
    ax3.spines["right"].set_position(("outward", 60))
    ax3.set_ylabel('Penalty', color=color3)
    ax3.set_yscale('log')
    ax3.plot(iterations, penalties, color=color3, label='Penalty')
    ax3.tick_params(axis='y', labelcolor=color3)

    for iter_num, event_type in events:
        if event_type == "routability":
            ax1.axvline(x=iter_num, color="red", linestyle="--", linewidth=1.0)
        elif event_type == "timing_virtual":
            ax1.axvline(x=iter_num, color="purple", linestyle="--", linewidth=1.0)
        elif event_type == "timing_actual":
            ax1.axvline(x=iter_num, color="black", linestyle="--", linewidth=1.0)

    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    handles3, labels3 = ax3.get_legend_handles_labels()

    event_labels = {
        "Routability": ("red", "--"),
        "Timing-driven (virtual)": ("purple", "--"),
        "Timing-driven": ("black", "--"),
    }
    for label, (color, style) in event_labels.items():
        handles1.append(plt.Line2D([0], [0], color=color, linestyle=style, linewidth=1))
        labels1.append(label)

    all_handles = handles1 + handles2 + handles3
    all_labels = labels1 + labels2 + labels3
    by_label = dict(zip(all_labels, all_handles))

    plt.legend(
        by_label.values(),
        by_label.keys(),
        loc="best",
        framealpha=0.2,
        fontsize="small",
        handlelength=1.5,
        handletextpad=0.4,
        borderaxespad=0.3
    )

    plt.title(title)
    fig.tight_layout()
    plt.savefig(filename)
    plt.close()

# Main logic
base_path = '.'
unzip_runs(base_path, UNZIP_DIR)
summary_rows = []

for log_name, output_dir in OUTPUT_DIRS.items():
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    gp_logs = collect_gp_log_paths(UNZIP_DIR, log_name)

    if gp_logs:
        for (platform, design, stage), log_path in gp_logs:
            data, events = extract_gp_data_and_events(log_path)
            status = determine_log_status(log_path)
            starting_overflow = extract_starting_overflow(log_path)
            summary_rows.append([design, platform, stage, design, platform, status, starting_overflow])
            data.sort(key=lambda x: x[0])
            safe_platform = platform.replace("/", "_")
            safe_design = design.replace("/", "_")
            safe_stage = stage.replace("/", "_")
            filename = os.path.join(output_dir, f"{safe_platform}__{safe_design}__{safe_stage}.png")
            plot_gp_iterations(data, events, f"{platform}/{design}/{stage}", filename)
    else:
        print(f"No {log_name} files found.")

# Write summary table
with open(CSV_SUMMARY, 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(['Design', 'Technology', 'Stage', 'Design Name', 'Technology Name', 'Status', 'Starting Overflow'])
    writer.writerows(summary_rows)

print(f"Summary table saved to {CSV_SUMMARY}")
