import os
import re
import csv
from collections import defaultdict

def process_log_file(log_file_path):
    iteration_number = None
    metadata_status = "ERROR"
    iteration_pattern = r"(\d+)(st|nd|rd|th) optimization iteration"
    metadata_pass_pattern = "All metadata rules passed"
    metadata_fail_pattern = "Failed metadata check"
    error_pattern = re.compile(r"error", re.IGNORECASE)

    if not os.path.exists(log_file_path):
        return None, ""

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
                # break
            elif metadata_fail_pattern in line:
                metadata_status = "FAIL"
                status_found = True
                # break      

        if not status_found:
            # Search for the word "error" and remove commas from the line
            for line in lines:
                if error_pattern.search(line):
                    clean_line = line.strip().replace(',', '')  # Remove commas from the line
                    metadata_status = clean_line
                    break

    return iteration_number, metadata_status

def process_directories(base_path):
    data = defaultdict(lambda: defaultdict(lambda: {'Iterations': [], 'Status': None}))

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
                            iterations, status = process_log_file(log_file_path)
                        else:
                            iterations, status = None, ""
                        data[(design_name, technology)][run_config]['Iterations'].append(iterations)
                        data[(design_name, technology)][run_config]['Status'] = status

    return data

def write_to_csv(data, output_file):
    with open(output_file, 'w', newline='') as file:
        writer = csv.writer(file)

        run_configs = set()
        for run_config_dict in data.values():
            run_configs.update(run_config_dict.keys())
        run_configs = sorted(run_configs)

        headers = ['Design Name', 'Technology']
        for rc in run_configs:
            headers.extend([f'{rc} Iterations', f'{rc} Status']) 
        writer.writerow(headers)

        for (design_name, technology), run_config_data in data.items():
            row = [design_name, technology]
            for rc in run_configs:
                rc_data = run_config_data.get(rc, {'Iterations': [''], 'Status': ''})
                iterations = rc_data['Iterations'][0] if rc_data['Iterations'] else ''
                status = rc_data['Status'] if rc_data['Status'] is not None else ''
                row.extend([iterations, status])
            writer.writerow(row)

base_path = '.'
output_file = 'output.csv'
data = process_directories(base_path)
write_to_csv(data, output_file)

