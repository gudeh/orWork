import os
import json
import re
import matplotlib.pyplot as plt

# Configuration
LOG_DIR = "."
OUTPUT_FILE = "variant_comparison_plots.png"
SHOW_TNS = False  # Set to False to hide TNS plots

def get_metrics(log_dir):
    data = {}
    
    if not os.path.exists(log_dir):
        print(f"Error: Directory {log_dir} not found.")
        return {}

    # Get all subdirectories (variants)
    try:
        variants = [d for d in os.listdir(log_dir) if os.path.isdir(os.path.join(log_dir, d))]
    except OSError as e:
        print(f"Error accessing directory: {e}")
        return {}
    
    for variant in variants:
        variant_path = os.path.join(log_dir, variant)
        metrics = {
            'tns': None,
            'ws': None,
            'dp_tns': None,
            'dp_ws': None,
            'congestion': None,
            'exit_status': None,
            'inflation': None
        }
        
        # 1. Parse JSON report for TNS and WS
        # File: variant/6_report.json
        json_path = os.path.join(variant_path, "6_report.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as f:
                    report = json.load(f)
                    metrics['tns'] = report.get("finish__timing__setup__tns")
                    metrics['ws'] = report.get("finish__timing__setup__ws")
            except Exception as e:
                print(f"Warning: Failed to parse {json_path}: {e}")

        # 1.5 Parse JSON report for Detailed Place TNS and WS
        # File: variant/3_5_place_dp.json
        dp_json_path = os.path.join(variant_path, "3_5_place_dp.json")
        if os.path.exists(dp_json_path):
            try:
                with open(dp_json_path, 'r') as f:
                    report = json.load(f)
                    metrics['dp_tns'] = report.get("detailedplace__timing__setup__tns")
                    metrics['dp_ws'] = report.get("detailedplace__timing__setup__ws")
            except Exception as e:
                print(f"Warning: Failed to parse {dp_json_path}: {e}")

        # 2. Parse Log file for Congestion
        # File: variant/3_3_place_gp.log
        # Pattern: [INFO GPL-1005] Routability final weighted congestion: 1.0674
        log_path = os.path.join(variant_path, "3_3_place_gp.log")
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r') as f:
                    content = f.read()
                    match = re.search(r"\[INFO GPL-1005\] Routability final weighted congestion:\s+([\d\.]+)", content)
                    if match:
                        metrics['congestion'] = float(match.group(1))
                    
                    # Check for exit status
                    if "[INFO GPL-0050]" in content:
                        metrics['exit_status'] = 1
                    elif "[INFO GPL-0054]" in content:
                        metrics['exit_status'] = -1
                    else:
                        metrics['exit_status'] = 0

                    # Check for inflation percentage
                    # Pattern: [INFO GPL-1012] Total routability artificial inflation: 9150.31 (+35.96%)
                    match_inf = re.search(r"\[INFO GPL-1012\] Total routability artificial inflation:.*?\(.*?([\d\.]+)\%\)", content)
                    if match_inf:
                        metrics['inflation'] = float(match_inf.group(1))

            except Exception as e:
                print(f"Warning: Failed to parse {log_path}: {e}")
        
        # Only add if we found relevant data
        if any(v is not None for v in metrics.values()):
            data[variant] = metrics
            
    return data

def plot_data(data):
    # Sort variants naturally (handling floats in strings)
    def natural_keys(text):
        def try_float(s):
            try:
                return float(s)
            except ValueError:
                return s
        return [try_float(c) for c in re.split(r'(\d+\.\d+|\d+)', text)]

    # Sort variants for X-axis
    sorted_variants = sorted(data.keys(), key=natural_keys)
    
    # Extract lists for plotting, handling None values with 0 or NaN
    tns_vals = [data[v]['tns'] if data[v]['tns'] is not None else 0 for v in sorted_variants]
    ws_vals = [data[v]['ws'] if data[v]['ws'] is not None else 0 for v in sorted_variants]
    dp_tns_vals = [data[v]['dp_tns'] if data[v]['dp_tns'] is not None else 0 for v in sorted_variants]
    dp_ws_vals = [data[v]['dp_ws'] if data[v]['dp_ws'] is not None else 0 for v in sorted_variants]
    cong_vals = [data[v]['congestion'] if data[v]['congestion'] is not None else 0 for v in sorted_variants]
    exit_vals = [data[v]['exit_status'] if data[v]['exit_status'] is not None else 0 for v in sorted_variants]
    inf_vals = [data[v]['inflation'] if data[v]['inflation'] is not None else 0 for v in sorted_variants]
    
    # Determine colors based on 'default' variant
    tns_colors = 'tab:blue'
    ws_colors = 'tab:red'
    dp_tns_colors = 'tab:blue'
    dp_ws_colors = 'tab:red'
    cong_colors = 'tab:green'
    inf_colors = 'tab:purple'

    if 'default' in data:
        def get_colors(variants, values, ref_val, higher_is_better=True):
            colors = []
            # Handle case where ref_val might be None
            if ref_val is None:
                ref_val = 0

            for var, val in zip(variants, values):
                if var == 'default':
                    colors.append('gray')
                elif val > ref_val:
                    colors.append('tab:green' if higher_is_better else 'tab:red')
                elif val < ref_val:
                    colors.append('tab:red' if higher_is_better else 'tab:green')
                else:
                    colors.append('gray')
            return colors

        def_metrics = data['default']
        # TNS/WS: Higher (less negative) is usually better
        tns_colors = get_colors(sorted_variants, tns_vals, def_metrics['tns'], higher_is_better=True)
        ws_colors = get_colors(sorted_variants, ws_vals, def_metrics['ws'], higher_is_better=True)
        dp_tns_colors = get_colors(sorted_variants, dp_tns_vals, def_metrics['dp_tns'], higher_is_better=True)
        dp_ws_colors = get_colors(sorted_variants, dp_ws_vals, def_metrics['dp_ws'], higher_is_better=True)
        # Congestion: Lower is better
        cong_colors = get_colors(sorted_variants, cong_vals, def_metrics['congestion'], higher_is_better=False)
        # Inflation: Lower is better
        inf_colors = get_colors(sorted_variants, inf_vals, def_metrics['inflation'], higher_is_better=False)

    # Determine number of subplots based on SHOW_TNS
    if SHOW_TNS:
        num_plots = 7
        fig, axes = plt.subplots(num_plots, 1, figsize=(14, 4 * num_plots), sharex=True)
        (ax1, ax2, ax3, ax4, ax5, ax6, ax7) = axes
    else:
        num_plots = 5
        fig, axes = plt.subplots(num_plots, 1, figsize=(14, 4 * num_plots), sharex=True)
        (ax2, ax4, ax5, ax6, ax7) = axes # Map to same variable names for convenience, skipping TNS axes

    if SHOW_TNS:
        # Plot Finish TNS
        ax1.bar(sorted_variants, tns_vals, color=tns_colors, alpha=0.7)
        ax1.set_title('Finish Timing Setup TNS')
        ax1.set_ylabel('TNS')
        ax1.grid(axis='y', linestyle='--', alpha=0.5)
    
    # Plot Finish WS
    ax2.bar(sorted_variants, ws_vals, color=ws_colors, alpha=0.7)
    ax2.set_title('Finish Timing Setup WS')
    ax2.set_ylabel('WS')
    ax2.grid(axis='y', linestyle='--', alpha=0.5)

    if SHOW_TNS:
        # Plot DP TNS
        ax3.bar(sorted_variants, dp_tns_vals, color=dp_tns_colors, alpha=0.7)
        ax3.set_title('Detailed Place Timing Setup TNS')
        ax3.set_ylabel('TNS')
        ax3.grid(axis='y', linestyle='--', alpha=0.5)

    # Plot DP WS
    ax4.bar(sorted_variants, dp_ws_vals, color=dp_ws_colors, alpha=0.7)
    ax4.set_title('Detailed Place Timing Setup WS')
    ax4.set_ylabel('WS')
    ax4.grid(axis='y', linestyle='--', alpha=0.5)

    # Plot Congestion
    ax5.bar(sorted_variants, cong_vals, color=cong_colors, alpha=0.7)
    ax5.set_title('GPL Final Weighted Congestion (GPL-1005)')
    ax5.set_ylabel('Congestion')
    ax5.set_ylim(bottom=0.9)
    ax5.grid(axis='y', linestyle='--', alpha=0.5)
    
    # Plot Exit Status
    colors = ['tab:green' if v == 1 else 'tab:orange' if v == -1 else 'gray' for v in exit_vals]
    ax6.bar(sorted_variants, exit_vals, color=colors, alpha=0.7)
    ax6.set_title('Routability Exit Status')
    ax6.set_ylabel('Routability Status')
    ax6.set_yticks([-1, 0, 1])
    ax6.set_yticklabels(['No Improv\n3x(GPL-54)', 'Neither', 'Target hit\n(GPL-50)'])
    ax6.grid(axis='y', linestyle='--', alpha=0.5)

    # Plot Inflation
    ax7.bar(sorted_variants, inf_vals, color=inf_colors, alpha=0.7)
    ax7.set_title('Routability Artificial Inflation (GPL-1012)')
    ax7.set_ylabel('Inflation (%)')
    ax7.grid(axis='y', linestyle='--', alpha=0.5)

    # Rotate x-axis labels for readability
    plt.xticks(rotation=45, ha='right')
    plt.xlabel('Flow Variant')
    
    plt.tight_layout()
    
    plt.savefig(OUTPUT_FILE)
    print(f"Plots successfully saved to {os.path.abspath(OUTPUT_FILE)}")

if __name__ == "__main__":
    print(f"Scanning directory: {LOG_DIR}")
    metrics_data = get_metrics(LOG_DIR)
    
    if metrics_data:
        print(f"Found data for {len(metrics_data)} variants.")
        plot_data(metrics_data)
    else:
        print("No matching data found to plot.")
