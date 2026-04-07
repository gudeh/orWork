#!/usr/bin/env bash

## SPDX-License-Identifier: BSD-3-Clause
## Copyright (c) 2024-2026, The OpenROAD Authors

# Update .ok files for all failed tests found in ctest output.
#
# Usage:
#   --rerun-failed
#   ctest --test-dir ./build --output-on-failure -j 32 2>&1 | tee ctest_output.txt | ./updateOkAll.sh
#   ./updateOkAll.sh ctest_output.txt

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Collect failed tests grouped by module.
# Use awk to skip to the failed-tests section and extract "MODULE.testname.ext" tokens.
declare -A module_tests

while read -r token; do
    noext="${token%.*}"       # dpl.simple10
    module="${noext%%.*}"     # dpl
    testname="${noext#*.}"    # simple10
    if [ -n "${module_tests[$module]+x}" ]; then
        module_tests[$module]+=" $testname"
    else
        module_tests[$module]="$testname"
    fi
done < <(awk '
    /The following tests FAILED:/ { found=1; next }
    found && /\(Failed\)/ {
        for (i=1; i<=NF; i++) {
            if ($i ~ /\.(tcl|py)$/) { print $i; break }
        }
    }
' "${1:-/dev/stdin}")

echo "Finished parsing test output."

if [ ${#module_tests[@]} -eq 0 ]; then
    echo "No failed tests found."
    exit 0
fi

# For each module, cd into its test directory and call save_ok.
for module in "${!module_tests[@]}"; do
    if [ "$module" = "openroad" ]; then
        test_dir="$SCRIPT_DIR/test"
    else
        test_dir="$SCRIPT_DIR/src/$module/test"
    fi

    if [ ! -d "$test_dir" ]; then
        echo "Warning: test directory not found for module '$module': $test_dir"
        continue
    fi

    echo "=== $module ==="
    if [ -f "$test_dir/save_ok" ]; then
        # shellcheck disable=SC2086
        (cd "$test_dir" && ./save_ok ${module_tests[$module]})
    else
        # No save_ok script — copy logs manually (same logic as save_ok).
        for test_name in ${module_tests[$module]}; do
            if [ -f "$test_dir/results/${test_name}-tcl.log" ]; then
                cp "$test_dir/results/${test_name}-tcl.log" "$test_dir/${test_name}.ok"
                echo "$test_name"
            elif [ -f "$test_dir/results/${test_name}-py.log" ]; then
                cp "$test_dir/results/${test_name}-py.log" "$test_dir/${test_name}.ok"
                echo "$test_name"
            else
                echo "\"${test_name}\" log file not found"
            fi
        done
    fi
done
