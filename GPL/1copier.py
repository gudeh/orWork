# You need to manually set the paths of the log directories.
# And manually change the position of 'path_parts' (between '/') of the name of each output directory inside the input path

import os
import shutil

def copy_files_from_sources_to_separate_dest(src_roots, dest_root_base):
    for src_root in src_roots:
        # Split the path and extract the unique name/identifier between the 4th and 5th '/'
        path_parts = src_root.strip('/').split('/')
        # Ensure there are enough parts in the path to extract the desired segment
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
