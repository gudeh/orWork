import os
import re
import csv
from collections import defaultdict

def process_log_file(log_file_path):
    iteration_number = None
    metadata_status = "ERROR"
    cpu_time = None
    violations = None
    first_iteration_violations = None  # Variable to store violations from the first iteration
    global_placer_cpu_time = None
    last_num_call = None
    iteration_pattern = r"(\d+)(st|nd|rd|th) optimization iteration"
    metadata_pass_pattern = "All metadata rules passed"
    metadata_fail_pattern = "Failed metadata check"
    cpu_time_pattern = re.compile(r"\[INFO (DRT-\d{4})\] cpu time = ([0-9]{2}:[0-9]{2}:[0-9]{2})")
    violation_pattern = re.compile(r"Number of violations = (\d+)")
    global_placer_start_pattern = re.compile(r"global place report_design_area")
    cpu_time_global_placer_pattern = re.compile(r"CPU time: user ([0-9.]+)")
    num_call_pattern = re.compile(r"Routability numCall: (\d+)")

    if not os.path.exists(log_file_path):
        return None, "", "", "", None, None, None

    with open(log_file_path, 'r') as file:
        lines = file.readlines()
        status_found = False
        in_first_iteration = False

        for line in lines:
            if 'Start 0th optimization iteration.' in line:
                in_first_iteration = True  # Start capturing data for the first iteration
            elif 'Start' in line and 'optimization iteration' in line and '0th' not in line:
                in_first_iteration = False  # Stop capturing after the first iteration ends

            if in_first_iteration:
                if first_iteration_violations is None:
                    violation_match = violation_pattern.search(line)
                    if violation_match:
                        first_iteration_violations = violation_match.group(1)

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
                    cpu_time = cpu_match.group(2)

            if violations is None:
                violation_match = violation_pattern.search(line)
                if violation_match:
                    violations = violation_match.group(1)

            if last_num_call is None:
                num_call_match = num_call_pattern.search(line)
                if num_call_match:
                    last_num_call = num_call_match.group(1)

        # Handle section specific to global placer CPU time
        in_global_placer_section = False
        for line in lines:
            if global_placer_start_pattern.search(line):
                in_global_placer_section = True
            elif in_global_placer_section:
                placer_cpu_match = cpu_time_global_placer_pattern.search(line)
                if placer_cpu_match:
                    global_placer_cpu_time = placer_cpu_match.group(1)
                    break

        if not status_found and violations is None:
            error_pattern = re.compile(r"error", re.IGNORECASE)
            for line in lines:
                if error_pattern.search(line):
                    clean_line = line.strip().replace(',', '')
                    metadata_status = clean_line
                    break

    return iteration_number, metadata_status, cpu_time, violations, global_placer_cpu_time, last_num_call, first_iteration_violations


def process_directories(base_path):
    data = defaultdict(lambda: defaultdict(lambda: {'Iterations': [], 'Status': None, 'CPU Time': None, 'Violations': None, 'Global Placer CPU Time': None, 'Last NumCall': None, '0th DRT Iteration Violations': None}))
    for run_config in os.listdir(base_path):
        run_config_path = os.path.join(base_path, run_config)
        if os.path.isdir(run_config_path):
            for technology in os.listdir(run_config_path):
                tech_path = os.path.join(run_config_path, technology)
                if os.path.isdir(tech_path):
                    for file in os.listdir(tech_path):
                        design_name = file.replace('.log', '')
                        log_file_path = os.path.join(tech_path, file)
                        if file.endswith('.log'):
                            iterations, status, cpu_time, violations, global_placer_cpu_time, last_num_call, first_iteration_violations = process_log_file(log_file_path)
                        else:
                            iterations, status, cpu_time, violations, global_placer_cpu_time, last_num_call, first_iteration_violations = None, "", "", "", None, None, None
                        data[(design_name, technology)][run_config]['Iterations'].append(iterations)
                        data[(design_name, technology)][run_config]['Status'] = status
                        data[(design_name, technology)][run_config]['CPU Time'] = cpu_time
                        data[(design_name, technology)][run_config]['Violations'] = violations
                        data[(design_name, technology)][run_config]['Global Placer CPU Time'] = global_placer_cpu_time
                        data[(design_name, technology)][run_config]['Last NumCall'] = last_num_call
                        data[(design_name, technology)][run_config]['0th DRT Iteration Violations'] = first_iteration_violations
    return data

def write_to_csv(data, output_file):
    with open(output_file, 'w', newline='') as file:
        writer = csv.writer(file)
        run_configs = set()
        for run_config_dict in data.values():
            run_configs.update(run_config_dict.keys())
        run_configs = sorted(run_configs, key=lambda x: ("standard" not in x.lower(), x))

        headers_top = [''] * 2
        headers_middle = [''] * 2
        headers_bottom = ['Design Name', 'Technology']
        for rc in run_configs:
            headers_top.extend([rc] * 7)  # Ensure the header spans 7 columns for each run configuration
            headers_middle.extend(['0th DRT Iteration', 'Final DRT', 'Final DRT', 'Final DRT', 'Final DRT', 'GPL', 'GPL'])
            headers_bottom.extend(['Violations', 'Iterations', 'Status', 'CPU Time', 'Violations', 'CPU Time', 'Last NumCall'])
        writer.writerow(headers_top)
        writer.writerow(headers_middle)
        writer.writerow(headers_bottom)

        for (design_name, technology), run_config_data in data.items():
            row = [design_name, technology]
            for rc in run_configs:
                rc_data = run_config_data.get(rc, {'Iterations': [''], 'Status': '', 'CPU Time': '', 'Violations': '', 'Global Placer CPU Time': None, 'Last NumCall': None, '0th DRT Iteration Violations': None})
                iterations = rc_data['Iterations'][0] if rc_data['Iterations'] else ''
                status = rc_data['Status'] if rc_data['Status'] is not None else ''
                cpu_time = rc_data['CPU Time']
                violations = rc_data['Violations']
                global_placer_cpu_time = rc_data['Global Placer CPU Time']
                last_num_call = rc_data['Last NumCall']
                first_iteration_violations = rc_data['0th DRT Iteration Violations']
                # Note the change in order here to match new header positions
                row.extend([first_iteration_violations, iterations, status, cpu_time, violations, global_placer_cpu_time, last_num_call])
            writer.writerow(row)

base_path = '.'
output_file = 'output.csv'
data = process_directories(base_path)
write_to_csv(data, output_file)
