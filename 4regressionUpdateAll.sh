#!/usr/bin/env bash

## SPDX-License-Identifier: BSD-3-Clause
## Copyright (c) 2024-2026, The OpenROAD Authors

# Full regression update workflow:
#   0. Format/lint-fix Bazel files with buildifier (mirrors the CI check)
#   0b. (optional) Run ALL top-level flow tests and update their metrics
#       goldens (save_flow_metrics / save_flow_metrics_limits) — only when
#       "flow" is passed as argument.  Flow tests (aes_sky130hd, gcd_*, ...)
#       are NOT registered in ctest; they only run via test/regression.
#   1. Run all tests  →  ctest_output.txt
#   2. Update DEF golden files (save_defok) for failed tests
#   3. Re-run failed tests  →  ctest_after_defok.txt
#   4. Update log golden files (save_ok) for still-failed tests
#   5. Re-run failed tests  →  check_update.txt  (verification)
#
# Can be called from anywhere — the repo root is auto-detected by walking up
# from the current working directory.
#
# Usage:
#   /path/to/4regressionUpdateAll.sh [flow|only_flow]
#     flow      — also run the full flow-test group (gcd_*, aes_*, ibex_*,
#                 ...) and update their metrics goldens.  Skipped when absent.
#                 CAUTION: each flow test is a full RTL-to-GDS run.
#     only_flow — run ONLY the flow tests (and the cheap buildifier fix);
#                 skip the ctest steps 1-5 entirely.
#
# Overrides (env vars):
#   OPENROAD_ROOT=/path/to/repo   — explicit repo root
#   BUILD_DIR=/path/to/build      — explicit build directory (default: <repo>/build)
#   JOBS=16                       — ctest parallelism (default: nproc)
#   FLOW_JOBS=5                   — parallel flow-test processes (default: 5);
#                                   per-test logs: <repo>/flow_<test>.txt

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Walk up a directory tree looking for the OpenROAD repo root marker.
_find_repo_root() {
    local _dir="$1"
    while [ "$_dir" != "/" ]; do
        if [ -f "$_dir/src/openroad/OpenROAD.cc" ] || [ -d "$_dir/src/dpl" ]; then
            echo "$_dir"
            return 0
        fi
        _dir="$(dirname "$_dir")"
    done
    return 1
}

# Resolve the OpenROAD repo root:
#   1. Explicit env var ($OPENROAD_ROOT)
#   2. Walk up from $PWD  (handles: cd into repo, then call script from PATH)
#   3. Walk up from $SCRIPT_DIR  (handles: script lives inside the repo)
#   4. Error out with a helpful message
if [ -n "$OPENROAD_ROOT" ]; then
    REPO_ROOT="$OPENROAD_ROOT"
elif REPO_ROOT="$(_find_repo_root "$PWD")"; then
    : # found via $PWD
elif REPO_ROOT="$(_find_repo_root "$SCRIPT_DIR")"; then
    : # found via script location
else
    echo "Error: could not locate the OpenROAD repo root." >&2
    echo "  Run from inside the repo, or set OPENROAD_ROOT=/path/to/repo." >&2
    exit 1
fi

BUILD_DIR="${BUILD_DIR:-$REPO_ROOT/build}"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 32)}"

CTEST_OUTPUT="$REPO_ROOT/ctest_output.txt"
CTEST_EMBEDDED_FIX="$REPO_ROOT/ctest_embedded_fix.txt"
CTEST_AFTER_DEFOK="$REPO_ROOT/ctest_after_defok.txt"
CHECK_OUTPUT="$REPO_ROOT/check_update.txt"

RUN_FLOW=0
RUN_CTEST=1
case "${1:-}" in
    "") ;;
    flow) RUN_FLOW=1 ;;
    only_flow)
        RUN_FLOW=1
        RUN_CTEST=0
        ;;
    *)
        echo "Error: unknown argument '$1' (accepted: \"flow\", \"only_flow\")." >&2
        exit 1
        ;;
esac

echo "Repo root : $REPO_ROOT"
echo "Build dir : $BUILD_DIR"
echo "Jobs      : $JOBS"
echo "Flow tests: $([ "$RUN_FLOW" -eq 1 ] && echo yes || echo no)"
echo "Ctest     : $([ "$RUN_CTEST" -eq 1 ] && echo yes || echo no)"
echo ""

# ---------------------------------------------------------------------------
# Parse a ctest output file and populate the module_tests associative array.
# Clears the array before parsing.
# Usage: _parse_failures <ctest_output_file>
# ---------------------------------------------------------------------------
_parse_failures() {
    local log_file="$1"
    module_tests=()

    while read -r token; do
        local noext="${token%.*}"      # dpl.simple10
        local module="${noext%%.*}"    # dpl
        local testname="${noext#*.}"   # simple10
        if [ -n "${module_tests[$module]+x}" ]; then
            # Avoid duplicates (tcl + py variants share the same testname)
            if [[ " ${module_tests[$module]} " != *" $testname "* ]]; then
                module_tests[$module]+=" $testname"
            fi
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
    ' "$log_file")
}

# ---------------------------------------------------------------------------
# Run save_defok for all modules in module_tests.
# Falls back to copying results/*.def files when no save_defok script exists.
# ---------------------------------------------------------------------------
_run_save_defok() {
    for module in "${!module_tests[@]}"; do
        local test_dir
        if [ "$module" = "openroad" ]; then
            test_dir="$REPO_ROOT/test"
        else
            test_dir="$REPO_ROOT/src/$module/test"
        fi

        if [ ! -d "$test_dir" ]; then
            echo "Warning: test directory not found for module '$module': $test_dir"
            continue
        fi

        echo "--- $module ---"
        if [ -f "$test_dir/save_defok" ]; then
            # shellcheck disable=SC2086
            (cd "$test_dir" && ./save_defok ${module_tests[$module]})
        else
            for test_name in ${module_tests[$module]}; do
                if [ -f "$test_dir/results/${test_name}-tcl.def" ]; then
                    cp "$test_dir/results/${test_name}-tcl.def" "$test_dir/${test_name}.defok"
                    echo "$test_name (defok from tcl)"
                elif [ -f "$test_dir/results/${test_name}-py.def" ]; then
                    cp "$test_dir/results/${test_name}-py.def" "$test_dir/${test_name}.defok"
                    echo "$test_name (defok from py)"
                fi
                # No .def result is normal — not all tests produce DEF output
            done
        fi
    done
}

# ---------------------------------------------------------------------------
# Scan .ok files for embedded "Differences found at line" strings.
# These tests pass ctest (log matches golden) but their golden was itself
# captured while an internal diff_files call was already failing.
# Populates the embedded_diff_tests associative array: module -> "t1 t2 ..."
# ---------------------------------------------------------------------------
_find_embedded_diff_tests() {
    embedded_diff_tests=()

    while IFS= read -r ok_file; do
        local rel="${ok_file#$REPO_ROOT/}"   # e.g. src/cts/test/foo.ok
        local test_name module

        test_name="$(basename "$ok_file" .ok)"

        if [[ "$rel" == src/*/test/*.ok ]]; then
            module="$(echo "$rel" | cut -d/ -f2)"
        elif [[ "$rel" == test/*.ok ]]; then
            module="openroad"
        else
            continue
        fi

        if [ -n "${embedded_diff_tests[$module]+x}" ]; then
            if [[ " ${embedded_diff_tests[$module]} " != *" $test_name "* ]]; then
                embedded_diff_tests[$module]+=" $test_name"
            fi
        else
            embedded_diff_tests[$module]="$test_name"
        fi
    done < <(
        grep -rl "Differences found at line" \
            "$REPO_ROOT/src" "$REPO_ROOT/test" \
            --include="*.ok" 2>/dev/null
    )
}

# ---------------------------------------------------------------------------
# For every test in embedded_diff_tests:
#   1. Update all output goldens from the latest results/ files.
#      Handles any extension: .v→.vok, .spef→.spefok, .guide→.guideok, etc.
#      Also handles non-standard stems (e.g. repair_setup4_hier_out.v).
#   2. Re-run those specific tests so ctest regenerates a clean log.
#   3. Update the .ok golden from the fresh log.
# ---------------------------------------------------------------------------
_fix_embedded_diffs() {
    local -a rerun_patterns=()

    # Pass 1: update output golden files and collect ctest patterns for re-run.
    for module in "${!embedded_diff_tests[@]}"; do
        local test_dir
        if [ "$module" = "openroad" ]; then
            test_dir="$REPO_ROOT/test"
        else
            test_dir="$REPO_ROOT/src/$module/test"
        fi

        for test_name in ${embedded_diff_tests[$module]}; do
            local lang=""
            local updated=0

            # Glob all result files whose stem starts with the test name.
            # Covers both exact matches (foo-tcl.v) and suffixed stems (foo_out-tcl.v).
            for result_file in "$test_dir/results/${test_name}"*-tcl.* \
                               "$test_dir/results/${test_name}"*-py.*; do
                [ -f "$result_file" ] || continue

                local basename ext stem golden
                basename="$(basename "$result_file")"     # e.g. repair_setup4_hier_out-tcl.v
                ext="${basename##*.}"                      # v
                stem="${basename%-tcl.$ext}"               # repair_setup4_hier_out
                stem="${stem%-py.$ext}"                    # (handles py variant)
                golden="$test_dir/${stem}.${ext}ok"       # repair_setup4_hier_out.vok

                # Only update if a golden already exists for this output type.
                if [ -f "$golden" ]; then
                    cp "$result_file" "$golden"
                    echo "$module/$test_name: updated ${stem}.${ext}ok"
                    updated=1
                    # Determine lang for ctest pattern
                    if [[ "$basename" == *-tcl.* ]]; then
                        lang="tcl"
                    else
                        lang="py"
                    fi
                fi
            done

            if [ "$updated" -eq 1 ]; then
                rerun_patterns+=("${module}\\.${test_name}\\.${lang}")
            else
                echo "$module/$test_name: WARNING — no matching result/golden pair found"
            fi
        done
    done

    if [ ${#rerun_patterns[@]} -eq 0 ]; then
        echo "No golden files updated."
        return
    fi

    # Build an alternation regex for ctest -R.
    local regex
    regex="$(printf '%s|' "${rerun_patterns[@]}")"
    regex="${regex%|}"   # strip trailing |

    echo "Re-running ${#rerun_patterns[@]} test(s) to regenerate clean .ok files..."
    ctest --test-dir "$BUILD_DIR" -R "$regex" --output-on-failure -j "$JOBS" \
        > "$CTEST_EMBEDDED_FIX" 2>&1 || true

    # Pass 2: update .ok files from fresh logs.
    for module in "${!embedded_diff_tests[@]}"; do
        local test_dir
        if [ "$module" = "openroad" ]; then
            test_dir="$REPO_ROOT/test"
        else
            test_dir="$REPO_ROOT/src/$module/test"
        fi

        for test_name in ${embedded_diff_tests[$module]}; do
            if [ -f "$test_dir/results/${test_name}-tcl.log" ]; then
                cp "$test_dir/results/${test_name}-tcl.log" "$test_dir/${test_name}.ok"
                echo "$module/$test_name: updated .ok (tcl)"
            elif [ -f "$test_dir/results/${test_name}-py.log" ]; then
                cp "$test_dir/results/${test_name}-py.log" "$test_dir/${test_name}.ok"
                echo "$module/$test_name: updated .ok (py)"
            fi
        done
    done
}

# ---------------------------------------------------------------------------
# Run save_vok (and save_spefok, save_guideok, etc.) for all modules in
# module_tests.  Uses the same general stem-matching logic as _fix_embedded_diffs:
# any results/<stem>-tcl.<ext> is copied to <stem>.<ext>ok if a golden exists.
# ---------------------------------------------------------------------------
_run_save_vok() {
    for module in "${!module_tests[@]}"; do
        local test_dir
        if [ "$module" = "openroad" ]; then
            test_dir="$REPO_ROOT/test"
        else
            test_dir="$REPO_ROOT/src/$module/test"
        fi

        if [ ! -d "$test_dir" ]; then
            continue
        fi

        for test_name in ${module_tests[$module]}; do
            for result_file in "$test_dir/results/${test_name}"*-tcl.* \
                               "$test_dir/results/${test_name}"*-py.*; do
                [ -f "$result_file" ] || continue

                local basename ext stem golden
                basename="$(basename "$result_file")"
                ext="${basename##*.}"
                stem="${basename%-tcl.$ext}"
                stem="${stem%-py.$ext}"
                golden="$test_dir/${stem}.${ext}ok"

                if [ -f "$golden" ]; then
                    cp "$result_file" "$golden"
                    echo "$module/$test_name: updated ${stem}.${ext}ok"
                fi
            done
        done
    done
}

# ---------------------------------------------------------------------------
# Run save_ok for all modules in module_tests.
# Falls back to copying results/*.log files when no save_ok script exists.
# ---------------------------------------------------------------------------
_run_save_ok() {
    for module in "${!module_tests[@]}"; do
        local test_dir
        if [ "$module" = "openroad" ]; then
            test_dir="$REPO_ROOT/test"
        else
            test_dir="$REPO_ROOT/src/$module/test"
        fi

        if [ ! -d "$test_dir" ]; then
            echo "Warning: test directory not found for module '$module': $test_dir"
            continue
        fi

        echo "--- $module ---"
        # The top-level test/save_ok is a legacy Tcl script whose test registry
        # only covers flow tests.  Use it only for module sub-directories where
        # save_ok is a bash script (those always support arbitrary test names).
        if [ -f "$test_dir/save_ok" ] && [ "$module" != "openroad" ]; then
            # shellcheck disable=SC2086
            (cd "$test_dir" && ./save_ok ${module_tests[$module]})
        else
            for test_name in ${module_tests[$module]}; do
                if [ -f "$test_dir/results/${test_name}-tcl.log" ]; then
                    cp "$test_dir/results/${test_name}-tcl.log" "$test_dir/${test_name}.ok"
                    echo "$test_name (ok from tcl)"
                elif [ -f "$test_dir/results/${test_name}-py.log" ]; then
                    cp "$test_dir/results/${test_name}-py.log" "$test_dir/${test_name}.ok"
                    echo "$test_name (ok from py)"
                else
                    echo "\"${test_name}\" log file not found"
                fi
            done
        fi
    done
}

# ---------------------------------------------------------------------------
# Step 0: Fix Bazel file formatting/lint with buildifier.
# CI runs `buildifier -lint=warn` over all tracked Bazel files and fails on any
# warning (e.g. unsorted-dict-items after editing a test BUILD file).  The
# repo's .buildifier.json sets mode=fix/lint=fix/warnings=all, so running
# buildifier from the repo root auto-repairs everything CI would flag.
# ---------------------------------------------------------------------------
echo "=== Step 0/5: Fixing Bazel files with buildifier ==="
BUILDIFIER="${BUILDIFIER:-}"
if [ -z "$BUILDIFIER" ]; then
    if [ -x "$REPO_ROOT/buildifier" ]; then
        BUILDIFIER="$REPO_ROOT/buildifier"
    elif command -v buildifier > /dev/null 2>&1; then
        BUILDIFIER="buildifier"
    fi
fi
if [ -n "$BUILDIFIER" ]; then
    _bazel_state() {
        (cd "$REPO_ROOT" && \
            git ls-files -z ':(glob)**/*.bzl' ':(glob)**/*.bazel' \
                ':(glob)**/BUILD' ':(glob)**/WORKSPACE' \
            | xargs -0 -r md5sum)
    }
    before="$(_bazel_state)"
    (cd "$REPO_ROOT" && \
        git ls-files -z ':(glob)**/*.bzl' ':(glob)**/*.bazel' \
            ':(glob)**/BUILD' ':(glob)**/WORKSPACE' \
        | xargs -0 -r "$BUILDIFIER")
    changed="$(diff <(echo "$before") <(_bazel_state) \
        | awk '/^>/ {print $3}')"
    if [ -n "$changed" ]; then
        echo "buildifier fixed:"
        echo "$changed" | sed 's/^/  /'
    else
        echo "No Bazel file changes needed."
    fi
else
    echo "Warning: buildifier not found — skipping Bazel lint fix." >&2
fi
echo ""

# ---------------------------------------------------------------------------
# Step 0b (optional): Flow tests + metrics golden update.
# Flow tests are not part of ctest — they run through test/regression.  For
# failed tests, save_flow_metrics copies results/<test>-tcl.metrics over the
# golden <test>.metrics, and save_flow_metrics_limits recomputes
# <test>.metrics_limits from the same result metrics.  A re-run then verifies
# the update took.
# Note: only metrics mismatches are fixable this way — a flow test failing
# for another reason (crash, "fail" last line) will still fail the re-run.
#
# Parallelism: the Tcl runner executes tests sequentially, so we launch one
# ./regression <test> process per test (capped at $FLOW_JOBS).  Each test
# writes uniquely-named results/<test>-tcl.* files, so parallel runs don't
# collide — except results/failures, which every invocation deletes and
# appends (a race).  We therefore detect failures from each process's exit
# code (the runner exits with its failure count), not from that file.
# ---------------------------------------------------------------------------

# List the individual tests of the "flow" group using the repo's own Tcl
# registry (regression_tests.tcl).  Prints one test name per line.
_expand_flow_tests() {
    (cd "$FLOW_DIR" && tclsh <<'EOF'
set test_dir [file normalize .]
set openroad_dir [file dirname $test_dir]
source regression.tcl
source regression_tests.tcl
foreach t [expand_tests {flow}] { puts $t }
EOF
    )
}

# Run each given flow test as its own ./regression process, at most
# $FLOW_JOBS at a time.  Per-test logs go to $REPO_ROOT/flow_<test>.txt.
# Each process writes its exit code to a status file — more robust than
# tracking pids (wait -n consumes job statuses on some bash versions).
# Populates the flow_failed array.
_run_flow_tests_parallel() {
    local -a tests=("$@")
    local status_dir
    status_dir="$(mktemp -d)"
    flow_failed=()

    for t in "${tests[@]}"; do
        while [ "$(jobs -rp | wc -l)" -ge "$FLOW_JOBS" ]; do
            sleep 5
        done
        echo "  launching $t (log: flow_${t}.txt)"
        (
            cd "$FLOW_DIR" && ./regression "$t" \
                > "$REPO_ROOT/flow_${t}.txt" 2>&1
            echo $? > "$status_dir/$t"
        ) &
    done
    wait

    for t in "${tests[@]}"; do
        # Missing status file = process died before writing it — treat as fail.
        if [ "$(cat "$status_dir/$t" 2>/dev/null || echo 1)" != "0" ]; then
            flow_failed+=("$t")
        fi
    done
    rm -rf "$status_dir"
}

if [ "$RUN_FLOW" -eq 1 ]; then
    echo "=== Step 0b: Running flow tests and updating metrics goldens ==="
    FLOW_DIR="$REPO_ROOT/test"
    FLOW_JOBS="${FLOW_JOBS:-5}"

    mapfile -t flow_expanded < <(_expand_flow_tests)
    echo "Running ${#flow_expanded[@]} flow test(s), $FLOW_JOBS in parallel:"

    declare -a flow_failed
    _run_flow_tests_parallel "${flow_expanded[@]}"

    if [ ${#flow_failed[@]} -gt 0 ]; then
        echo "Failed flow tests: ${flow_failed[*]}"

        echo "--- save_flow_metrics ---"
        (cd "$FLOW_DIR" && ./save_flow_metrics "${flow_failed[@]}")
        echo "--- save_flow_metrics_limits ---"
        (cd "$FLOW_DIR" && ./save_flow_metrics_limits "${flow_failed[@]}")

        echo "Re-running ${#flow_failed[@]} flow test(s) to verify..."
        _run_flow_tests_parallel "${flow_failed[@]}"
        if [ ${#flow_failed[@]} -gt 0 ]; then
            echo "WARNING: flow tests still failing after metrics update:"
            printf '  %s\n' "${flow_failed[@]}"
            echo "  (see flow_<test>.txt — likely not a metrics-only failure)"
        else
            echo "All flow tests pass after metrics update."
        fi
    else
        echo "All flow tests passed — no metrics update needed."
    fi
    echo ""
fi

if [ "$RUN_CTEST" -eq 0 ]; then
    echo "only_flow: skipping ctest steps 1-5."
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 1: Run all tests
# ---------------------------------------------------------------------------
echo "=== Step 1/5: Running all tests ==="
ctest --test-dir "$BUILD_DIR" --output-on-failure -j "$JOBS" > "$CTEST_OUTPUT" 2>&1
echo ""

declare -A module_tests
_parse_failures "$CTEST_OUTPUT"

# Detect tests that pass ctest but have embedded diff failures in their .ok.
declare -A embedded_diff_tests
_find_embedded_diff_tests

if [ ${#embedded_diff_tests[@]} -gt 0 ]; then
    echo "=== Step 1b/5: Fixing embedded diff failures in .ok files ==="
    echo "Found in modules: ${!embedded_diff_tests[*]}"
    _fix_embedded_diffs
    echo ""
fi

if [ ${#module_tests[@]} -eq 0 ] && [ ${#embedded_diff_tests[@]} -eq 0 ]; then
    echo "All tests passed — nothing to update."
    exit 0
fi

if [ ${#module_tests[@]} -eq 0 ]; then
    echo "No ctest failures — only embedded diffs were fixed."
    exit 0
fi

echo "Failed modules: ${!module_tests[*]}"
echo ""

# ---------------------------------------------------------------------------
# Step 2: Update DEF and Verilog golden files for initially failed tests
# ---------------------------------------------------------------------------
echo "=== Step 2/5: Updating DEF golden files (save_defok) ==="
_run_save_defok
echo ""
echo "=== Step 2b/5: Updating Verilog golden files (save_vok) ==="
_run_save_vok
echo ""

# ---------------------------------------------------------------------------
# Step 3: Re-run failed tests after defok update
# ---------------------------------------------------------------------------
echo "=== Step 3/5: Re-running failed tests after save_defok ==="
ctest --test-dir "$BUILD_DIR" --rerun-failed --output-on-failure -j "$JOBS" > "$CTEST_AFTER_DEFOK" 2>&1
echo ""

_parse_failures "$CTEST_AFTER_DEFOK"

if [ ${#module_tests[@]} -eq 0 ]; then
    echo "All tests pass after save_defok — no log golden update needed."
    echo "Log: $CTEST_AFTER_DEFOK"
    exit 0
fi

echo "Still-failing modules: ${!module_tests[*]}"
echo ""

# ---------------------------------------------------------------------------
# Step 4: Update log golden files for still-failing tests
# ---------------------------------------------------------------------------
echo "=== Step 4/5: Updating log golden files (save_ok) ==="
_run_save_ok
echo ""

# ---------------------------------------------------------------------------
# Step 5: Re-run to verify everything is now correct
# ---------------------------------------------------------------------------
echo "=== Step 5/5: Verifying updates ==="
ctest --test-dir "$BUILD_DIR" --rerun-failed --output-on-failure -j "$JOBS" > "$CHECK_OUTPUT" 2>&1
echo ""

echo "--- Checking for embedded diff failures in .ok files ---"
embedded_diff_hits="$(grep -ril "Differences found at line" \
    "$REPO_ROOT/src" "$REPO_ROOT/test" --include="*.ok" 2>/dev/null)"
if [ -n "$embedded_diff_hits" ]; then
    echo "WARNING: the following .ok files still contain embedded diff failures:"
    echo "$embedded_diff_hits" | sed "s|$REPO_ROOT/||"
else
    echo "No embedded diff failures found in .ok files."
fi
echo ""

echo "Logs saved:"
echo "  Initial run        : $CTEST_OUTPUT"
echo "  Embedded diff fix  : $CTEST_EMBEDDED_FIX"
echo "  After save_defok   : $CTEST_AFTER_DEFOK"
echo "  After save_ok      : $CHECK_OUTPUT"
