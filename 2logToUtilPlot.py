import os
import re
import zipfile
import matplotlib.pyplot as plt
from pathlib import Path
from collections import defaultdict
import matplotlib.cm as cm
import numpy as np

def parse_logs_from_zip(zip_path):
    # Dictionary structure: data[(platform, variant)][design][stage] = utilization
    data = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    
    pattern = re.compile(r"(\d+_\d+_\w+)\.log:.* (\d+)% utilization")
    # [INFO IFP-0107] Defining die area using utilization: 45.00% and aspect ratio: 1.
    user_util_pattern = re.compile(r"IFP-0107.*utilization:\s*([\d.]+)%")
    # [INFO IFP-0104] Effective utilization:                0.459
    effective_util_pattern = re.compile(r"IFP-0104.*Effective utilization:\s*([\d.]+)")

    if not os.path.exists(zip_path):
        print(f"Error: {zip_path} not found.")
        return data

    with zipfile.ZipFile(zip_path, 'r') as z:
        for file_info in z.infolist():
            # Skip directories and non-log files
            if file_info.is_dir() or not file_info.filename.endswith(".log"):
                continue

            try:
                with z.open(file_info) as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    internal_path = Path(file_info.filename)
                    parts = internal_path.parts

                    if len(parts) < 4:
                        continue

                    offset = 1 if parts[0] == 'logs' else 0
                    platform = parts[offset]
                    design   = parts[offset + 1]
                    variant  = parts[offset + 2]

                    for line in content.splitlines():
                        # Existing: design area utilization per stage
                        if "design area" in line.lower():
                            match = pattern.search(f"{internal_path.name}:{line}")

                            if match:
                                stage, util_val = match.groups()
                                util = int(util_val)

                                if util > 0:
                                        data[(platform, variant)][design][stage] = util

                        # User-given utilization (may not be present)
                        elif "IFP-0107" in line:
                            match = user_util_pattern.search(line)
                            if match:
                                util = float(match.group(1))
                                if util > 0:
                                    data[(platform, variant)][design]["0_0_user_util"] = round(util)

                        # Effective utilization (decimal, convert to %)
                        elif "IFP-0104" in line:
                            match = effective_util_pattern.search(line)
                            if match:
                                util = float(match.group(1)) * 100
                                if util > 0:
                                    data[(platform, variant)][design]["0_1_effective_util"] = round(util)
            except Exception as e:
                print(f"Could not read {file_info.filename}: {e}")
            
    return data

def plot_data(data):
    # This loop ensures every unique (platform, variant) combination creates its own image
    print(f"\nFound {len(data)} unique combinations of Platform + Variant.")
    
    for (platform, variant), designs in data.items():
        print(f"Plotting Platform: {platform}, Variant: {variant} ({len(designs)} designs)")
        
        fig, ax = plt.subplots(figsize=(15, 7))
        design_names = sorted(designs.keys())
        num_designs = len(design_names)
        
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

        ax.set_title(f"Utilization per Stage\nPlatform: {platform} | Variant: {variant}", fontsize=14, pad=20)
        ax.set_xlabel("Design Stage", fontsize=12)
        ax.set_ylabel("Utilization (%)", fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.6)
        plt.xticks(rotation=45, ha='right')
        
        num_cols = 1 if num_designs <= 20 else 2
        plt.subplots_adjust(right=0.75 if num_cols == 2 else 0.85)

        leg = ax.legend(title="Designs", loc='center left', bbox_to_anchor=(1.02, 0.5), 
                        borderaxespad=0, fontsize=8, ncol=num_cols)

        filename = f"utilization_{platform}_{variant}.png"
        plt.savefig(filename, dpi=150, bbox_extra_artists=(leg,), bbox_inches='tight')
        plt.close(fig)
        print(f"   -> Saved: {filename}")

if __name__ == "__main__":
    zip_filename = "logs.zip" 
    extracted_data = parse_logs_from_zip(zip_filename)
    
    if not extracted_data:
        print(f"No valid data found in {zip_filename}.")
    else:
        plot_data(extracted_data)
