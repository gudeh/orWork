import os
import shutil

def copy_files_from_sources_to_separate_dest(src_roots, dest_root_base):
    for src_root in src_roots:
        # Split the path and extract the unique name/identifier between the 4th and 5th '/'
        path_parts = src_root.strip('/').split('/')
        # Ensure there are enough parts in the path to extract the desired segment
        if len(path_parts) >= 5:
            src_identifier = path_parts[3]
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

src_roots = [
    '/home/gudeh/Desktop/inflatIter3/flow/logs',
    '/home/gudeh/Desktop/targetRC08/flow/logs/',
    '/home/gudeh/Desktop/targetRC125/flow/logs/',
    '/home/gudeh/Desktop/3OpenROAD-flow-scripts/flow/logs/',
    '/home/gudeh/Desktop/2OpenROAD-flow-scripts/flow/logs/',
    '/home/gudeh/Desktop/1OpenROAD-flow-scripts/flow/logs/'
]
dest_root = './'
copy_files_from_sources_to_separate_dest(src_roots, dest_root)
