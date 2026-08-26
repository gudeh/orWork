#!/usr/bin/env bash

## SPDX-License-Identifier: BSD-3-Clause
## Copyright (c) 2024-2026, The OpenROAD Authors

# Full regression update workflow:
#   0. Refuse to run on a branch that is behind its upstream master (see
#      "Why freshness matters" below), then format/lint-fix Bazel files with
#      buildifier (mirrors the CI check)
#   0b. (optional) Run ALL top-level flow tests and update their metrics
#       goldens (save_flow_metrics) and, where a metric genuinely fails, its
#       limits — only when "flow" is passed as argument.  Flow tests
#       (aes_sky130hd, gcd_*, ...) are NOT registered in ctest; they only run
#       via test/regression.
#   1. Run all tests  →  ctest_output.txt
#   2. Update DEF golden files (save_defok) for failed tests
#   3. Re-run failed tests  →  ctest_after_defok.txt
#   4. Update log golden files (save_ok) for still-failed tests
#   5. Re-run failed tests  →  check_update.txt  (verification)
#   6. Re-verify everything under Bazel — CI builds with Bazel, and its
#      results do NOT always match this CMake build (see below)
#
# Why freshness matters (step 0)
#   Goldens regenerated on a stale base merge cleanly but wrongly: if master
#   added a line to a golden this branch also rewrites, git keeps master's
#   value while the merged binary prints a different one.  That is a CI-only
#   failure no amount of local re-running will show, so this script stops
#   before spending hours regenerating against the wrong base.
#
# Why Bazel matters (steps 0b and 6)
#   The CMake build here and the Bazel build CI uses do not produce identical
#   flow QoR — aes_nangate45 reports 1 hold buffer under CMake and 74 under
#   Bazel.  Limits derived from a CMake run alone are therefore unreachable
#   in CI, so flow limits are only relaxed for metrics that actually fail,
#   and are widened to cover both builds when Bazel is available.
#
# Logs are written to a scratch directory that is deleted when the script
# finishes, so a normal run leaves the repo clean.  Pass -v to write them into
# the repo root instead and keep them.  A run that ends with something still
# broken keeps its scratch directory and prints the path.
#
# Can be called from anywhere — the repo root is auto-detected by walking up
# from the current working directory.
#
# Usage:
#   /path/to/4regressionUpdateAll.sh [-v] [-s] [--no-bazel] [flow|only_flow]
#     -v         — keep the log files (ctest_output.txt, check_update.txt,
#                  flow_<test>.txt, ...) in the repo root instead of discarding
#                  them.
#     -s         — stale-ok: proceed even when the branch is behind upstream
#                  master.  Only sensible when the goldens being updated are
#                  untouched by the missing commits.
#     --no-bazel — skip the Bazel cross-checks (step 6 and the Bazel half of
#                  the flow limit update).  Faster, but a green run then says
#                  nothing about CI.
#     flow       — also run the full flow-test group (gcd_*, aes_*, ibex_*,
#                  ...) and update their metrics goldens.  Skipped when absent.
#                  CAUTION: each flow test is a full RTL-to-GDS run.
#     only_flow  — run ONLY the flow tests (and the cheap buildifier fix);
#                  skip the ctest steps 1-5 entirely.
#
# Overrides (env vars):
#   OPENROAD_ROOT=/path/to/repo   — explicit repo root
#   BUILD_DIR=/path/to/build      — explicit build directory (default: <repo>/build)
#   JOBS=16                       — ctest parallelism (default: nproc)
#   FLOW_JOBS=5                   — parallel flow-test processes (default: 5);
#                                   per-test logs: <log dir>/flow_<test>.txt
#   UPSTREAM_REF=private/master   — branch the freshness check compares against
#                                   (default: first of private/master,
#                                   origin/master, upstream/master that exists)

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

RUN_FLOW=0
RUN_CTEST=1
VERBOSE=0
STALE_OK=0
USE_BAZEL=1
while [ $# -gt 0 ]; do
    case "$1" in
        -v | --verbose) VERBOSE=1 ;;
        -s | --stale-ok) STALE_OK=1 ;;
        --no-bazel) USE_BAZEL=0 ;;
        flow) RUN_FLOW=1 ;;
        only_flow)
            RUN_FLOW=1
            RUN_CTEST=0
            ;;
        *)
            echo "Error: unknown argument '$1'" \
                "(accepted: \"-v\", \"-s\", \"--no-bazel\", \"flow\"," \
                "\"only_flow\")." >&2
            exit 1
            ;;
    esac
    shift
done

# Where the ctest / flow-test logs go.  With -v they land in the repo root and
# stay there; otherwise they go to a scratch directory removed on exit, so a
# clean run doesn't litter `git status` with a dozen untracked .txt files.
if [ "$VERBOSE" -eq 1 ]; then
    LOG_DIR="$REPO_ROOT"
    KEEP_LOGS=1
else
    if ! LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/regressionUpdate.XXXXXX")"; then
        echo "Error: could not create a temporary log directory." >&2
        exit 1
    fi
    KEEP_LOGS=0
fi

_cleanup_logs() {
    if [ "$KEEP_LOGS" -eq 0 ] && [ -n "$LOG_DIR" ] && [ "$LOG_DIR" != "$REPO_ROOT" ]; then
        rm -rf "$LOG_DIR"
    fi
}
trap _cleanup_logs EXIT

# Keep the scratch logs around — called when the run ends with something still
# broken, since that is exactly when the logs are worth reading.
_retain_logs() {
    [ "$KEEP_LOGS" -eq 1 ] && return 0
    KEEP_LOGS=1
    echo "  (logs kept for inspection: $LOG_DIR)"
}

CTEST_OUTPUT="$LOG_DIR/ctest_output.txt"
CTEST_EMBEDDED_FIX="$LOG_DIR/ctest_embedded_fix.txt"
CTEST_AFTER_DEFOK="$LOG_DIR/ctest_after_defok.txt"
CHECK_OUTPUT="$LOG_DIR/check_update.txt"

# Bazel is used to cross-check the goldens against the build CI actually runs.
BAZEL=""
if [ "$USE_BAZEL" -eq 1 ]; then
    for _b in bazelisk bazel; do
        if command -v "$_b" > /dev/null 2>&1; then
            BAZEL="$_b"
            break
        fi
    done
    if [ -z "$BAZEL" ]; then
        echo "Warning: bazel not found — Bazel cross-checks disabled." >&2
        USE_BAZEL=0
    fi
fi

echo "Repo root : $REPO_ROOT"
echo "Build dir : $BUILD_DIR"
echo "Jobs      : $JOBS"
echo "Flow tests: $([ "$RUN_FLOW" -eq 1 ] && echo yes || echo no)"
echo "Ctest     : $([ "$RUN_CTEST" -eq 1 ] && echo yes || echo no)"
echo "Bazel     : $([ "$USE_BAZEL" -eq 1 ] && echo "$BAZEL" || echo no)"
echo "Logs      : $LOG_DIR$([ "$VERBOSE" -eq 1 ] || echo " (temporary; -v to keep)")"
echo ""

# ---------------------------------------------------------------------------
# Step 0: refuse to regenerate goldens on a base that is behind master.
#
# A golden regenerated here records the output of THIS source tree.  When
# master has since added a line to the same golden, git merges both edits
# without conflict and the result is a file that matches neither build: the
# merged binary prints master's new line with a value derived from this
# branch's behaviour.  Nothing local reproduces it, so catch it up front.
# ---------------------------------------------------------------------------
_check_branch_freshness() {
    local upstream="${UPSTREAM_REF:-}"
    if [ -z "$upstream" ]; then
        for ref in private/master origin/master upstream/master; do
            if git -C "$REPO_ROOT" rev-parse --verify --quiet \
                "refs/remotes/$ref" > /dev/null; then
                upstream="$ref"
                break
            fi
        done
    fi
    if [ -z "$upstream" ]; then
        echo "Warning: no upstream master ref found — skipping freshness check." >&2
        return 0
    fi

    local remote="${upstream%%/*}"
    echo "Fetching $remote to check freshness against $upstream ..."
    git -C "$REPO_ROOT" fetch "$remote" --quiet 2> /dev/null \
        || echo "Warning: could not fetch $remote; using the local ref." >&2

    local behind
    behind="$(git -C "$REPO_ROOT" rev-list --count "HEAD..$upstream" 2>/dev/null)"
    if [ -z "$behind" ] || [ "$behind" -eq 0 ]; then
        echo "Branch is up to date with $upstream."
        return 0
    fi

    echo ""
    echo "ERROR: this branch is $behind commit(s) behind $upstream." >&2
    echo "       Goldens regenerated now can merge cleanly but still fail CI," >&2
    echo "       because CI tests the merge, not this tree.  Commits missing:" >&2
    git -C "$REPO_ROOT" log --oneline "HEAD..$upstream" | sed 's/^/         /' >&2
    echo "" >&2
    echo "       Goldens those commits touch (regenerate after merging):" >&2
    git -C "$REPO_ROOT" diff --name-only "HEAD...$upstream" \
        -- '*.ok' '*.defok' '*.vok' '*.guideok' '*.metrics' '*.metrics_limits' \
        | sed 's/^/         /' >&2
    echo "" >&2
    echo "       Merge $upstream and rebuild, then re-run.  Pass -s to override." >&2
    exit 1
}

if [ "$STALE_OK" -eq 1 ]; then
    echo "Freshness check skipped (-s)."
    echo ""
else
    _check_branch_freshness
    echo ""
fi

# ---------------------------------------------------------------------------
# Step 6: re-check the updated goldens under Bazel.
#
# ctest passing proves the goldens match THIS build.  CI builds with Bazel,
# whose dependency versions and flags differ, so a golden can be green here
# and red there.  //... skips the flow tests (they are tagged manual and are
# handled by step 0b).
# ---------------------------------------------------------------------------
_bazel_verify() {
    [ "$USE_BAZEL" -eq 1 ] || return 0
    echo "=== Step 6: Verifying goldens under Bazel (the build CI uses) ==="
    local log="$LOG_DIR/bazel_verify.txt"
    local rc=0
    (cd "$REPO_ROOT" && "$BAZEL" test //... --keep_going --test_output=summary) \
        > "$log" 2>&1 || rc=$?

    local failed
    failed="$(grep -aE '^//.*(FAILED|TIMEOUT)' "$log" || true)"
    if [ -n "$failed" ]; then
        echo "WARNING: green under ctest, red under Bazel — CI will fail on:"
        echo "$failed" | sed 's/^/  /'
        echo "  (full log: $log)"
        _retain_logs
    elif [ "$rc" -ne 0 ]; then
        echo "WARNING: bazel exited $rc without naming a failed test."
        echo "  (full log: $log)"
        _retain_logs
    else
        echo "All Bazel tests pass — the goldens hold for CI too."
    fi
    echo ""
}

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
echo "=== Step 0/6: Fixing Bazel files with buildifier ==="
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
# $FLOW_JOBS at a time.  Per-test logs go to $LOG_DIR/flow_<test>.txt.
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
        echo "  launching $t (log: $LOG_DIR/flow_${t}.txt)"
        (
            cd "$FLOW_DIR" && ./regression "$t" \
                > "$LOG_DIR/flow_${t}.txt" 2>&1
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

# ---------------------------------------------------------------------------
# Write the limit merger used by _update_flow_limits.
# Kept as its own file so the policy is readable and testable on its own.
# ---------------------------------------------------------------------------
LIMITS_MERGER="$LOG_DIR/merge_flow_limits.py"
_write_limits_merger() {
    cat > "$LIMITS_MERGER" << 'PYEOF'
#!/usr/bin/env python3
"""Widen flow metric limits only where a run actually violates them.

save_flow_metrics_limits re-derives EVERY limit from the one run it is given
(limit = value * 1.2 and friends), so a lucky run ratchets the gate down to
whatever that build happened to produce -- which then fails on a build that
behaves slightly differently, e.g. CI's.

This keeps every committed limit untouched unless a run actually fails it,
and then takes the loosest derived limit among the runs that failed, so the
new limit covers every build that was checked.  Comparison directions come
from test/flow_metrics.tcl rather than a copy kept here, so a metric added
upstream is handled without touching this script.
"""
import argparse
import json
import re
import sys

DEFINE_METRIC = re.compile(
    r'^define_metric\s+"(?P<name>[^"]+)"'   # metric name / json key
    r'\s+"[^"]*"\s+"[^"]*"'                 # two header strings
    r'\s+\d+\s+"[^"]*"'                     # field width, format
    r'\s+"(?P<op>[<>=]+)"'                  # comparison operator
)
LIMIT_LINE = re.compile(r'^(?P<pre>\s*[,\s])"(?P<key>[^"]+)"\s*:\s*"(?P<val>[^"]+)"\s*$')
SATISFIES = {
    "<": lambda v, l: v < l,
    "<=": lambda v, l: v <= l,
    ">": lambda v, l: v > l,
    ">=": lambda v, l: v >= l,
}


def parse_ops(flow_metrics_tcl):
    ops = {}
    with open(flow_metrics_tcl) as stream:
        for line in stream:
            match = DEFINE_METRIC.match(line)
            if match:
                ops[match.group("name")] = match.group("op")
    if not ops:
        sys.exit(f"error: no define_metric lines found in {flow_metrics_tcl}")
    return ops


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ops", required=True, help="path to flow_metrics.tcl")
    parser.add_argument("--limits", required=True, help="limits file, rewritten in place")
    parser.add_argument(
        "--pair",
        action="append",
        default=[],
        metavar="METRICS:DERIVED_LIMITS",
        help="a run's result metrics and the limits derived from it",
    )
    parser.add_argument("--label", default="", help="test name, for messages")
    args = parser.parse_args()

    ops = parse_ops(args.ops)
    runs = []
    for pair in args.pair:
        metrics_path, _, derived_path = pair.partition(":")
        # <test>-cmake.metrics / <test>-bazel.metrics -> "cmake" / "bazel"
        name = metrics_path.rsplit("/", 1)[-1].rsplit(".", 1)[0].rsplit("-", 1)[-1]
        try:
            runs.append(
                (name, json.load(open(metrics_path)), json.load(open(derived_path)))
            )
        except (OSError, ValueError) as exc:
            print(f"  {args.label}: skipping {metrics_path} ({exc})")
    if not runs:
        return

    out, changes = [], []
    for line in open(args.limits).read().splitlines():
        match = LIMIT_LINE.match(line)
        if not match:
            out.append(line)
            continue
        key, old = match.group("key"), match.group("val")
        op = ops.get(key)
        # A metric with no known comparison direction cannot be judged; leave it.
        if op is None:
            out.append(line)
            continue
        # Only runs that fail this limit get a say in relaxing it.
        failing = [
            (name, derived[key])
            for name, metrics, derived in runs
            if key in metrics
            and key in derived
            and not SATISFIES[op](float(metrics[key]), float(old))
        ]
        if not failing:
            out.append(line)
            continue
        drivers = ",".join(name for name, _ in failing)
        candidates = [value for _, value in failing]
        values = [float(c) for c in candidates]
        loosest = max(values) if op in ("<", "<=") else min(values)
        new = candidates[values.index(loosest)]
        # Adopt only what is genuinely looser: "old satisfies new" means new
        # admits everything old did.  A derived limit that is tighter than the
        # committed one never gets through, whatever the run did.
        if SATISFIES[op](float(old), float(new)) and float(new) != float(old):
            changes.append((key, old, new, drivers))
            out.append(f'{match.group("pre")}"{key}" : "{new}"')
        else:
            out.append(line)

    if changes:
        with open(args.limits, "w") as stream:
            stream.write("\n".join(out) + "\n")
        for key, old, new, drivers in changes:
            note = ""
            # A relaxation no Bazel run asked for is build divergence, not a
            # QoR change CI will see -- worth a look before it is committed.
            if len(runs) > 1 and "bazel" not in drivers:
                note = "   <-- CMake only; CI does not see this"
            print(
                f"  {args.label}: {key} {float(old):.6g} -> {float(new):.6g}"
                f" [{drivers}]{note}"
            )
    else:
        print(f"  {args.label}: limits already cover this run")


main()
PYEOF
}

# ---------------------------------------------------------------------------
# Update <test>.metrics_limits for the given flow tests.
#
# The repo's save_flow_metrics_limits is still what derives a candidate limit,
# so the margin formulas stay in one place -- but it is run against a scratch
# copy and its output is merged by policy rather than adopted wholesale.  When
# Bazel is available the test is also run there, and the merged limit covers
# whichever builds actually failed, because CI gates on the Bazel numbers.
# ---------------------------------------------------------------------------
_update_flow_limits() {
    local -a tests=("$@")
    _write_limits_merger

    local scratch="$LOG_DIR/flow_limits"
    mkdir -p "$scratch"

    # Tests whose limits this call actually changed; the caller re-checks them.
    flow_limits_changed=()

    # One bazel invocation for all of them: bazel schedules the tests itself,
    # and these are hour-scale runs to serialize by hand.  Failures are the
    # point of the exercise, so the exit code is ignored.
    if [ "$USE_BAZEL" -eq 1 ]; then
        local -a targets=()
        for t in "${tests[@]}"; do
            targets+=("//test:${t}-tcl_test")
        done
        echo "  running ${#tests[@]} flow test(s) under bazel for the CI-side numbers"
        echo "  (log: $LOG_DIR/bazel_flow_tests.txt)"
        (cd "$REPO_ROOT" && "$BAZEL" test "${targets[@]}" --keep_going \
            --test_output=summary) > "$LOG_DIR/bazel_flow_tests.txt" 2>&1 || true
    fi

    for t in "${tests[@]}"; do
        local limits="$FLOW_DIR/$t.metrics_limits"
        local result="$FLOW_DIR/results/$t-tcl.metrics"
        if [ ! -f "$limits" ] || [ ! -f "$result" ]; then
            echo "  $t: no limits or result metrics — skipped"
            continue
        fi

        # Every metrics set to judge this limit against: the CMake run just
        # done, plus a Bazel run of the same test when available.
        local -a metric_sets=("$scratch/$t-cmake.metrics")
        cp "$result" "$scratch/$t-cmake.metrics"

        if [ "$USE_BAZEL" -eq 1 ]; then
            local bazel_metrics="$REPO_ROOT/bazel-testlogs/test/${t}-tcl_test/test.outputs/results/$t-tcl.metrics"
            if [ -f "$bazel_metrics" ]; then
                cp "$bazel_metrics" "$scratch/$t-bazel.metrics"
                metric_sets+=("$scratch/$t-bazel.metrics")
            else
                echo "  $t: bazel produced no metrics" \
                    "(see $LOG_DIR/bazel_flow_tests.txt)"
            fi
        fi

        # Derive a candidate limits file per metrics set.  save_flow_metrics_limits
        # reads results/<test>-tcl.metrics and overwrites <test>.metrics_limits,
        # so both are swapped out around the call and put back afterwards.
        cp "$limits" "$scratch/$t-committed.metrics_limits"
        local -a pairs=()
        for set_file in "${metric_sets[@]}"; do
            local tag derived
            tag="$(basename "$set_file" .metrics)"
            derived="$scratch/$tag.derived_limits"
            cp "$set_file" "$result"
            (cd "$FLOW_DIR" && ./save_flow_metrics_limits "$t") > /dev/null 2>&1
            cp "$limits" "$derived"
            cp "$scratch/$t-committed.metrics_limits" "$limits"
            pairs+=("--pair" "$set_file:$derived")
        done
        cp "$scratch/$t-cmake.metrics" "$result"

        python3 "$LIMITS_MERGER" \
            --ops "$FLOW_DIR/flow_metrics.tcl" \
            --limits "$limits" \
            --label "$t" \
            "${pairs[@]}" | tee "$scratch/$t.merge.txt"
        if grep -q -- "->" "$scratch/$t.merge.txt"; then
            flow_limits_changed+=("$t")
        fi
    done
}

if [ "$RUN_FLOW" -eq 1 ]; then
    echo "=== Step 0b: Running flow tests and updating metrics goldens ==="
    FLOW_DIR="$REPO_ROOT/test"
    FLOW_JOBS="${FLOW_JOBS:-4}"

    mapfile -t flow_expanded < <(_expand_flow_tests)
    echo "Running ${#flow_expanded[@]} flow test(s), $FLOW_JOBS in parallel:"

    declare -a flow_failed
    _run_flow_tests_parallel "${flow_expanded[@]}"

    if [ ${#flow_failed[@]} -gt 0 ]; then
        echo "Failed flow tests: ${flow_failed[*]}"
        echo "--- save_flow_metrics ---"
        (cd "$FLOW_DIR" && ./save_flow_metrics "${flow_failed[@]}")
    else
        echo "All flow tests passed under ctest."
    fi

    # Limits are judged for EVERY flow test, not just the ones that failed
    # here: a test can pass under CMake and fail under Bazel, which is the
    # build CI gates on.  Feeding all of them in is safe because the merge
    # only touches a limit some run actually violates.
    echo "--- metrics limits (relaxed only where a run fails) ---"
    declare -a flow_limits_changed
    _update_flow_limits "${flow_expanded[@]}"

    if [ ${#flow_failed[@]} -gt 0 ]; then
        echo "Re-running ${#flow_failed[@]} flow test(s) under ctest to verify..."
        _run_flow_tests_parallel "${flow_failed[@]}"
        if [ ${#flow_failed[@]} -gt 0 ]; then
            echo "WARNING: flow tests still failing after metrics update:"
            printf '  %s\n' "${flow_failed[@]}"
            echo "  (see $LOG_DIR/flow_<test>.txt — likely not a metrics-only failure)"
            _retain_logs
        else
            echo "All flow tests pass under ctest after the metrics update."
        fi
    fi

    # And the same check on the CI side, for the tests whose limits moved.
    if [ "$USE_BAZEL" -eq 1 ] && [ ${#flow_limits_changed[@]} -gt 0 ]; then
        echo "Re-checking ${#flow_limits_changed[@]} flow test(s) under bazel..."
        bazel_recheck_targets=()
        for t in "${flow_limits_changed[@]}"; do
            bazel_recheck_targets+=("//test:${t}-tcl_test")
        done
        bazel_recheck_log="$LOG_DIR/bazel_flow_recheck.txt"
        (cd "$REPO_ROOT" && "$BAZEL" test "${bazel_recheck_targets[@]}" \
            --keep_going --test_output=summary) \
            > "$bazel_recheck_log" 2>&1 || true
        bazel_recheck_failed="$(grep -aE '^//.*(FAILED|TIMEOUT)' \
            "$bazel_recheck_log" || true)"
        if [ -n "$bazel_recheck_failed" ]; then
            echo "WARNING: still failing under bazel after the limits update:"
            echo "$bazel_recheck_failed" | sed 's/^/  /'
            echo "  (a limit only moves for a metric that failed, so this is a"
            echo "   different metric or a non-metric failure: $bazel_recheck_log)"
            _retain_logs
        else
            echo "Updated flow limits hold under bazel."
        fi
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
echo "=== Step 1/6: Running all tests ==="
ctest --test-dir "$BUILD_DIR" --output-on-failure -j "$JOBS" > "$CTEST_OUTPUT" 2>&1
ctest_rc=$?
echo ""

declare -A module_tests
_parse_failures "$CTEST_OUTPUT"

# Detect tests that pass ctest but have embedded diff failures in their .ok.
declare -A embedded_diff_tests
_find_embedded_diff_tests

if [ ${#embedded_diff_tests[@]} -gt 0 ]; then
    echo "=== Step 1b/6: Fixing embedded diff failures in .ok files ==="
    echo "Found in modules: ${!embedded_diff_tests[*]}"
    _fix_embedded_diffs
    echo ""
fi

if [ ${#module_tests[@]} -eq 0 ] && [ ${#embedded_diff_tests[@]} -eq 0 ]; then
    # ctest failing without any parsed test failure means it never got to run
    # the suite (missing/stale build dir, bad -j, ...) — don't call that a pass.
    if [ "$ctest_rc" -ne 0 ]; then
        echo "Error: ctest exited $ctest_rc but reported no failed tests." >&2
        echo "       Is $BUILD_DIR a configured build directory?" >&2
        _retain_logs
        exit "$ctest_rc"
    fi
    echo "All tests passed — nothing to update."
    echo ""
    _bazel_verify
    exit 0
fi

if [ ${#module_tests[@]} -eq 0 ]; then
    echo "No ctest failures — only embedded diffs were fixed."
    echo ""
    _bazel_verify
    exit 0
fi

echo "Failed modules: ${!module_tests[*]}"
echo ""

# ---------------------------------------------------------------------------
# Step 2: Update DEF and Verilog golden files for initially failed tests
# ---------------------------------------------------------------------------
echo "=== Step 2/6: Updating DEF golden files (save_defok) ==="
_run_save_defok
echo ""
echo "=== Step 2b/6: Updating Verilog golden files (save_vok) ==="
_run_save_vok
echo ""

# ---------------------------------------------------------------------------
# Step 3: Re-run failed tests after defok update
# ---------------------------------------------------------------------------
echo "=== Step 3/6: Re-running failed tests after save_defok ==="
ctest --test-dir "$BUILD_DIR" --rerun-failed --output-on-failure -j "$JOBS" > "$CTEST_AFTER_DEFOK" 2>&1
echo ""

_parse_failures "$CTEST_AFTER_DEFOK"

if [ ${#module_tests[@]} -eq 0 ]; then
    echo "All tests pass after save_defok — no log golden update needed."
    [ "$VERBOSE" -eq 1 ] && echo "Log: $CTEST_AFTER_DEFOK"
    echo ""
    _bazel_verify
    exit 0
fi

echo "Still-failing modules: ${!module_tests[*]}"
echo ""

# ---------------------------------------------------------------------------
# Step 4: Update log golden files for still-failing tests
# ---------------------------------------------------------------------------
echo "=== Step 4/6: Updating log golden files (save_ok) ==="
_run_save_ok
echo ""

# ---------------------------------------------------------------------------
# Step 5: Re-run to verify everything is now correct
# ---------------------------------------------------------------------------
echo "=== Step 5/6: Verifying updates ==="
ctest --test-dir "$BUILD_DIR" --rerun-failed --output-on-failure -j "$JOBS" > "$CHECK_OUTPUT" 2>&1
echo ""

_parse_failures "$CHECK_OUTPUT"
if [ ${#module_tests[@]} -gt 0 ]; then
    echo "WARNING: still failing after the golden update: ${!module_tests[*]}"
    echo "  (not a golden mismatch — crash, timeout or a real regression)"
    _retain_logs
    echo ""
fi

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

_bazel_verify

if [ "$VERBOSE" -eq 1 ]; then
    echo "Logs saved:"
    echo "  Initial run        : $CTEST_OUTPUT"
    echo "  Embedded diff fix  : $CTEST_EMBEDDED_FIX"
    echo "  After save_defok   : $CTEST_AFTER_DEFOK"
    echo "  After save_ok      : $CHECK_OUTPUT"
    [ "$USE_BAZEL" -eq 1 ] \
        && echo "  Bazel verification : $LOG_DIR/bazel_verify.txt"
elif [ "$KEEP_LOGS" -eq 1 ]; then
    echo "Logs kept in: $LOG_DIR"
else
    echo "Logs discarded — re-run with -v to keep them in the repo root."
fi
