import os
import re
import csv
from collections import defaultdict
import json

SHOW_GPL = True

def process_log_file(log_file_path):
    finish_metadata_status = "ERROR"
    gpl_cpu_time = gpl_cpu_time_seconds = gpl_last_num_call = gpl_iterations = None

    metadata_pass_pattern = "All metadata rules passed"
    metadata_fail_pattern = "Failed metadata check"
    violation_pattern = re.compile(r"Number of violations = (\d+)")
    global_placer_report_pattern = re.compile(r"global place report_design_area")
    cpu_time_global_placer_pattern = re.compile(r"CPU time: user ([0-9.]+)")
    num_call_pattern = re.compile(r"Routability numCall: (\d+)")
    gpl_iterations_pattern = re.compile(r"\[NesterovSolve\] Iter:\s*(\d+)")

    if not os.path.exists(log_file_path):
        return None, "", "", "", None, None, None, None, None, 0, 0

    with open(log_file_path, 'r') as file:
        lines = file.readlines()
        status_found = False

        for line in reversed(lines):
            if metadata_pass_pattern in line:
                finish_metadata_status = "OK"
                status_found = True
            elif metadata_fail_pattern in line:
                finish_metadata_status = "FAIL"
                status_found = True

            if gpl_last_num_call is None:
                num_call_match = num_call_pattern.search(line)
                if num_call_match:
                    gpl_last_num_call = num_call_match.group(1)

            if gpl_iterations is None:
                gpl_iterations_match = gpl_iterations_pattern.search(line)
                if gpl_iterations_match:
                    gpl_iterations = gpl_iterations_match.group(1)

        in_global_place_report_section = False
        for line in lines:
            if global_placer_report_pattern.search(line):
                in_global_place_report_section = True
            elif in_global_place_report_section:
                placer_cpu_match = cpu_time_global_placer_pattern.search(line)
                if placer_cpu_match:
                    seconds = float(placer_cpu_match.group(1))
                    gpl_cpu_time_seconds = seconds
                    gpl_cpu_time = '{:.2f}'.format(seconds / 60)
                    break            

        if not status_found:
            error_pattern = re.compile(r"error", re.IGNORECASE)
            for line in lines:
                if error_pattern.search(line):
                    clean_line = line.strip().replace(',', '')
                    finish_metadata_status = clean_line
                    break

    return (finish_metadata_status, gpl_cpu_time, gpl_cpu_time_seconds,
            gpl_last_num_call, gpl_iterations)

def process_json_file(json_file_path):
    with open(json_file_path, 'r') as file:
        data = json.load(file)
        start_inst_area = data.get("floorplan__design__instance__area", None)
        start_inst_num = data.get("floorplan__design__instance__count", None)
        end_instance_area = data.get("globalplace__design__instance__area", None)
        end_instance_count = data.get("globalplace__design__instance__count", None)
        cts_tns = data.get("cts__timing__setup__tns", None)
        finish_tns = data.get("finish__timing__setup__tns", None)
        placeopt_area = data.get("placeopt__design__instance__area", None)
        placeopt_count = data.get("placeopt__design__instance__count", None)
        return end_instance_area, cts_tns, finish_tns, end_instance_count, start_inst_area, start_inst_num, placeopt_area, placeopt_count

# Updating process_directories to handle new data
def process_directories(base_path):
    data = defaultdict(lambda: defaultdict(lambda: {
        'gpl_iterations': None, 'finish_status': None, 'gpl_cpu_time': None, 'gpl_cpu_time_seconds': None, 'gpl_last_num_call': None,
        'start_inst_area': None, 'start_inst_num': None,
        'end_instance_area': None, 'cts_tns': None, 'finish_tns': None, 'end_instance_count': None,
        'placeopt_area': None, 'placeopt_count': None
    }))
    for run_config in os.listdir(base_path):
        run_config_path = os.path.join(base_path, run_config)
        if os.path.isdir(run_config_path):
            for technology in os.listdir(run_config_path):
                tech_path = os.path.join(run_config_path, technology)
                if os.path.isdir(tech_path):
                    for file in os.listdir(tech_path):
                        design_name = file.replace('.log', '').replace('.json', '')
                        log_file_path = os.path.join(tech_path, file)
                        if file.endswith('.log'):
                            log_data = process_log_file(log_file_path)
                            if log_data:
                                (finish_status, gpl_cpu_time, gpl_cpu_time_seconds, gpl_last_num_call,
                                 gpl_iterations) = log_data
                                data[(design_name, technology)][run_config]['gpl_iterations'] = gpl_iterations
                                data[(design_name, technology)][run_config]['finish_status'] = finish_status
                                data[(design_name, technology)][run_config]['gpl_cpu_time'] = gpl_cpu_time
                                data[(design_name, technology)][run_config]['gpl_cpu_time_seconds'] = gpl_cpu_time_seconds
                                data[(design_name, technology)][run_config]['gpl_last_num_call'] = gpl_last_num_call
                        elif file.endswith('.json'):
                            result = process_json_file(log_file_path)
                            if result:
                                end_instance_area, cts_tns, finish_tns, end_instance_count, start_inst_area, start_inst_num, placeopt_area, placeopt_count = result
                                data[(design_name, technology)][run_config].update({
                                    'end_instance_area': end_instance_area,
                                    'cts_tns': cts_tns,
                                    'finish_tns': finish_tns,
                                    'end_instance_count': end_instance_count,
                                    'start_inst_area': start_inst_area,
                                    'start_inst_num': start_inst_num,
                                    'placeopt_area': placeopt_area,
                                    'placeopt_count': placeopt_count
                                })
    return data

def write_to_csv(data, output_file):
    with open(output_file, 'w', newline='') as file:
        writer = csv.writer(file)
        run_configs = set()
        for run_config_dict in data.values():
            run_configs.update(run_config_dict.keys())
        run_configs = sorted(run_configs, key=lambda x: ('nightly' not in x.lower(), 'standard' not in x.lower(), x))

        headers_top = [''] * 2
        headers_middle = [''] * 2
        headers_bottom = ['Design Name', 'Technology']

        for rc in run_configs:
            if SHOW_GPL:
                headers_top.extend([rc] * 17 + [''])
                headers_middle.extend([
                    '6-Final', 'GPL', 'GPL', 'GPL', 'GPL', '4-CTS (json)', '6-Final (json)',
                    '2-Floorp (json)', '3.3-GPL (json)', '2-Floorp (json)', '3.3-GPL (json)',
                    'change 2 to 3.3', 'change 2 to 3.3', 'placeopt (3.4)', 'placeopt (3.4)', 'change 3.3 to 3.4', 'change 3.3 to 3.4', ''
                ])
                headers_bottom.extend([
                    'Status', '# RD iterations', 'Iterations', 'CPU Time (min)', 'Avg. Runtime per Iteration (s)', 'CTS TNS', 'Finish TNS', 
                    'Start Area (um^2)', 'End Area', 'Start #Instances', 'End #Instances', '% Area Change', '% Inst Change',
                    'Area (um^2)', 'Instance Count', '% Area Change', '% Instance Change', ''
                ])

        writer.writerow(headers_top)
        writer.writerow(headers_middle)
        writer.writerow(headers_bottom)

        for (design_name, technology), run_config_data in data.items():
            row = [design_name, technology]
            for rc in run_configs:
                rc_data = run_config_data.get(rc, {
                    'gpl_iterations': None, 'finish_status': '', 'gpl_cpu_time': None, 'gpl_cpu_time_seconds': None, 'gpl_last_num_call': None,
                    'cts_tns': None, 'finish_tns': None, 'start_inst_area': None, 'start_inst_num': None, 
                    'end_instance_area': None, 'end_instance_count': None, 'placeopt_area': None, 'placeopt_count': None
                })
                finish_status = rc_data['finish_status'] if rc_data['finish_status'] is not None else ''
                gpl_iterations = rc_data['gpl_iterations']
                gpl_cpu_time = rc_data['gpl_cpu_time']
                gpl_cpu_time_seconds = rc_data['gpl_cpu_time_seconds']
                gpl_last_num_call = rc_data['gpl_last_num_call']
                cts_tns = rc_data['cts_tns']
                finish_tns = rc_data['finish_tns']
                start_inst_area = rc_data['start_inst_area']
                end_instance_area = rc_data['end_instance_area']
                start_inst_num = rc_data['start_inst_num']
                end_instance_count = rc_data['end_instance_count']
                placeopt_area = rc_data['placeopt_area']
                placeopt_count = rc_data['placeopt_count']
                
                avg_runtime_per_iteration = '{:.3f}'.format(gpl_cpu_time_seconds / float(gpl_iterations)) if gpl_cpu_time_seconds and gpl_iterations else ''
                
                area_change = ''
                if start_inst_area and end_instance_area:
                    try:
                        area_change = '{:.3f}'.format((float(end_instance_area) - float(start_inst_area)) / float(start_inst_area))
                    except ValueError:
                        area_change = ''

                instance_change = ''
                if start_inst_num and end_instance_count:
                    try:
                        instance_change = '{:.3f}'.format((float(end_instance_count) - float(start_inst_num)) / float(start_inst_num))
                    except ValueError:
                        instance_change = ''

                area_change_3_3_to_3_4 = ''
                if end_instance_area and placeopt_area:
                    try:
                        area_change_3_3_to_3_4 = '{:.3f}'.format((float(placeopt_area) - float(end_instance_area)) / float(end_instance_area))
                    except ValueError:
                        area_change_3_3_to_3_4 = ''

                instance_change_3_3_to_3_4 = ''
                if end_instance_count and placeopt_count:
                    try:
                        instance_change_3_3_to_3_4 = '{:.3f}'.format((float(placeopt_count) - float(end_instance_count)) / float(end_instance_count))
                    except ValueError:
                        instance_change_3_3_to_3_4 = ''

                if SHOW_GPL:
                    row.extend([
                        finish_status, gpl_last_num_call, gpl_iterations, gpl_cpu_time, avg_runtime_per_iteration, 
                        cts_tns, finish_tns, start_inst_area, end_instance_area, start_inst_num, end_instance_count, area_change, instance_change,
                        placeopt_area, placeopt_count, area_change_3_3_to_3_4, instance_change_3_3_to_3_4, ''
                    ])
            writer.writerow(row)


base_path = '.'
output_file = 'gpl_output.csv'
data = process_directories(base_path)
write_to_csv(data, output_file)
