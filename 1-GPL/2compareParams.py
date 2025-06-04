import os
import re
import csv
import zipfile
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
    for run_dir in os.listdir(unzip_dir):
        run_path = os.path.join(unzip_dir, run_dir, 'logs')
        if os.path.isdir(run_path):
            for platform in os.listdir(run_path):
                platform_path = os.path.join(run_path, platform)
                if os.path.isdir(platform_path):
                    for file in os.listdir(platform_path):
                        if file.endswith('.log'):
                            design_name = file.replace('.log', '')
                            log_path = os.path.join(platform_path, file)
                            log_paths.append((run_dir, platform, design_name, log_path))
    return log_paths


def process_log_file(log_file_path):
    iteration_number = None
    metadata_status = "ERROR"
    cpu_time = None
    violations = None
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
        status_found = False
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
                status_found = True
            elif metadata_fail_pattern in line:
                metadata_status = "FAIL"
                status_found = True

            if cpu_time is None:
                cpu_match = cpu_time_pattern.search(line)
                if cpu_match:
                    h, m, s = map(int, cpu_match.group(2).split(':'))
                    cpu_time = '{:.2f}'.format(h * 60 + m + s / 60.0)

            if violations is None:
                match = violation_pattern.search(line)
                if match:
                    violations = match.group(1)

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

    return iteration_number, metadata_status, cpu_time, violations, global_placer_cpu_time, last_routability, first_iteration_violations


def aggregate_data(log_paths):
    data = defaultdict(lambda: defaultdict(lambda: {
        'Iterations': None, 'Status': None, 'CPU Time': None, 'Violations': None,
        'Global Placer CPU Time': None, 'routability': None, '0th DRT Iteration Violations': None
    }))
    for run, platform, design, path in log_paths:
        vals = process_log_file(path)
        data[(design, platform)][run] = {
            'Iterations': vals[0], 'Status': vals[1], 'CPU Time': vals[2], 'Violations': vals[3],
            'Global Placer CPU Time': vals[4], 'routability': vals[5], '0th DRT Iteration Violations': vals[6]
        }
    return data


def write_to_csv(data, output_file):
    with open(output_file, 'w', newline='') as file:
        writer = csv.writer(file)
        run_configs = sorted({rc for d in data.values() for rc in d})

        writer.writerow([''] * 2 + [rc for rc in run_configs for _ in range(7)])
        writer.writerow([''] * 2 + ['0th DRT Iteration', 'Final DRT', 'Final DRT', 'Final DRT', 'Final DRT', 'GPL', 'GPL'] * len(run_configs))
        writer.writerow(['Design Name', 'Technology'] + ['Violations', 'Iterations', 'Status', 'CPU Time', 'Violations', 'CPU Time', 'routability'] * len(run_configs))

        for (design, tech), runs in data.items():
            row = [design, tech]
            for rc in run_configs:
                info = runs.get(rc, {})
                row.extend([
                    info.get('0th DRT Iteration Violations', ''),
                    info.get('Iterations', ''),
                    info.get('Status', ''),
                    info.get('CPU Time', ''),
                    info.get('Violations', ''),
                    info.get('Global Placer CPU Time', ''),
                    info.get('routability', '')
                ])
            writer.writerow(row)


if __name__ == "__main__":
    base_path = '.'  # current dir with .zip files
    unzip_runs(base_path, UNZIP_DIR)
    logs = collect_log_paths(UNZIP_DIR)
    data = aggregate_data(logs)
    write_to_csv(data, 'output.csv')
