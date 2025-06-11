import glob
import os
import re
import csv
import zipfile
import json
from collections import defaultdict

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
    cpu_time = None
    first_iteration_violations = None
    global_placer_cpu_time = None
    last_routability = None

    iteration_pattern = r"(\d+)(st|nd|rd|th) optimization iteration"
    metadata_pass_pattern = "All metadata rules passed"
    metadata_fail_pattern = "Failed metadata check"
    cpu_time_pattern = re.compile(r"\[INFO (DRT-\d{4})\] cpu time = ([0-9]{2}:[0-9]{2}:[0-9]{2})")
    violation_pattern = re.compile(r"Number of violations = (\d+)")
    global_placer_start_pattern = re.compile(r"global place report_design_area")
    cpu_time_global_placer_pattern = re.compile(r"CPU time: user ([0-9.]+)")
    routability_pattern = re.compile(r"Routability iteration: (\d+)")

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

        for line in reversed(lines):
            if iteration_number is None:
                match = re.search(iteration_pattern, line)
                if match:
                    iteration_number = match.group(1)

            if metadata_pass_pattern in line:
                metadata_status = "OK"
            elif metadata_fail_pattern in line:
                metadata_status = "FAIL"

            if cpu_time is None:
                cpu_match = cpu_time_pattern.search(line)
                if cpu_match:
                    h, m, s = map(int, cpu_match.group(2).split(':'))
                    cpu_time = '{:.2f}'.format(h * 60 + m + s / 60.0)

            if last_routability is None:
                match = routability_pattern.search(line)
                if match:
                    last_routability = match.group(1)

        in_global_placer_section = False
        for line in lines:
            if global_placer_start_pattern.search(line):
                in_global_placer_section = True
            elif in_global_placer_section:
                match = cpu_time_global_placer_pattern.search(line)
                if match:
                    seconds = float(match.group(1))
                    global_placer_cpu_time = '{:.2f}'.format(seconds / 60)
                    break

    return iteration_number, metadata_status, cpu_time, global_placer_cpu_time, last_routability, first_iteration_violations


def aggregate_data(log_paths):
    data = defaultdict(lambda: defaultdict(lambda: {
        'Iterations': None,
        'Status': None,
        'CPU Time': None,
        'Global Placer CPU Time': None,
        'routability': None,
        '0th DRT Iteration Violations': None,
        'Wirelength': None,
        'Finish TNS': None
    }))
    for run, platform, design, log_path in log_paths:
        vals = process_log_file(log_path)

        # Look for the JSON file in the same base directory
        json_path = os.path.join(os.path.dirname(log_path), f"{design}.json")
        wirelength, finish_tns = extract_metrics_from_json(json_path)

        data[(design, platform)][run] = {
            'Iterations': vals[0],
            'Status': vals[1],
            'CPU Time': vals[2],
            'Global Placer CPU Time': vals[3],
            'routability': vals[4],
            '0th DRT Iteration Violations': vals[5],
            'Wirelength': wirelength,
            'Finish TNS': finish_tns
        }
    return data


def extract_metrics_from_json(json_path):
    wirelength = None
    finish_tns = None
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
                        if wirelength is not None and finish_tns is not None:
                            break
            elif isinstance(data, dict):
                wirelength = data.get("detailedplace__route__wirelength__estimated")
                finish_tns = data.get("finish__timing__setup__tns")

    except Exception as e:
        print(f"Failed to parse JSON from {json_path}: {e}")

    return wirelength, finish_tns


def write_to_csv(data, output_file):
    with open(output_file, 'w', newline='') as file:
        writer = csv.writer(file)
        run_configs = sorted({rc for d in data.values() for rc in d})

        writer.writerow([''] * 2 + [rc for rc in run_configs for _ in range(8)])
        writer.writerow([''] * 2 + [
            '0th DRT Iteration', 'Iterations', 'Status', 'CPU Time',
            'GPL CPU Time', 'routability', 'Wirelength', 'Finish TNS'
        ] * len(run_configs))
        writer.writerow(['Design Name', 'Technology'] + [
            'Violations', 'Iterations', 'Status', 'CPU Time',
            'GPL CPU Time', 'routability', 'Wirelength', 'Finish TNS'
        ] * len(run_configs))

        for (design, tech), runs in data.items():
            row = [design, tech]
            for rc in run_configs:
                info = runs.get(rc, {})
                row.extend([
                    info.get('0th DRT Iteration Violations', ''),
                    info.get('Iterations', ''),
                    info.get('Status', ''),
                    info.get('CPU Time', ''),
                    info.get('Global Placer CPU Time', ''),
                    info.get('routability', ''),
                    info.get('Wirelength', ''),
                    info.get('Finish TNS', '')
                ])
            writer.writerow(row)



if __name__ == "__main__":
    base_path = '.'  # current dir with .zip files
    unzip_runs(base_path, UNZIP_DIR)
    logs = collect_log_paths(UNZIP_DIR)
    collect_json_paths_and_merge(UNZIP_DIR)
    data = aggregate_data(logs)
    write_to_csv(data, 'output.csv')
