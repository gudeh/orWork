import os
import re
import csv
from collections import defaultdict

def process_log_file(log_file_path):
    iteration_number = None
    metadata_status = "ERROR"  # Default status if the file is found but no relevant messages are found
    iteration_pattern = r"(\d+)(st|nd|rd|th) optimization iteration"
    metadata_pass_pattern = "All metadata rules passed"
    metadata_fail_pattern = "Failed metadata check"

    if not os.path.exists(log_file_path):
        return None, ""  # No iterations and empty status if file is not found

    with open(log_file_path, 'r') as file:
        lines = file.readlines()
        for line in reversed(lines):
            if iteration_number is None:
                match = re.search(iteration_pattern, line)
                if match:
                    iteration_number = match.group(1)

            if metadata_pass_pattern in line:
                metadata_status = "OK"
            elif metadata_fail_pattern in line:
                metadata_status = "FAIL"

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

        # Create headers for each run configuration, with 'Iterations' and 'Status' as separate columns.
        headers = ['Design Name', 'Technology']
        for rc in run_configs:
            headers.extend([f'{rc} Iterations', f'{rc} Status'])  # Append pairs of headers for each run configuration
        writer.writerow(headers)

        for (design_name, technology), run_config_data in data.items():
            row = [design_name, technology]
            for rc in run_configs:
                rc_data = run_config_data.get(rc, {'Iterations': [''], 'Status': ''})
                # Make sure to convert None or list to a string, if needed.
                iterations = rc_data['Iterations'][0] if rc_data['Iterations'] else ''
                status = rc_data['Status'] if rc_data['Status'] is not None else ''
                row.extend([iterations, status])  # Extend the row with iterations and status as a pair
            writer.writerow(row)



# Usage
base_path = '.'  # Current directory
output_file = 'output.csv'
data = process_directories(base_path)
write_to_csv(data, output_file)
