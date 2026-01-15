#!/usr/bin/env python3

import os
import subprocess
import re
import sys
from pathlib import Path

# Configuration
OUTPUT_FILE = "update_ok_summary.txt"
DESIGNS_DIR = "./designs"
LARGE_CHANGE_THRESHOLD = 50

def discover_designs():
    """Discover all platforms and designs with config.mk files."""
    designs = []
    designs_path = Path(DESIGNS_DIR)
    
    print("Discovering platforms and designs...")
    for platform_dir in designs_path.iterdir():
        if platform_dir.is_dir() and platform_dir.name != 'src':
            platform = platform_dir.name
            
            for design_dir in platform_dir.iterdir():
                if design_dir.is_dir():
                    design = design_dir.name
                    config_path = design_dir / "config.mk"
                    
                    if config_path.exists():
                        designs.append((design, platform))
                        print(f"  Found: {design} ({platform})")
    
    return designs

def extract_table(output):
    """Extract the metrics table from make output."""
    lines = output.split('\n')
    table_lines = []
    in_table = False
    
    for line in lines:
        if 'updates:' in line:
            in_table = True
        if in_table:
            if line.startswith('cp -f'):
                break
            table_lines.append(line)
    
    return '\n'.join(table_lines) if table_lines else ""

def parse_failing_metrics(table):
    """Parse failing metrics and calculate percentage changes."""
    large_changes = []
    lines = table.split('\n')
    
    for line in lines:
        if 'Failing' not in line:
            continue
        
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 5:
            continue
        
        metric = parts[1]
        old_str = parts[2]
        new_str = parts[3]
        
        # Try to parse numeric values
        try:
            old_val = float(old_str)
            new_val = float(new_str)
            
            old_abs = abs(old_val)
            new_abs = abs(new_val)
            
            if old_abs > 0.01:
                percent_change = ((new_abs - old_abs) / old_abs) * 100
                percent_change_abs = abs(percent_change)
                
                if percent_change_abs > LARGE_CHANGE_THRESHOLD:
                    large_changes.append({
                        'metric': metric,
                        'old': old_str,
                        'new': new_str,
                        'percent': f"{percent_change:.2f}"
                    })
        except ValueError:
            continue
    
    return large_changes

def parse_tighten_metrics(table):
    """Parse tighten metrics and calculate percentage improvements."""
    large_improvements = []
    lines = table.split('\n')
    
    for line in lines:
        if 'Tighten' not in line:
            continue
        
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 5:
            continue
        
        metric = parts[1]
        old_str = parts[2]
        new_str = parts[3]
        
        # Try to parse numeric values
        try:
            old_val = float(old_str)
            new_val = float(new_str)
            
            old_abs = abs(old_val)
            new_abs = abs(new_val)
            
            if old_abs > 0.01:
                # Calculate improvement (negative means better for negative metrics)
                percent_change = ((new_abs - old_abs) / old_abs) * 100
                percent_change_abs = abs(percent_change)
                
                if percent_change_abs > LARGE_CHANGE_THRESHOLD:
                    large_improvements.append({
                        'metric': metric,
                        'old': old_str,
                        'new': new_str,
                        'percent': f"{percent_change:.2f}"
                    })
        except ValueError:
            continue
    
    return large_improvements

def run_update_ok(design, platform, config_path, platform_home=None, extra_args=None):
    """Run make update_ok and return output."""
    cmd = ['make', f'DESIGN_CONFIG={config_path}']
    if platform_home:
        cmd.append(f'PLATFORM_HOME={platform_home}')
    if extra_args:
        cmd.extend(extra_args)
    cmd.append('update_ok')

    print(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return ""
    except Exception as e:
        print(f"Error running make for {design} ({platform}): {e}")
        return ""

def main():
    # Determine PLATFORM_HOME based on args
    platform_home = None
    if len(sys.argv) > 1 and sys.argv[1] == "private":
        platform_home = "/platforms"

    # Clear previous results
    with open(OUTPUT_FILE, 'w') as f:
        f.write("")
    
    # Discover designs
    designs = discover_designs()
    print(f"\nTotal designs found: {len(designs)}\n")
    if platform_home:
        print(f"Using PLATFORM_HOME={platform_home}\n")
    
    # Track results
    failed_designs = []
    designs_with_failing_checks = []
    large_failing_changes = []
    large_improvements = []
    
    # Process each design
    for design, platform in designs:
        if platform_home and platform not in ["rapidus2hp", "gf12"]:
            continue

        config_path = f"./designs/{platform}/{design}/config.mk"
        
        variants = [([], "")]
        if platform_home == "/platforms" and len(sys.argv) > 1 and sys.argv[1] == "private":
            if platform in ["rapidus2hp", "gf12"]:
                variants.append((["FLOW_VARIANT=verific"], " (verific)"))

        for extra_args, suffix in variants:
            print("=" * 53)
            print(f"make update_ok for {design} ({platform}){suffix}...")
            print("=" * 53)
            
            output = run_update_ok(design, platform, config_path, platform_home, extra_args)
            table = extract_table(output)
            
            if table:
                print(table)
                print()
                
                # Check if output contains "Failing" or "Tighten"
                if "Failing" in output or "Tighten" in output:
                    # Write to summary file
                    with open(OUTPUT_FILE, 'a') as f:
                        f.write("=" * 53 + "\n")
                        f.write(f"make update_ok for {design} ({platform}){suffix}...\n")
                        f.write("=" * 53 + "\n")
                        f.write(table + "\n\n")

                # Check if output contains "Failing"
                if "Failing" in output:
                    designs_with_failing_checks.append(f"{design} ({platform}){suffix}")
                    
                    # Check for large percentage changes
                    changes = parse_failing_metrics(table)
                    for change in changes:
                        large_failing_changes.append({
                            'design': design,
                            'platform': f"{platform}{suffix}",
                            'metric': change['metric'],
                            'percent': change['percent'],
                            'old': change['old'],
                            'new': change['new']
                        })
            
                # Check for large improvements in Tighten metrics
                improvements = parse_tighten_metrics(table)
                for improvement in improvements:
                    large_improvements.append({
                        'design': design,
                        'platform': f"{platform}{suffix}",
                        'metric': improvement['metric'],
                        'percent': improvement['percent'],
                        'old': improvement['old'],
                        'new': improvement['new']
                    })
            else:
                print(f"No metrics table found for {design} ({platform}){suffix}")
                failed_designs.append(f"{design} ({platform}){suffix}")
                print()
    
    # Final report
    print("-" * 53)
    print("Final report:")
    
    if failed_designs:
        print("\nSome designs only tightened or did not produce an output metrics table from update_ok:")
        for f in failed_designs:
            print(f" - {f}")
    
    if designs_with_failing_checks:
        print("\nDesigns with failing checks:")
        for f in designs_with_failing_checks:
            print(f" - {f}")
    else:
        print("\nNo designs had failing checks.")
    
    if large_failing_changes:
        msg = f"\nLarge percentage changes in failing metrics (>{LARGE_CHANGE_THRESHOLD}%):"
        print(msg)
        with open(OUTPUT_FILE, 'a') as f:
            f.write(msg + "\n")
        
        # Sort by percentage change (descending)
        large_failing_changes.sort(key=lambda x: float(x['percent']), reverse=True)
        
        # Calculate column widths for alignment
        max_design_len = max(len(f"{c['design']} ({c['platform']})") for c in large_failing_changes)
        max_metric_len = max(len(c['metric']) for c in large_failing_changes)
        max_percent_len = max(len(c['percent']) for c in large_failing_changes)
        
        with open(OUTPUT_FILE, 'a') as f:
            for change in large_failing_changes:
                design_platform = f"{change['design']} ({change['platform']})"
                line = (f" - {design_platform:<{max_design_len}}  "
                      f"{change['metric']:<{max_metric_len}}  "
                      f"{change['percent']:>{max_percent_len}}%  "
                      f"({change['old']} → {change['new']})")
                print(line)
                f.write(line + "\n")
    
    if large_improvements:
        msg = f"\nLarge percentage improvements in tighten metrics (>{LARGE_CHANGE_THRESHOLD}%):"
        print(msg)
        with open(OUTPUT_FILE, 'a') as f:
            f.write(msg + "\n")
        
        # Sort by absolute percentage change (descending)
        large_improvements.sort(key=lambda x: abs(float(x['percent'])), reverse=True)
        
        # Calculate column widths for alignment
        max_design_len = max(len(f"{c['design']} ({c['platform']})") for c in large_improvements)
        max_metric_len = max(len(c['metric']) for c in large_improvements)
        max_percent_len = max(len(c['percent']) for c in large_improvements)
        
        with open(OUTPUT_FILE, 'a') as f:
            for improvement in large_improvements:
                design_platform = f"{improvement['design']} ({improvement['platform']})"
                line = (f" - {design_platform:<{max_design_len}}  "
                      f"{improvement['metric']:<{max_metric_len}}  "
                      f"{improvement['percent']:>{max_percent_len}}%  "
                      f"({improvement['old']} → {improvement['new']})")
                print(line)
                f.write(line + "\n")
    
    print("\n" + "-" * 53)
    print("Summary counts:")
    print(f"  Total designs processed: {len(designs)}")
    print(f"  Designs with failing checks: {len(designs_with_failing_checks)}")
    print(f"  Designs without metrics table: {len(failed_designs)}")
    print(f"  Large failing metric changes: {len(large_failing_changes)}")
    print(f"  Large improvements: {len(large_improvements)}")
    print("-" * 53)
    print(f"\nSummary saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
