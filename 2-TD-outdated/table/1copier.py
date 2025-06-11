# useful to unpack all artifacts from jenkins:
# for file in *.zip; do unzip "$file" -d "${file%%.*}"; done
import os
import shutil
import json

def merge_json_files(json_files, output_path):
    merged_data = {}
    
    for json_file in json_files:
        with open(json_file, 'r') as file:
            data = json.load(file)
            merged_data.update(data)
    
    with open(output_path, 'w') as output_file:
        json.dump(merged_data, output_file, indent=4)

def copy_files_from_sources_to_separate_dest(src_roots, dest_root_base):
    for src_root in src_roots:
        path_parts = src_root.strip('/').split('/')
        if len(path_parts) >= 2:
            src_identifier = path_parts[2]
        else:
            print(f"Invalid source path, not enough segments to extract identifier: {src_root}")
            continue
        
        dest_root = os.path.join(dest_root_base, src_identifier)
        if not os.path.exists(dest_root):
            os.makedirs(dest_root)

        if not os.path.exists(src_root):
            print(f"Source root not found: {src_root}")
            continue
        
        for folder in os.listdir(src_root):
            folder_path = os.path.join(src_root, folder)
            
            if os.path.isdir(folder_path):
                dest_folder_path = os.path.join(dest_root, folder)
                
                if not os.path.exists(dest_folder_path):
                    os.makedirs(dest_folder_path)
                
                for item in os.listdir(folder_path):
                    item_path = os.path.join(folder_path, item)
                    
                    if os.path.isfile(item_path):
                        shutil.copy2(item_path, dest_folder_path)
                        
                        if item.endswith(".log"):
                            log_name = os.path.splitext(item)[0]
                            log_subdir = os.path.join(folder_path, log_name)  # Add the log name to the path
                            base_directory = os.path.join(log_subdir, 'base')
                            if os.path.exists(base_directory) and os.path.isdir(base_directory):
                                json_files = [os.path.join(base_directory, f) for f in os.listdir(base_directory) if f.endswith(".json")]
                                if json_files:
                                    merged_json_path = os.path.join(dest_folder_path, f"{log_name}.json")
                                    merge_json_files(json_files, merged_json_path)

base_path = '../sourceData/'
directories = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
src_roots = []

if directories:
    for directory_name in directories:
        src_roots.append(os.path.join(base_path, directory_name, 'logs/'))
else:
    print("No directories found.")

print("src_roots", src_roots)
                        
dest_root = './'
copy_files_from_sources_to_separate_dest(src_roots, dest_root)
