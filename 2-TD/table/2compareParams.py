import os
import re
import csv
from collections import defaultdict
import json

SHOW_GPL = True
SHOW_DRT = False

def process_log_file(log_file_path):
    drt_metadata_status = "ERROR"
    drt_iteration_number = drt_cpu_time = drt_violations = drt_first_iteration_violations = gpl_cpu_time = gpl_cpu_time_seconds = gpl_last_num_call = gpl_iterations = gpl_last_tns = rsz_tns = starting_inst_area = starting_num_instances = None
    total_resized_gates = total_inserted_buffers = 0

    iteration_pattern = r"(\d+)(st|nd|rd|th) optimization iteration"
    metadata_pass_pattern = "All metadata rules passed"
    metadata_fail_pattern = "Failed metadata check"
    cpu_time_pattern = re.compile(r"\[INFO (DRT-\d{4})\] cpu time = ([0-9]{2}:[0-9]{2}:[0-9]{2})")
    violation_pattern = re.compile(r"Number of violations = (\d+)")
    global_placer_report_pattern = re.compile(r"global place report_design_area")
    cpu_time_global_placer_pattern = re.compile(r"CPU time: user ([0-9.]+)")
    num_call_pattern = re.compile(r"Routability numCall: (\d+)")
    gpl_iterations_pattern = re.compile(r"\[NesterovSolve\] Iter:\s*(\d+)")
    tns_pattern = re.compile(r"rs_->repair_design-> TNS:\s*(.*)")
    rsz_tns_pattern = re.compile(r"tns (-?\d+\.\d+)")
    rsz_line_pattern = re.compile(r"\[INFO RSZ-\d+\] Resized \d+ instances\.")
    journal_restore_pattern = re.compile(r"run_journal_restore \(virtual resizer\): false")
    resized_gates_pattern = re.compile(r"Resized gates:\s+(\d+)")
    inserted_buffers_pattern = re.compile(r"Inserted buffers:\s+(\d+)")
    global_placer_start_pattern = re.compile(r"global_placement")
    stdinst_area_pattern = re.compile(r"\[INFO GPL-0020\] StdInstsArea:\s+([\d.]+) um\^2")
    num_instances_pattern = re.compile(r"\[INFO GPL-0006\] NumInstances:\s+(\d+)")

    if not os.path.exists(log_file_path):
        return None, "", "", "", None, None, None, None, None, None, None, None, None, 0, 0

    with open(log_file_path, 'r') as file:
        lines = file.readlines()
        status_found = False
        in_first_iteration = False
        in_global_place_report_section = False
        in_global_placer_section = False

        for i, line in enumerate(lines):
            if 'Start 0th optimization iteration.' in line:
                in_first_iteration = True
            elif 'Start' in line and 'optimization iteration' in line and '0th' not in line:
                in_first_iteration = False

            if in_first_iteration:
                if drt_first_iteration_violations is None:
                    violation_match = violation_pattern.search(line)
                    if violation_match:
                        drt_first_iteration_violations = violation_match.group(1)
            
            if rsz_line_pattern.search(line) and i + 1 < len(lines):
                rsz_tns_match = rsz_tns_pattern.search(lines[i + 1])
                if rsz_tns_match:
                    rsz_tns = rsz_tns_match.group(1)

            if journal_restore_pattern.search(line) and i + 2 < len(lines):
                resized_gates_match = resized_gates_pattern.search(lines[i + 1])
                inserted_buffers_match = inserted_buffers_pattern.search(lines[i + 2])
                if resized_gates_match and inserted_buffers_match:
                    total_resized_gates += int(resized_gates_match.group(1))
                    total_inserted_buffers += int(inserted_buffers_match.group(1))

        for line in reversed(lines):
            if drt_iteration_number is None:
                match = re.search(iteration_pattern, line)
                if match:
                    drt_iteration_number = match.group(1)

            if metadata_pass_pattern in line:
                drt_metadata_status = "OK"
                status_found = True
            elif metadata_fail_pattern in line:
                drt_metadata_status = "FAIL"
                status_found = True

            if drt_cpu_time is None:
                cpu_match = cpu_time_pattern.search(line)
                if cpu_match:
                    h, m, s = map(int, cpu_match.group(2).split(':'))
                    drt_cpu_time = '{:.2f}'.format(h * 60 + m + s / 60.0)

            if drt_violations is None:
                violation_match = violation_pattern.search(line)
                if violation_match:
                    drt_violations = violation_match.group(1)

            if gpl_last_num_call is None:
                num_call_match = num_call_pattern.search(line)
                if num_call_match:
                    gpl_last_num_call = num_call_match.group(1)

            if gpl_iterations is None:
                gpl_iterations_match = gpl_iterations_pattern.search(line)
                if gpl_iterations_match:
                    gpl_iterations = gpl_iterations_match.group(1)

            if gpl_last_tns is None:
                tns_match = tns_pattern.search(line)
                if tns_match:
                    gpl_last_tns = tns_match.group(1)

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
            
        in_global_placer_section = False
        for line in lines:
            if global_placer_start_pattern.search(line):
                in_global_placer_section = True
            elif in_global_placer_section:
                stdinst_area_match = stdinst_area_pattern.search(line)
                starting_num_instances_match = num_instances_pattern.search(line)

                if stdinst_area_match:
                    starting_inst_area = stdinst_area_match.group(1)
                if starting_num_instances_match:
                    starting_num_instances = starting_num_instances_match.group(1)
                if starting_num_instances != None and starting_inst_area != None:
                    break

        if not status_found and drt_violations is None:
            error_pattern = re.compile(r"error", re.IGNORECASE)
            for line in lines:
                if error_pattern.search(line):
                    clean_line = line.strip().replace(',', '')
                    drt_metadata_status = clean_line
                    break

    return drt_iteration_number, drt_metadata_status, drt_cpu_time, drt_violations, gpl_cpu_time, gpl_cpu_time_seconds, gpl_last_num_call, drt_first_iteration_violations, gpl_iterations, gpl_last_tns, rsz_tns, starting_inst_area, starting_num_instances, total_resized_gates, total_inserted_buffers

def process_json_file(json_file_path):
    with open(json_file_path, 'r') as file:
        data = json.load(file)
        instance_area = data.get("globalplace__design__instance__area", None)
        cts_tns = data.get("cts__timing__setup__tns", None)
        finish_tns = data.get("finish__timing__setup__tns", None)
        end_instance_count = data.get("globalplace__design__instance__count", None)
        return instance_area, cts_tns, finish_tns, end_instance_count

def process_directories(base_path):
    data = defaultdict(lambda: defaultdict(lambda: {
        'gpl_iterations': None, 'drt_iterations': [], 'drt_status': None, 'drt_cpu_time': None, 'drt_violations': None,
        'gpl_cpu_time': None, 'gpl_cpu_time_seconds': None, 'gpl_last_num_call': None, 'drt_first_iteration_violations': None, 'gpl_last_tns': None, 'rsz_tns': None,
        'starting_inst_area': None, 'starting_num_instances': None, 'total_resized_gates': 0, 'total_inserted_buffers': 0,
        'end_instance_area': None, 'cts_tns': None, 'finish_tns': None, 'end_instance_count': None  # New fields
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
                                drt_iterations, drt_status, drt_cpu_time, drt_violations, gpl_cpu_time, gpl_cpu_time_seconds, gpl_last_num_call, drt_first_iteration_violations, gpl_iterations, gpl_last_tns, rsz_tns, starting_inst_area, starting_num_instances, total_resized_gates, total_inserted_buffers = log_data
                                data[(design_name, technology)][run_config]['gpl_iterations'] = gpl_iterations
                                data[(design_name, technology)][run_config]['drt_iterations'].append(drt_iterations)
                                data[(design_name, technology)][run_config]['drt_status'] = drt_status
                                data[(design_name, technology)][run_config]['drt_cpu_time'] = drt_cpu_time
                                data[(design_name, technology)][run_config]['drt_violations'] = drt_violations
                                data[(design_name, technology)][run_config]['gpl_cpu_time'] = gpl_cpu_time
                                data[(design_name, technology)][run_config]['gpl_cpu_time_seconds'] = gpl_cpu_time_seconds
                                data[(design_name, technology)][run_config]['gpl_last_num_call'] = gpl_last_num_call
                                data[(design_name, technology)][run_config]['drt_first_iteration_violations'] = drt_first_iteration_violations
                                data[(design_name, technology)][run_config]['gpl_last_tns'] = gpl_last_tns
                                data[(design_name, technology)][run_config]['rsz_tns'] = rsz_tns
                                data[(design_name, technology)][run_config]['starting_inst_area'] = starting_inst_area
                                data[(design_name, technology)][run_config]['starting_num_instances'] = starting_num_instances
                                data[(design_name, technology)][run_config]['total_resized_gates'] = total_resized_gates
                                data[(design_name, technology)][run_config]['total_inserted_buffers'] = total_inserted_buffers
                        elif file.endswith('.json'):
                            end_instance_area, cts_tns, finish_tns, end_instance_count = process_json_file(log_file_path)
                            if end_instance_area is not None:
                                data[(design_name, technology)][run_config]['end_instance_area'] = end_instance_area
                            if cts_tns is not None:
                                data[(design_name, technology)][run_config]['cts_tns'] = cts_tns
                            if finish_tns is not None:
                                data[(design_name, technology)][run_config]['finish_tns'] = finish_tns
                            if end_instance_count is not None:
                                data[(design_name, technology)][run_config]['end_instance_count'] = end_instance_count

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
                headers_top.extend([rc] * 15 + [''])
                headers_middle.extend(['6-Final', 'GPL', 'GPL', 'GPL', 'GPL', '3_3-GPL-RSZ', '3_4-RSZ', '4-CTS (json)', '6-Final (json)', 'GPL', 'GPL (json)', 'GPL', 'GPL (json)', '3_3-GPL-RSZ', '3_3-GPL-RSZ', ''])
                headers_bottom.extend(['Status', '# RD iterations', 'Iterations', 'CPU Time (min)', 'Avg. Runtime per Iteration (s)', 'TNS', 'RSZ TNS', 'CTS TNS', 'Finish TNS', 'Start Inst Area (um^2)', 'End Instance Area', 'Start Num Instances', 'End Num Instance', 'Resized Gates', 'Inserted Buffers', ''])
            
            if SHOW_DRT:
                headers_top.extend([rc] * 5 + [''])
                headers_middle.extend(['DRT', 'DRT', 'DRT', 'DRT', 'DRT', ''])
                headers_bottom.extend(['Status', '0th Iteration Violations', 'Iterations', 'CPU Time (min)', ''])

        writer.writerow(headers_top)
        writer.writerow(headers_middle)
        writer.writerow(headers_bottom)

        for (design_name, technology), run_config_data in data.items():
            row = [design_name, technology]
            for rc in run_configs:
                rc_data = run_config_data.get(rc, {
                    'gpl_iterations': None, 'drt_iterations': [''], 'drt_status': '', 'drt_cpu_time': '', 'drt_violations': '',
                    'gpl_cpu_time': None, 'gpl_cpu_time_seconds': None, 'gpl_last_num_call': None, 'drt_first_iteration_violations': None, 'gpl_last_tns': None, 'rsz_tns': None,
                    'starting_inst_area': None, 'starting_num_instances': None, 'total_resized_gates': 0, 'total_inserted_buffers': 0, 'end_instance_area': None,
                    'cts_tns': None, 'finish_tns': None, 'end_instance_count': None
                })
                drt_status = rc_data['drt_status'] if rc_data['drt_status'] is not None else ''
                gpl_iterations = rc_data['gpl_iterations']
                drt_iterations = rc_data['drt_iterations'][0] if rc_data['drt_iterations'] else ''
                drt_cpu_time = rc_data['drt_cpu_time']
                drt_violations = rc_data['drt_violations']
                gpl_cpu_time = rc_data['gpl_cpu_time']
                gpl_cpu_time_seconds = rc_data['gpl_cpu_time_seconds']
                gpl_last_num_call = rc_data['gpl_last_num_call']
                gpl_last_tns = rc_data['gpl_last_tns']
                rsz_tns = rc_data['rsz_tns']
                cts_tns = rc_data['cts_tns']
                finish_tns = rc_data['finish_tns']
                starting_inst_area = rc_data['starting_inst_area']
                end_instance_area = rc_data['end_instance_area']
                starting_num_instances = rc_data['starting_num_instances']
                end_instance_count = rc_data['end_instance_count']
                total_resized_gates = rc_data['total_resized_gates']
                total_inserted_buffers = rc_data['total_inserted_buffers']
                avg_runtime_per_iteration = '{:.2f}'.format(gpl_cpu_time_seconds / float(gpl_iterations)) if gpl_cpu_time_seconds and gpl_iterations else ''

                if SHOW_GPL:
                    row.extend([drt_status, gpl_last_num_call, gpl_iterations, gpl_cpu_time, avg_runtime_per_iteration, gpl_last_tns, rsz_tns, cts_tns, finish_tns, starting_inst_area, end_instance_area, starting_num_instances, end_instance_count, total_resized_gates, total_inserted_buffers, ''])
                
                if SHOW_DRT:
                    row.extend([drt_status, drt_first_iteration_violations, drt_iterations, drt_cpu_time, ''])

            writer.writerow(row)

base_path = '.'
output_file = 'output.csv'
data = process_directories(base_path)
write_to_csv(data, output_file)
