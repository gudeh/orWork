import os
import re
import zipfile
import matplotlib.pyplot as plt
from pathlib import Path
from collections import defaultdict
import matplotlib.cm as cm
import numpy as np

def parse_logs_from_zip(zip_path):
    # Structure: data[platform][design][stage] = utilization
    data = defaultdict(lambda: defaultdict(dict))
    
    # Regex to capture the stage name from filename and the % from the line
    pattern = re.compile(r"(\d+_\d+_\w+)\.log:.* (\d+)% utilization")

    if not os.path.exists(zip_path):
        print(f"Error: {zip_path} not found.")
        return data

    with zipfile.ZipFile(zip_path, 'r') as z:
        # Loop through every file inside the zip
        for file_info in z.infolist():
            if file_info.filename.endswith(".log"):
                try:
                    # Read file content as text
                    with z.open(file_info) as f:
                        for line_bytes in f:
                            line = line_bytes.decode('utf-8', errors='ignore')
                            
                            if "design area" in line.lower():
                                # Get the filename part of the internal path
                                internal_path = Path(file_info.filename)
                                match = pattern.search(f"{internal_path.name}:{line}")
                                
                                if match:
                                    stage, util_val = match.groups()
                                    util = int(util_val)
                                    
                                    if util > 0:
                                        # internal_path parts: ('logs', 'sky130hd', 'microwatt', 'base', 'file.log')
                                        parts = internal_path.parts
                                        # Adjusting index based on typical OpenROAD flow zip structure
                                        if len(parts) >= 4:
                                            # If zip starts with 'logs/', platform is parts[1]
                                            # If zip starts with platform, platform is parts[0]
                                            platform = parts[1] if parts[0] == 'logs' else parts[0]
                                            design = parts[2] if parts[0] == 'logs' else parts[1]
                                            data[platform][design][stage] = util
                except Exception as e:
                    print(f"Could not read {file_info.filename} inside zip: {e}")
            
    return data

def plot_data(data):
    for platform, designs in data.items():
        fig, ax = plt.subplots(figsize=(15, 7))
        
        design_names = sorted(designs.keys())
        num_designs = len(design_names)
        
        # Color & Style cycling (20 colors * 4 styles = 80 unique combinations)
        colors = cm.get_cmap('tab20')(np.linspace(0, 1, min(num_designs, 20)))
        line_styles = ['-', '--', '-.', ':']
        
        for i, design_name in enumerate(design_names):
            stages_dict = designs[design_name]
            sorted_stages = sorted(stages_dict.keys())
            utils = [stages_dict[s] for s in sorted_stages]
            
            color = colors[i % 20]
            style = line_styles[(i // 20) % len(line_styles)]
            
            ax.plot(sorted_stages, utils, 
                    marker='o', linestyle=style, color=color, 
                    label=design_name, linewidth=1.5, markersize=4)

        ax.set_title(f"Utilization per Stage - Platform: {platform}", fontsize=14, pad=20)
        ax.set_xlabel("Design Stage", fontsize=12)
        ax.set_ylabel("Utilization (%)", fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.6)
        plt.xticks(rotation=45, ha='right')
        
        num_cols = 1 if num_designs <= 20 else 2

        # Provide a buffer for the legend
        plt.subplots_adjust(right=0.75 if num_cols == 2 else 0.85)

        leg = ax.legend(title="Designs", 
                        loc='center left', 
                        bbox_to_anchor=(1.02, 0.5), 
                        borderaxespad=0, 
                        fontsize=8, 
                        ncol=num_cols)

        filename = f"utilization_{platform}.png"
        plt.savefig(filename, dpi=150, bbox_extra_artists=(leg,), bbox_inches='tight')
        
        print(f"Generated plot: {filename}")
        plt.show()

if __name__ == "__main__":
    # Change 'logs.zip' to your actual zip filename
    zip_filename = "logs.zip" 
    extracted_data = parse_logs_from_zip(zip_filename)
    
    if not extracted_data:
        print(f"No data found in {zip_filename}. Ensure the zip contains .log files.")
    else:
        plot_data(extracted_data)
