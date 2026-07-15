#!/usr/bin/env python3

import os
import shutil
import subprocess
import re
import sys
from pathlib import Path

# Configuration
OUTPUT_FILE = "update_ok_summary.txt"
DESIGNS_DIR = "./designs"
LARGE_CHANGE_THRESHOLD = 50

# Metrics containing this substring (e.g. netlist hashes) are not treated as
# "real" failures on their own -- they change on every netlist edit and
# shouldn't by themselves trigger a metrics update.
IGNORED_METRIC_SUBSTRING = "hash"

# For rapidus we use a fixed path at "~/workspace/rapidus2/designs", 
#  make sure to have the reports with new metrics at ORFS folder to call this script.
#  updates are applied on the fixed path, the local ORFS folder will be left outdated.

# Per-platform settings used in "private" mode.
# Each private platform may live under a different repo path, with its
# design configs either local (./designs) or inside that repo.
#   home    -> value passed as PLATFORM_HOME
#   designs -> root directory holding <platform>/<design>/config.mk
# Fixed checkout metric updates get committed into, regardless of which
# ORFS folder this script is invoked from.
RAPIDUS2_ROOT = os.path.expanduser("~/workspace/rapidus2")

PRIVATE_PLATFORMS = {
    "rapidus2hp": {
        "home": "/platforms/rapidus-repo",
        # Write metric updates into our own checkout so they can be committed,
        # rather than the read-only /platforms install.
        "designs": os.path.join(RAPIDUS2_ROOT, "designs"),
    },
    "gf12": {
        "home": "/platforms",
        "designs": DESIGNS_DIR,
    },
}


def designs_root(platform, private):
    """Directory under which <platform>/<design>/config.mk is found."""
    if private and platform in PRIVATE_PLATFORMS:
        return PRIVATE_PLATFORMS[platform]["designs"]
    return DESIGNS_DIR

def _git_root(cwd=None):
    result = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],
        capture_output=True, text=True, cwd=cwd
    )
    return result.stdout.strip()

GIT_ROOT = _git_root()

_REPO_ROOT_CACHE = {}

def repo_root_for(platform, private):
    """Git repo root containing this platform's design configs. Private
    platforms with designs living outside GIT_ROOT (e.g. rapidus2hp) have
    their changes committed in their own repo, not the invoking ORFS repo."""
    root = designs_root(platform, private)
    if root not in _REPO_ROOT_CACHE:
        _REPO_ROOT_CACHE[root] = _git_root(cwd=root) or GIT_ROOT
    return _REPO_ROOT_CACHE[root]

def sync_private_designs():
    """Copy each private platform's current design/rule files from its
    canonical checkout (e.g. ~/workspace/rapidus2) into this ORFS folder's
    own local designs dir, so whichever ORFS copy runs the flow does so
    against up-to-date config/constraints/rules, and the metrics update_ok
    later compares are meaningful (not stale vs. the canonical baseline).
    """
    for platform, info in PRIVATE_PLATFORMS.items():
        src = Path(info["designs"]) / platform
        dst = Path(DESIGNS_DIR) / platform

        if src.resolve() == dst.resolve():
            continue
        if not src.is_dir():
            print(f"Skipping sync for {platform}: {src} does not exist")
            continue

        if dst.is_symlink() and not dst.exists():
            print(f"Removing stale symlink {dst}")
            dst.unlink()

        print(f"Syncing {platform} designs: {src} -> {dst}")
        shutil.copytree(src, dst, dirs_exist_ok=True)


def discover_designs(private=False):
    """Discover all platforms and designs with config.mk files."""
    designs = []
    seen = set()

    # Always scan the local ./designs; in private mode also scan any
    # private platform whose designs live in a separate repo.
    roots = [DESIGNS_DIR]
    if private:
        for info in PRIVATE_PLATFORMS.values():
            if info["designs"] not in roots:
                roots.append(info["designs"])

    print("Discovering platforms and designs...")
    for root in roots:
        root_path = Path(root)
        if not root_path.is_dir():
            continue

        for platform_dir in root_path.iterdir():
            if platform_dir.is_dir() and platform_dir.name != 'src':
                platform = platform_dir.name

                for design_dir in platform_dir.iterdir():
                    if design_dir.is_dir():
                        design = design_dir.name
                        config_path = design_dir / "config.mk"

                        if config_path.exists() and (design, platform) not in seen:
                            seen.add((design, platform))
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

def has_real_failing_metric(table):
    """Return True if the table has a Failing row whose metric isn't in the
    ignored set (e.g. netlist hashes), i.e. a failure worth updating for."""
    for line in table.split('\n'):
        if 'Failing' not in line:
            continue

        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 5:
            continue

        metric = parts[1]
        if IGNORED_METRIC_SUBSTRING in metric.lower():
            continue

        return True

    return False

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

# Files each repo's update_ok runs actually modified and kept, keyed by
# repo root. Only these are ever committed -- committing everything
# `git diff` reports would sweep in unrelated working-tree changes
# (stray deletions, submodule pointer bumps, ...).
KEPT_FILES = {}


def commit_updates_in(repo_root):
    """git add + signed-off commit the files kept by this script's own
    update_ok runs in repo_root, using the update_ok summary (with its
    non-'====' title line) as the commit message. No-op if nothing was
    actually kept there."""
    if not repo_root:
        return

    # Restrict to files still modified, in case something reverted them.
    modified = KEPT_FILES.get(repo_root, set()) & get_modified_files(repo_root)
    if not modified:
        return

    summary_path = os.path.abspath(OUTPUT_FILE)
    subprocess.run(['git', 'add'] + list(modified), cwd=repo_root, check=True)
    result = subprocess.run(
        ['git', 'commit', '-s', '-F', summary_path],
        cwd=repo_root, capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"\nCommitted metric updates in {repo_root}")
    else:
        print(f"\nFailed to commit in {repo_root}:\n{result.stdout}{result.stderr}")


def commit_updates():
    """Commit kept metric updates in each repo they can land in: rapidus
    always at its fixed RAPIDUS2_ROOT checkout, other platforms (e.g. gf12)
    in the ORFS repo this script was invoked from."""
    rapidus_repo_root = _git_root(cwd=RAPIDUS2_ROOT)
    if not rapidus_repo_root:
        print(f"\nSkipping rapidus commit: {RAPIDUS2_ROOT} is not a git checkout")
    else:
        commit_updates_in(rapidus_repo_root)

    if GIT_ROOT and GIT_ROOT != rapidus_repo_root:
        commit_updates_in(GIT_ROOT)


def get_modified_files(repo_root=GIT_ROOT):
    """Return the set of tracked files currently modified according to git."""
    result = subprocess.run(
        ['git', 'diff', '--name-only'],
        capture_output=True, text=True, cwd=repo_root
    )
    lines = result.stdout.strip().split('\n')
    return set(lines) if lines != [''] else set()


def revert_files(files_before, files_after, repo_root=GIT_ROOT):
    """Revert files that were modified by the last make update_ok call."""
    new_files = list(files_after - files_before)
    if new_files:
        subprocess.run(['git', 'checkout', '--'] + new_files, capture_output=True, cwd=repo_root)
        print(f"  Reverted (tighten-only): {', '.join(new_files)}")


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
    # Determine whether we're running private platforms
    private = len(sys.argv) > 1 and sys.argv[1] == "private"

    if private:
        sync_private_designs()

    # Clear previous results. The first line becomes the commit subject, so
    # keep it a plain title rather than the "====" table-header line.
    with open(OUTPUT_FILE, 'w') as f:
        f.write("Update OK metrics\n\n")

    # Discover designs
    designs = discover_designs(private)
    print(f"\nTotal designs found: {len(designs)}\n")
    if private:
        for plat, info in PRIVATE_PLATFORMS.items():
            print(f"Using PLATFORM_HOME={info['home']} for {plat}")
        print()
    
    # Track results
    failed_designs = []
    designs_with_failing_checks = []
    large_failing_changes = []
    large_improvements = []

    # Process each design
    for design, platform in designs:
        if private and platform not in PRIVATE_PLATFORMS:
            continue

        platform_home = PRIVATE_PLATFORMS[platform]["home"] if private else None
        repo_root = repo_root_for(platform, private)

        config_path = f"{designs_root(platform, private)}/{platform}/{design}/config.mk"

        variants = [([], "")]
        if private and platform in PRIVATE_PLATFORMS:
            variants.append((["FLOW_VARIANT=verific"], " (verific)"))

        for extra_args, suffix in variants:
            print("=" * 53)
            print(f"make update_ok for {design} ({platform}){suffix}...")
            print("=" * 53)

            files_before = get_modified_files(repo_root)
            output = run_update_ok(design, platform, config_path, platform_home, extra_args)
            files_after = get_modified_files(repo_root)
            table = extract_table(output)

            if table:
                print(table)
                print()

                # Only keep the update if some non-ignored (e.g. non-hash)
                # metric is actually failing; otherwise treat like a
                # tighten-only run and revert.
                real_failing = has_real_failing_metric(table)

                if real_failing:
                    KEPT_FILES.setdefault(repo_root, set()).update(
                        files_after - files_before)
                else:
                    revert_files(files_before, files_after, repo_root)

                # Write to summary file only for designs that were actually updated
                if real_failing:
                    with open(OUTPUT_FILE, 'a') as f:
                        f.write(f"## make update_ok for {design} ({platform}){suffix}...\n")
                        f.write(table + "\n\n")

                if real_failing:
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

                # Check for large improvements in Tighten metrics (only for updated designs)
                improvements = parse_tighten_metrics(table) if real_failing else []
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

    commit_updates()

if __name__ == "__main__":
    main()
