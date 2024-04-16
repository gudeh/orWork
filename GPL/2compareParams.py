import os
import re
import csv
from collections import defaultdict

def process_log_file(log_file_path):
    iteration_number = None
    metadata_status = "ERROR"
    cpu_time = None
    violations = None
    global_placer_cpu_time = None
    iteration_pattern = r"(\d+)(st|nd|rd|th) optimization iteration"
    metadata_pass_pattern = "All metadata rules passed"
    metadata_fail_pattern = "Failed metadata check"
    cpu_time_pattern = re.compile(r"\[INFO (DRT-\d{4})\] cpu time = ([0-9]{2}:[0-9]{2}:[0-9]{2})")
    violation_pattern = re.compile(r"Number of violations = (\d+)")
    global_placer_start_pattern = re.compile(r"global place report_design_area")
    cpu_time_global_placer_pattern = re.compile(r"CPU time: user ([0-9.]+)")

    if not os.path.exists(log_file_path):
        return None, "", "", "", None

    in_global_placer_section = False

    with open(log_file_path, 'r') as file:
        lines = file.readlines()
        status_found = False
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
                    cpu_time = cpu_match.group(2) #)+ ' user, ' + cpu_match.group(2) + ' sys'

            if violations is None:
                violation_match = violation_pattern.search(line)
                if violation_match:
                    violations = violation_match.group(1)

        for line in lines:
            if global_placer_start_pattern.search(line):
                in_global_placer_section = True
                print("HEYY!")
            elif in_global_placer_section:
                # Capturing CPU time from the global placer section
                placer_cpu_match = cpu_time_global_placer_pattern.search(line)
                if placer_cpu_match:
                    print ("match!!")
                    global_placer_cpu_time = placer_cpu_match.group(1)# + ' user, ' + placer_cpu_match.group(2) + ' sys'
                    break

        if not status_found and violations is None:
            # Fallback error line extraction
            error_pattern = re.compile(r"error", re.IGNORECASE)
            for line in lines:
                if error_pattern.search(line):
                    clean_line = line.strip().replace(',', '')
                    metadata_status = clean_line
                    break

    return iteration_number, metadata_status, cpu_time, violations, global_placer_cpu_time

def process_directories(base_path):
    data = defaultdict(lambda: defaultdict(lambda: {'Iterations': [], 'Status': None, 'CPU Time': None, 'Violations': None, 'Global Placer CPU Time': None}))
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
                            iterations, status, cpu_time, violations, global_placer_cpu_time = process_log_file(log_file_path)
                        else:
                            iterations, status, cpu_time, violations, global_placer_cpu_time = None, "", "", "", None
                        data[(design_name, technology)][run_config]['Iterations'].append(iterations)
                        data[(design_name, technology)][run_config]['Status'] = status
                        data[(design_name, technology)][run_config]['CPU Time'] = cpu_time
                        data[(design_name, technology)][run_config]['Violations'] = violations
                        data[(design_name, technology)][run_config]['Global Placer CPU Time'] = global_placer_cpu_time
    return data

def write_to_csv(data, output_file):
    with open(output_file, 'w', newline='') as file:
        writer = csv.writer(file)
        run_configs = set()
        for run_config_dict in data.values():
            run_configs.update(run_config_dict.keys())
        run_configs = sorted(run_configs, key=lambda x: ("standard" not in x.lower(), x))

        # Writing headers
        headers_top = [''] * 2
        headers_middle = [''] * 2
        headers_bottom = ['Design Name', 'Technology']
        for rc in run_configs:
            headers_top.extend([rc] * 5)
            headers_middle.extend(['Final DRT', 'Final DRT', 'Final DRT', 'Final DRT', 'Global Placer'])
            headers_bottom.extend(['Iterations', 'Status', 'CPU Time', 'Violations', 'CPU Time'])
        writer.writerow(headers_top)
        writer.writerow(headers_middle)
        writer.writerow(headers_bottom)

        # Writing data rows
        for (design_name, technology), run_config_data in data.items():
            row = [design_name, technology]
            for rc in run_configs:
                rc_data = run_config_data.get(rc, {'Iterations': [''], 'Status': '', 'CPU Time': '', 'Violations': '', 'Global Placer CPU Time': None})
                iterations = rc_data['Iterations'][0] if rc_data['Iterations'] else ''
                status = rc_data['Status'] if rc_data['Status'] is not None else ''
                cpu_time = rc_data['CPU Time']
                violations = rc_data['Violations']
                global_placer_cpu_time = rc_data['Global Placer CPU Time']
                row.extend([iterations, status, cpu_time, violations, global_placer_cpu_time])
            writer.writerow(row)

base_path = '.'
output_file = 'output.csv'
data = process_directories(base_path)
write_to_csv(data, output_file)
