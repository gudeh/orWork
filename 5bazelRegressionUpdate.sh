#!/usr/bin/env bash

## SPDX-License-Identifier: BSD-3-Clause
## Copyright (c) 2024-2026, The OpenROAD Authors

# Bazel-native regression golden update.
#
# Runs tests under Bazel and regenerates their goldens from that same run, so
# what lands in the tree is what CI will compare against.  Driving the update
# from ctest instead and checking Bazel afterwards has a cost: the golden is
# regenerated from the CMake binary, and where the two builds diverge (the
# aes_nangate45 hold-buffer count is 1 under CMake and 74 under Bazel) the
# CMake value is simply the wrong one to commit.
#
# Bazel where it works, CMake where it does not.  Everything registered as a
# Bazel regression test is run and updated through Bazel.  The flow tests are
# the one group Bazel cannot update (see the note below), so passing "flow"
# runs those through the repo's own ./regression runner and updates their
# metrics goldens with the repo's Tcl savers -- while still pulling Bazel
# metrics in to judge the limits, because CI's numbers differ.
#
# Workflow:
#   0. Refuse to run on a branch behind upstream master (same reasoning as
#      the ctest script: goldens regenerated on a stale base merge cleanly
#      but wrongly), then fix Bazel file formatting with buildifier.
#   1. bazel test the requested targets  ->  bazel_run1.txt
#   2. Copy goldens out of bazel-testlogs for every FAILED target.  All
#      golden types are handled generically: results/<stem>-<ext>.<out> is
#      written to <pkg>/<stem>.<out>ok, and the run log to <stem>.ok.
#   3. Re-run ONLY the targets whose goldens step 2 rewrote  ->  bazel_run2.txt
#   4. Report anything still failing (a real regression, crash or timeout --
#      not a golden mismatch).
#
# Why this can work at all (and why it needs no --update flag)
#   test/bazel_test.sh points RESULTS_DIR at $TEST_UNDECLARED_OUTPUTS_DIR, so
#   Bazel already copies every result file out of the sandbox to
#     bazel-testlogs/<pkg>/<target>/test.outputs/results/
#   as a plain directory.  Those are byte-for-byte the files the ctest script
#   copies from build/, so no rule change or "blessing" mode is required.
#
# Why the goldens land in the right place
#   A Bazel target label already encodes its source package
#   (//src/gpl/test:simple01-tcl_test -> src/gpl/test/simple01.ok), so the
#   destination is derived rather than guessed.  The ctest script has to map
#   a bare test name back to src/<module>/test and special-case the
#   top-level "openroad" module; here that ambiguity does not exist.
#
# Why the flow tests need the CMake path (step 0b, "flow")
#   1. They are tagged "manual", so they are excluded from //... and CI does
#      not run them under Bazel either.
#   2. Their savers cannot see Bazel output.  save_flow_metrics and
#      save_flow_metrics_limits are Tcl, and flow_metrics.tcl resolves input
#      as $test_dir/results/<test>-<lang>.metrics -- a hardcoded local path
#      with no bazel_save.sh-style fallback, unlike the shell savers.  So the
#      tests are run by ./regression, which writes exactly that path.
#   3. Relaxing a metrics limit is a QoR judgement, not a golden refresh.
#      save_metric_limits re-derives EVERY limit from the single run it is
#      given, so a lucky run ratchets the gate down to whatever that build
#      happened to produce.  It is therefore run against a scratch copy and
#      its output merged by policy: a committed limit moves only when a run
#      actually violates it, and then to the loosest value among the runs
#      that failed, so the new limit covers every build checked.
#   Bazel still contributes here: the same tests are run under Bazel to get
#   CI's numbers into that merge, since the two builds disagree.
#
# Logs go to a scratch directory removed on exit; -v keeps them in the repo
# root.  A run ending with something still broken keeps its logs regardless.
#
# Can be called from anywhere -- the repo root is auto-detected.
#
# Usage:
#   /path/to/5bazelRegressionUpdate.sh [-v] [-s] [-n] [flow|only_flow]
#                                      [target|module ...]
#     -v          -- keep the log files instead of discarding them.
#     -s          -- stale-ok: proceed even when behind upstream master.
#     -n          -- dry run: report what would be rewritten, touch nothing.
#     flow        -- ALSO run the flow tests and update their metrics goldens
#                    and limits, via ./regression + the repo's Tcl savers.
#                    CAUTION: each flow test is a full RTL-to-GDS run.
#     only_flow   -- run ONLY the flow tests; skip the Bazel steps entirely.
#     target      -- an explicit Bazel label (//src/gpl/test:simple01-tcl_test)
#     module      -- a module name (gpl) or package (//src/gpl/test/...),
#                    expanded to that package's regression tests.
#   With no target, every Bazel regression test is run.  Flow tests are never
#   part of that set (they are tagged "manual"); ask for them with "flow".
#
# Overrides (env vars):
#   OPENROAD_ROOT=/path/to/repo    -- explicit repo root
#   BAZEL=bazelisk                 -- bazel binary to use
#   BAZEL_TEST_FLAGS="..."         -- extra flags for the bazel test calls
#   FLOW_JOBS=5                    -- parallel flow-test processes (default 4)
#   UPSTREAM_REF=private/master    -- branch the freshness check compares to

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

VERBOSE=0
STALE_OK=0
DRY_RUN=0
RUN_FLOW=0
RUN_BAZEL_TESTS=1
declare -a REQUESTED=()
while [ $# -gt 0 ]; do
    case "$1" in
        -v | --verbose) VERBOSE=1 ;;
        -s | --stale-ok) STALE_OK=1 ;;
        -n | --dry-run) DRY_RUN=1 ;;
        flow) RUN_FLOW=1 ;;
        only_flow)
            RUN_FLOW=1
            RUN_BAZEL_TESTS=0
            ;;
        -h | --help)
            sed -n '6,70p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        -*)
            echo "Error: unknown option '$1'" \
                "(accepted: -v, -s, -n, -h)." >&2
            exit 1
            ;;
        *) REQUESTED+=("$1") ;;
    esac
    shift
done

BAZEL="${BAZEL:-}"
if [ -z "$BAZEL" ]; then
    for _b in bazelisk bazel; do
        if command -v "$_b" > /dev/null 2>&1; then
            BAZEL="$_b"
            break
        fi
    done
fi
if [ -z "$BAZEL" ]; then
    echo "Error: neither bazelisk nor bazel found in PATH." >&2
    echo "  This script runs and updates tests through Bazel only." >&2
    exit 1
fi

# shellcheck disable=SC2206  # deliberate word splitting of user-supplied flags
declare -a BAZEL_FLAGS=(${BAZEL_TEST_FLAGS:-})

if [ "$VERBOSE" -eq 1 ]; then
    LOG_DIR="$REPO_ROOT"
    KEEP_LOGS=1
else
    if ! LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/bazelRegressionUpdate.XXXXXX")"; then
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

_retain_logs() {
    [ "$KEEP_LOGS" -eq 1 ] && return 0
    KEEP_LOGS=1
    echo "  (logs kept for inspection: $LOG_DIR)"
}

RUN1_LOG="$LOG_DIR/bazel_run1.txt"
RUN2_LOG="$LOG_DIR/bazel_run2.txt"

# ---------------------------------------------------------------------------
# Step 0: refuse to regenerate goldens on a base that is behind master.
#
# Identical reasoning to the ctest script: a golden regenerated here records
# THIS tree's output.  If master has since changed the same golden, git merges
# both edits without conflict and the result matches neither build.
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
        echo "Warning: no upstream master ref found -- skipping freshness check." >&2
        return 0
    fi

    local remote="${upstream%%/*}"
    echo "Fetching $remote to check freshness against $upstream ..."
    git -C "$REPO_ROOT" fetch "$remote" --quiet 2> /dev/null \
        || echo "Warning: could not fetch $remote; using the local ref." >&2

    local behind
    behind="$(git -C "$REPO_ROOT" rev-list --count "HEAD..$upstream" 2> /dev/null)"
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
        -- '*.ok' '*ok' '*.metrics' '*.metrics_limits' \
        | sed 's/^/         /' >&2
    echo "" >&2
    echo "       Merge $upstream and rebuild, then re-run.  Pass -s to override." >&2
    exit 1
}

# ---------------------------------------------------------------------------
# Resolve the requested arguments into a list of Bazel test targets.
#
# kind(regression_rule_test, ...) is what makes this precise: it selects
# exactly the golden-diffing integration tests and leaves cc_test unit tests
# and doc_check targets alone, so a full-suite run never tries to "update"
# a test that has no golden.
# ---------------------------------------------------------------------------
_flow_targets() {
    # check_metrics=1 is the defining attribute of a flow test, read straight
    # from the build graph -- no separate list to keep in sync.  These are
    # also all tagged "manual", i.e. excluded from //..., so CI does not run
    # them under Bazel either; see the comment on _resolve_targets.
    "$BAZEL" query "attr(check_metrics, 1, kind(regression_rule_test, //...))" \
        2> /dev/null
}

# Is this label one of the metrics-checking flow tests?  The set is queried
# once and cached, since resolving several explicit labels would otherwise
# re-run the same bazel query for each.
FLOW_SET=""
_is_flow_target() {
    if [ -z "$FLOW_SET" ]; then
        FLOW_SET="$(_flow_targets)"
        # Never leave it empty, or every subsequent call re-queries.
        [ -z "$FLOW_SET" ] && FLOW_SET="(none)"
    fi
    printf '%s\n' "$FLOW_SET" | grep -qxF "$1"
}

# ---------------------------------------------------------------------------
# Add the sibling language variant of each given target.
#
# A test's tcl and py runs are two Bazel targets but share ONE golden:
# //src/gpl/test:ar01-tcl_test and :ar01-py_test both diff against
# src/gpl/test/ar01.ok (211 test stems in this tree have both).  So updating
# a golden because the tcl run failed also changes what the py run is
# compared against -- and re-running only the target that failed would leave
# its sibling broken by an edit this script made, without ever reporting it.
#
# The ctest script gets this for free: it matches "^module\.test\.(tcl|py)$"
# and so always re-runs both variants ("a golden update affects the tcl and
# py runs alike").  This is the Bazel equivalent.
#
# Only variants that actually exist as targets are added, so a tcl-only test
# stays a single target.  The result is still strictly scoped: siblings of
# updated tests, never the whole suite.
# ---------------------------------------------------------------------------
_add_language_siblings() {
    local -a want=()
    local label stem other
    for label in "$@"; do
        want+=("$label")
        case "$label" in
            *-tcl_test)
                stem="${label%-tcl_test}"
                other="${stem}-py_test"
                ;;
            *-py_test)
                stem="${label%-py_test}"
                other="${stem}-tcl_test"
                ;;
            *) continue ;;
        esac
        want+=("$other")
    done

    # Keep only labels that exist, in one query rather than one per label.
    # A missing target is normal (most tests are tcl-only), so the query must
    # tolerate it: --keep_going plus a filter through the existing set.
    local expr
    expr="$(printf '%s + ' "${want[@]}")"
    expr="${expr% + }"
    "$BAZEL" query "kind(regression_rule_test, $expr)" --keep_going 2> /dev/null \
        | sort -u
}

_resolve_targets() {
    local -a scopes=()
    if [ ${#REQUESTED[@]} -eq 0 ]; then
        scopes=("//...")
    else
        local arg
        for arg in "${REQUESTED[@]}"; do
            case "$arg" in
                //*:*)
                    # An explicit label.  Filtering it through the same
                    # kind()/check_metrics query as a package scope matters:
                    # a named flow test would otherwise be accepted here and
                    # run for an hour before step 2 discovered it has no
                    # copyable golden, only metrics limits.
                    if _is_flow_target "$arg"; then
                        # Not updatable through Bazel (see the header note), so
                        # it is handled by the flow step instead of here.
                        echo "Note: $arg is a flow test; run it with the \"flow\"" >&2
                        echo "  argument, which uses ./regression and the Tcl savers." >&2
                        continue
                    fi
                    echo "$arg"
                    continue
                    ;;
                //*) scopes+=("$arg") ;;
                *)
                    # A bare module name.  Prefer src/<mod>/test, fall back to
                    # any package matching the name.
                    if [ -d "$REPO_ROOT/src/$arg/test" ]; then
                        scopes+=("//src/$arg/test/...")
                    elif [ -d "$REPO_ROOT/$arg" ]; then
                        scopes+=("//$arg/...")
                    else
                        echo "Error: cannot resolve '$arg' to a package or label." >&2
                        return 1
                    fi
                    ;;
            esac
        done
    fi

    [ ${#scopes[@]} -eq 0 ] && return 0

    local scope_expr
    scope_expr="$(printf '%s + ' "${scopes[@]}")"
    scope_expr="${scope_expr% + }"

    # Flow tests are excluded: not updatable under Bazel, and their goldens
    # are metrics limits rather than files to copy (see the header note).
    "$BAZEL" query \
        "kind(regression_rule_test, $scope_expr) except attr(check_metrics, 1, kind(regression_rule_test, //...))" \
        2> /dev/null
}

# ---------------------------------------------------------------------------
# Map a Bazel test label to the source directory holding its goldens.
#   //src/gpl/test:simple01-tcl_test  ->  src/gpl/test
#   //test:some_test-tcl_test         ->  test
# ---------------------------------------------------------------------------
_label_to_pkg_dir() {
    local label="$1"
    local pkg="${label#//}"
    pkg="${pkg%%:*}"
    printf '%s' "$pkg"
}

# ---------------------------------------------------------------------------
# Map a Bazel test label to the bazel-testlogs results directory.
# ---------------------------------------------------------------------------
_label_to_results_dir() {
    local label="$1"
    local pkg target
    pkg="$(_label_to_pkg_dir "$label")"
    target="${label##*:}"
    printf '%s' "$REPO_ROOT/bazel-testlogs/$pkg/$target/test.outputs/results"
}

# Path to a target's bazel test.log (the runner's own transcript).
_label_to_test_log() {
    local label="$1"
    local pkg target
    pkg="$(_label_to_pkg_dir "$label")"
    target="${label##*:}"
    printf '%s' "$REPO_ROOT/bazel-testlogs/$pkg/$target/test.log"
}

# ---------------------------------------------------------------------------
# Why did this target fail?  Only one of the answers is a golden problem.
#
# regression_test.sh checks four things in order, and stops at the first that
# fails:
#   1. exit code      -> prints "Expected exit code: N", exits.  The log diff
#                        is never reached, so the goldens are not implicated
#                        at all.
#   2. log vs golden  -> prints "Log does not match golden file: ...".  THIS
#                        is the one a golden update can fix.
#   3. pass/OK line   -> prints "Test did not report pass/OK ...".
#   4. metrics limits -> flow tests only, not handled here.
# Rewriting a golden for anything but (2) is wrong: it commits whatever the
# run happened to print for a failure that had nothing to do with the golden.
# That is how a SWIG-generated line number (utl_py.py line 222 -> 226) got
# written into test_error_exception.ok for a test that was really failing its
# exit-code check.
#
# Echoes one of: golden | exit_code | passfail | metrics | unknown
# ---------------------------------------------------------------------------
_failure_kind() {
    local label="$1"
    local log
    log="$(_label_to_test_log "$label")"

    if [ ! -f "$log" ]; then
        printf 'unknown'
        return
    fi

    # Order matters: the runner stops at the first failing check, so the
    # marker that is present identifies the check that failed.
    if grep -qa "^Expected exit code:" "$log"; then
        printf 'exit_code'
    elif grep -qa "Log does not match golden file:" "$log"; then
        printf 'golden'
    elif grep -qa "did not report pass/OK" "$log"; then
        printf 'passfail'
    elif grep -qa "^Metrics:" "$log"; then
        printf 'metrics'
    else
        printf 'unknown'
    fi
}

# ---------------------------------------------------------------------------
# Parse failed/timed-out targets out of a bazel test log.
# Bazel prints one "//label   FAILED"/"TIMEOUT" summary line per target.
# ---------------------------------------------------------------------------
_parse_failed_targets() {
    local log_file="$1"
    grep -aE '^//[^ ]+ +(FAILED|TIMEOUT)' "$log_file" \
        | awk '{print $1}' \
        | sort -u
}

# ---------------------------------------------------------------------------
# Which of the repo's save_* scripts handles a given result extension.
#
# The mapping is the repo's own: save_ok/save_defok/save_guideok each call
# test/shared/bazel_save.sh with a (dest_ext, src_ext) pair, e.g.
#   save_ok      -> bazel_save.sh ok      log
#   save_defok   -> bazel_save.sh defok   def
#   save_guideok -> bazel_save.sh guideok guide
# ---------------------------------------------------------------------------
_saver_for_ext() {
    case "$1" in
        log) printf 'save_ok' ;;
        def) printf 'save_defok' ;;
        guide) printf 'save_guideok' ;;
        *) printf '' ;;
    esac
}

# Copy a bazel-testlogs artifact over a golden.  Mirrors bazel_save.sh: the
# destination is removed first because both it and the source can be
# read-only, and `cp` onto a read-only file fails with EACCES.
_copy_golden() {
    local src="$1" dst="$2"
    rm -f "$dst"
    cp "$src" "$dst"
    chmod u+w "$dst"
}

# Goldens are data files, never executables.  Strip the executable bit that
# bazel-testlogs' r-xr-xr-x mode otherwise drags into the commit, but respect
# the user's umask for the rest rather than forcing 644.
_normalize_golden_mode() {
    [ -f "$1" ] && chmod a-x "$1"
}

# ---------------------------------------------------------------------------
# Update every golden of one test target, delegating to the repo's own
# save_* scripts wherever one exists for that output type.
#
# Why delegate rather than copy directly
#   test/shared/bazel_save.sh is the repo's Bazel-mode golden extractor, and
#   it handles two things a plain `cp` from bazel-testlogs does not:
#     * Zipped outputs.  Older bazel writes test.outputs/outputs.zip instead
#       of an unzipped results/ directory; bazel_save.sh reads either.  This
#       machine's bazel writes unzipped, so a direct copy happens to work
#       here and would silently find nothing elsewhere.
#     * Read-only sources.  Files under bazel-testlogs are mode r-xr-xr-x,
#       and `cp` preserves mode when it creates the destination.  A golden
#       created that way is itself read-only, so the NEXT write to it fails
#       with EACCES -- which the convergence loop below does on purpose.
#       bazel_save.sh does rm -f, then cp, then chmod u+w.
#   Keeping the extraction in the repo's script also means a change to the
#   golden layout is picked up here for free instead of silently diverging.
#
# For output types with no save_* script (.vok, .spefok, .rptok, ... -- 18 of
# the 21 golden extensions in the tree), the same rm/cp/chmod sequence is
# applied inline, since there is no repo script to call.
#
# Prints one line per file updated; sets updated_any=1 when anything changed.
# ---------------------------------------------------------------------------
_update_goldens_for_target() {
    local label="$1"
    local results_dir pkg_dir pkg
    results_dir="$(_label_to_results_dir "$label")"
    pkg="$(_label_to_pkg_dir "$label")"
    pkg_dir="$REPO_ROOT/$pkg"

    updated_any=0

    # Only a log-diff failure is fixable by rewriting a golden.  Anything
    # else means the run never got as far as comparing against one, so
    # copying its output over the golden would commit noise for a failure
    # the golden had nothing to do with.
    local kind
    kind="$(_failure_kind "$label")"
    case "$kind" in
        exit_code)
            echo "  $label: exit-code failure, not a golden mismatch -- skipped"
            echo "    (the run never reached the log diff; fix the test or its"
            echo "     expected_exit_code)"
            return
            ;;
        passfail)
            echo "  $label: no pass/OK on the last line, not a golden mismatch" \
                "-- skipped"
            return
            ;;
        metrics)
            echo "  $label: metrics-limit failure -- skipped (flow tests are" \
                "handled by the \"flow\" argument)"
            return
            ;;
    esac
    # 'golden' and 'unknown' fall through: a golden mismatch is what this
    # function is for, and an unclassifiable failure is still worth trying,
    # since the per-file cmp below only rewrites goldens that actually differ.

    if [ ! -d "$results_dir" ]; then
        echo "  $label: no results directory -- test failed before producing output"
        echo "    (expected $results_dir)"
        return
    fi

    local result_file
    for result_file in "$results_dir"/*; do
        [ -f "$result_file" ] || continue

        local base ext stem golden
        base="$(basename "$result_file")"
        ext="${base##*.}"
        stem="${base%.$ext}"

        # Strip the -tcl / -py language suffix the runner appends.
        case "$stem" in
            *-tcl) stem="${stem%-tcl}" ;;
            *-py) stem="${stem%-py}" ;;
        esac

        # .diff is the runner's own diff artifact, never a golden.
        [ "$ext" = "diff" ] && continue

        if [ "$ext" = "log" ]; then
            golden="$pkg_dir/${stem}.ok"
        else
            golden="$pkg_dir/${stem}.${ext}ok"
        fi

        # Only refresh goldens that are already tracked.  A brand-new golden
        # is a new test, which is a deliberate act, not a regeneration.
        [ -f "$golden" ] || continue

        if cmp -s "$result_file" "$golden"; then
            continue
        fi

        if [ "$DRY_RUN" -eq 1 ]; then
            echo "  $label: would update ${golden#$REPO_ROOT/}"
            updated_any=1
            continue
        fi

        # Prefer the repo's own saver for this output type.
        local saver saver_path
        saver="$(_saver_for_ext "$ext")"
        saver_path=""
        if [ -n "$saver" ] && [ -x "$pkg_dir/$saver" ]; then
            saver_path="$pkg_dir/$saver"
        fi

        if [ -n "$saver_path" ]; then
            # The saver checks local results/ first and falls back to
            # bazel_save.sh, which re-runs the target and extracts from
            # bazel-testlogs.  Run it from the test directory, as designed.
            if (cd "$pkg_dir" && "./$saver" "$stem") > /dev/null 2>&1; then
                echo "  $label: updated ${golden#$REPO_ROOT/} (via $saver)"
            else
                echo "  $label: $saver failed for $stem -- falling back to copy"
                _copy_golden "$result_file" "$golden"
                echo "  $label: updated ${golden#$REPO_ROOT/}"
            fi
        else
            # No repo script for this extension; do the copy here.
            _copy_golden "$result_file" "$golden"
            echo "  $label: updated ${golden#$REPO_ROOT/}"
        fi
        # Goldens are data.  Normalize the mode whichever path wrote the file:
        # bazel-testlogs artifacts are r-xr-xr-x, and both bazel_save.sh's
        # `chmod u+w` and a plain `cp` carry that executable bit into the
        # working tree, which git then records as a 100644 -> 100755 mode
        # change in an otherwise content-only commit.
        _normalize_golden_mode "$golden"
        updated_any=1
    done

    if [ "$updated_any" -eq 0 ]; then
        echo "  $label: no golden differs -- not a golden mismatch"
    fi
}

echo "Repo root : $REPO_ROOT"
echo "Bazel     : $BAZEL"
echo "Mode      : $([ "$DRY_RUN" -eq 1 ] && echo "dry run (no writes)" || echo "update goldens")"
echo "Logs      : $LOG_DIR$([ "$VERBOSE" -eq 1 ] || echo " (temporary; -v to keep)")"
echo ""

if [ "$STALE_OK" -eq 1 ]; then
    echo "Freshness check skipped (-s)."
    echo ""
else
    _check_branch_freshness
    echo ""
fi

# ---------------------------------------------------------------------------
# Flow-test helpers (the CMake/Tcl path).
#
# List the individual tests of the "flow" group using the repo's own Tcl
# registry, so a test added upstream is picked up without editing this script.
# ---------------------------------------------------------------------------
_expand_flow_tests() {
    (cd "$FLOW_DIR" && tclsh << 'EOF'
set test_dir [file normalize .]
set openroad_dir [file dirname $test_dir]
source regression.tcl
source regression_tests.tcl
foreach t [expand_tests {flow}] { puts $t }
EOF
    )
}

# Run each flow test as its own ./regression process, at most $FLOW_JOBS at a
# time.  The Tcl runner is sequential, so parallelism has to come from running
# several of it.  Each test writes uniquely-named results/<test>-tcl.* files so
# parallel runs do not collide -- except results/failures, which every
# invocation deletes and appends (a race), so failures are detected from each
# process's exit code instead.  Populates flow_failed.
_run_flow_tests_parallel() {
    local -a tests=("$@")
    local status_dir
    status_dir="$(mktemp -d)"
    flow_failed=()

    local t
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
        # Missing status file = process died before writing it; treat as fail.
        if [ "$(cat "$status_dir/$t" 2> /dev/null || echo 1)" != "0" ]; then
            flow_failed+=("$t")
        fi
    done
    rm -rf "$status_dir"
}

# ---------------------------------------------------------------------------
# Write the limit merger used by _update_flow_limits.
#
# save_flow_metrics_limits re-derives EVERY limit from the one run it is given
# (limit = value * 1.2 and friends), so a lucky run ratchets the gate down to
# whatever that build happened to produce -- which then fails on a build that
# behaves differently, e.g. CI's.  This keeps every committed limit untouched
# unless a run actually fails it, and then takes the loosest derived limit
# among the runs that failed, so the new limit covers every build checked.
# Comparison directions are read from flow_metrics.tcl rather than duplicated
# here, so a metric added upstream is handled without touching this script.
# ---------------------------------------------------------------------------
LIMITS_MERGER="$LOG_DIR/merge_flow_limits.py"
_write_limits_merger() {
    cat > "$LIMITS_MERGER" << 'PYEOF'
#!/usr/bin/env python3
"""Widen flow metric limits only where a run CI would see actually violates them.

Two rules, both there to stop a gate being weakened for no reason:
  * A committed limit is left alone unless some run actually fails it.
    (save_flow_metrics_limits re-derives EVERY limit from the one run it is
    given, so adopting its output wholesale ratchets the gate down to
    whatever that build happened to produce.)
  * A limit only CMake failed is left alone when a Bazel run of the same
    test passed it.  CI gates on Bazel, so that is build divergence rather
    than a QoR change -- relaxing on it weakens a gate CI passes cleanly.
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

    out, changes, held = [], [], []
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

        # CI gates on Bazel.  When a Bazel run of this test is available and
        # it satisfied the committed limit, a CMake-only violation is build
        # divergence, not a QoR change CI will ever see -- relaxing on it
        # would permanently weaken a gate CI passes cleanly.  Observed for
        # real: ibex_sky130hd reports DRT::ANT::errors 1 under CMake and 0
        # under Bazel, and the server run PASSED against the committed 0.
        bazel_ran = any(name == "bazel" and key in metrics for name, metrics, _ in runs)
        bazel_failed = any(name == "bazel" for name, _ in failing)
        if bazel_ran and not bazel_failed:
            held.append((key, old, ",".join(name for name, _ in failing)))
            out.append(line)
            continue

        drivers = ",".join(name for name, _ in failing)
        candidates = [value for _, value in failing]
        values = [float(c) for c in candidates]
        loosest = max(values) if op in ("<", "<=") else min(values)
        new = candidates[values.index(loosest)]
        # Adopt only what is genuinely looser: "old satisfies new" means new
        # admits everything old did.  A derived limit tighter than the
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
            # Reaching here without a Bazel driver means no Bazel run was
            # available to judge against (a held one would have been skipped).
            if len(runs) > 1 and "bazel" not in drivers:
                note = "   <-- CMake only; no Bazel run to confirm"
            print(
                f"  {args.label}: {key} {float(old):.6g} -> {float(new):.6g}"
                f" [{drivers}]{note}"
            )
    elif not held:
        print(f"  {args.label}: limits already cover this run")

    for key, old, drivers in held:
        print(
            f"  {args.label}: {key} kept at {float(old):.6g}"
            f" -- {drivers} failed it but Bazel did not (CI gates on Bazel)"
        )


main()
PYEOF
}

# ---------------------------------------------------------------------------
# Update <test>.metrics_limits for the given flow tests.
#
# The repo's save_flow_metrics_limits is still what derives a candidate limit,
# so the margin formulas stay in one place -- but it is run against a scratch
# copy and its output merged by policy rather than adopted wholesale.  The
# tests are also run under Bazel, so the merged limit covers whichever builds
# actually failed; CI gates on the Bazel numbers.
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
    local -a bazel_targets=()
    local t
    for t in "${tests[@]}"; do
        bazel_targets+=("//test:${t}-tcl_test")
    done
    echo "  running ${#tests[@]} flow test(s) under Bazel for the CI-side numbers"
    echo "  (log: $LOG_DIR/bazel_flow_tests.txt)"
    (cd "$REPO_ROOT" && "$BAZEL" test "${bazel_targets[@]}" --keep_going \
        --test_output=summary "${BAZEL_FLAGS[@]}") \
        > "$LOG_DIR/bazel_flow_tests.txt" 2>&1 || true

    for t in "${tests[@]}"; do
        local limits="$FLOW_DIR/$t.metrics_limits"
        local result="$FLOW_DIR/results/$t-tcl.metrics"
        if [ ! -f "$limits" ] || [ ! -f "$result" ]; then
            echo "  $t: no limits or result metrics -- skipped"
            continue
        fi

        # Every metrics set to judge this limit against: the CMake run just
        # done, plus a Bazel run of the same test when available.
        local -a metric_sets=("$scratch/$t-cmake.metrics")
        cp "$result" "$scratch/$t-cmake.metrics"

        local bazel_metrics="$REPO_ROOT/bazel-testlogs/test/${t}-tcl_test/test.outputs/results/$t-tcl.metrics"
        if [ -f "$bazel_metrics" ]; then
            cp "$bazel_metrics" "$scratch/$t-bazel.metrics"
            metric_sets+=("$scratch/$t-bazel.metrics")
        else
            echo "  $t: Bazel produced no metrics" \
                "(see $LOG_DIR/bazel_flow_tests.txt)"
        fi

        # Derive a candidate limits file per metrics set.  save_flow_metrics_limits
        # reads results/<test>-tcl.metrics and overwrites <test>.metrics_limits,
        # so both are swapped out around the call and put back afterwards.
        cp "$limits" "$scratch/$t-committed.metrics_limits"
        local -a pairs=()
        local set_file
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

# ---------------------------------------------------------------------------
# Step 0b: buildifier, mirroring the CI lint check.
#
# CI runs buildifier -lint=warn over all tracked Bazel files and fails on any
# warning.  The repo's .buildifier.json sets mode=fix/lint=fix, so simply
# running it from the repo root repairs what CI would flag.
# ---------------------------------------------------------------------------
echo "=== Step 0/4: Fixing Bazel files with buildifier ==="
BUILDIFIER="${BUILDIFIER:-}"
if [ -z "$BUILDIFIER" ]; then
    if [ -x "$REPO_ROOT/buildifier" ]; then
        BUILDIFIER="$REPO_ROOT/buildifier"
    elif command -v buildifier > /dev/null 2>&1; then
        BUILDIFIER="buildifier"
    fi
fi
if [ -n "$BUILDIFIER" ] && [ "$DRY_RUN" -eq 0 ]; then
    _bazel_state() {
        (cd "$REPO_ROOT" \
            && git ls-files -z ':(glob)**/*.bzl' ':(glob)**/*.bazel' \
                ':(glob)**/BUILD' ':(glob)**/WORKSPACE' \
            | xargs -0 -r md5sum)
    }
    before="$(_bazel_state)"
    (cd "$REPO_ROOT" \
        && git ls-files -z ':(glob)**/*.bzl' ':(glob)**/*.bazel' \
            ':(glob)**/BUILD' ':(glob)**/WORKSPACE' \
        | xargs -0 -r "$BUILDIFIER")
    changed="$(diff <(echo "$before") <(_bazel_state) | awk '/^>/ {print $3}')"
    if [ -n "$changed" ]; then
        echo "buildifier fixed:"
        echo "$changed" | sed 's/^/  /'
    else
        echo "No Bazel file changes needed."
    fi
elif [ "$DRY_RUN" -eq 1 ]; then
    echo "Skipped (dry run)."
else
    echo "Warning: buildifier not found -- skipping Bazel lint fix." >&2
fi
echo ""

# ---------------------------------------------------------------------------
# Step 0b (optional): flow tests, via the CMake/Tcl path.
#
# This is the part Bazel cannot do (see the header).  The tests are run by the
# repo's ./regression runner, which writes results/<test>-tcl.metrics -- the
# exact path flow_metrics.tcl reads -- so save_flow_metrics and
# save_flow_metrics_limits work as designed.  Bazel is still used to run the
# same tests and contribute CI's metrics to the limit merge.
# ---------------------------------------------------------------------------
if [ "$RUN_FLOW" -eq 1 ]; then
    echo "=== Step 0b: Flow tests (CMake path) ==="
    FLOW_DIR="$REPO_ROOT/test"
    FLOW_JOBS="${FLOW_JOBS:-4}"

    if [ ! -x "$FLOW_DIR/regression" ]; then
        echo "Error: $FLOW_DIR/regression not found or not executable." >&2
        echo "       The flow tests need the repo's own runner." >&2
        exit 1
    fi

    mapfile -t flow_expanded < <(_expand_flow_tests)
    if [ ${#flow_expanded[@]} -eq 0 ]; then
        echo "Error: could not expand the flow test group." >&2
        exit 1
    fi

    if [ "$DRY_RUN" -eq 1 ]; then
        echo "Dry run: would run ${#flow_expanded[@]} flow test(s) and update"
        echo "  their metrics goldens and limits:"
        printf '  %s\n' "${flow_expanded[@]}"
        echo ""
    else
        echo "Running ${#flow_expanded[@]} flow test(s), $FLOW_JOBS in parallel:"
        declare -a flow_failed
        _run_flow_tests_parallel "${flow_expanded[@]}"

        if [ ${#flow_failed[@]} -gt 0 ]; then
            echo "Failed flow tests: ${flow_failed[*]}"
            echo "--- save_flow_metrics (the repo's Tcl saver) ---"
            (cd "$FLOW_DIR" && ./save_flow_metrics "${flow_failed[@]}")
        else
            echo "All flow tests passed."
        fi

        # Limits are judged for EVERY flow test, not just the ones that failed
        # here: a test can pass under CMake and fail under Bazel, which is the
        # build CI gates on.  Feeding all of them in is safe because the merge
        # only touches a limit some run actually violates.
        echo "--- metrics limits (relaxed only where a run fails) ---"
        declare -a flow_limits_changed
        _update_flow_limits "${flow_expanded[@]}"

        if [ ${#flow_failed[@]} -gt 0 ]; then
            echo "Re-running ${#flow_failed[@]} flow test(s) to verify..."
            _run_flow_tests_parallel "${flow_failed[@]}"
            if [ ${#flow_failed[@]} -gt 0 ]; then
                echo "WARNING: flow tests still failing after the metrics update:"
                printf '  %s\n' "${flow_failed[@]}"
                echo "  (see $LOG_DIR/flow_<test>.txt -- likely not a metrics-only"
                echo "   failure)"
                _retain_logs
            else
                echo "All flow tests pass after the metrics update."
            fi
        fi

        # And the same check on the CI side, for the tests whose limits moved.
        if [ ${#flow_limits_changed[@]} -gt 0 ]; then
            echo "Re-checking ${#flow_limits_changed[@]} flow test(s) under Bazel..."
            declare -a flow_recheck=()
            for t in "${flow_limits_changed[@]}"; do
                flow_recheck+=("//test:${t}-tcl_test")
            done
            flow_recheck_log="$LOG_DIR/bazel_flow_recheck.txt"
            (cd "$REPO_ROOT" && "$BAZEL" test "${flow_recheck[@]}" \
                --keep_going --test_output=summary "${BAZEL_FLAGS[@]}") \
                > "$flow_recheck_log" 2>&1 || true
            flow_recheck_failed="$(_parse_failed_targets "$flow_recheck_log")"
            if [ -n "$flow_recheck_failed" ]; then
                echo "WARNING: still failing under Bazel after the limits update:"
                echo "$flow_recheck_failed" | sed 's/^/  /'
                echo "  (a limit only moves for a metric that failed, so this is a"
                echo "   different metric or a non-metric failure:"
                echo "   $flow_recheck_log)"
                _retain_logs
            else
                echo "Updated flow limits hold under Bazel."
            fi
        fi
    fi
    echo ""
fi

if [ "$RUN_BAZEL_TESTS" -eq 0 ]; then
    echo "only_flow: skipping the Bazel test steps."
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 1: run the requested tests under Bazel.
# ---------------------------------------------------------------------------
echo "=== Step 1/4: Resolving targets ==="
mapfile -t TARGETS < <(_resolve_targets)
if [ ${#TARGETS[@]} -eq 0 ]; then
    echo "Error: no regression test targets matched." >&2
    if [ ${#REQUESTED[@]} -gt 0 ]; then
        echo "       Requested: ${REQUESTED[*]}" >&2
        echo "       Flow tests are not Bazel targets here; pass \"flow\" to run" >&2
        echo "       and update them through ./regression instead." >&2
    fi
    exit 1
fi
echo "${#TARGETS[@]} regression test target(s) to run."
if [ ${#REQUESTED[@]} -gt 0 ]; then
    printf '  %s\n' "${TARGETS[@]}" | head -20
    [ ${#TARGETS[@]} -gt 20 ] && echo "  ... and $(( ${#TARGETS[@]} - 20 )) more"
fi
echo ""

echo "=== Step 1b/4: Running tests under Bazel ==="
echo "  (log: $RUN1_LOG)"
# --keep_going so one failure does not hide the rest; the whole point is to
# collect every failing golden in one pass.
(cd "$REPO_ROOT" && "$BAZEL" test "${TARGETS[@]}" \
    --keep_going --test_output=summary "${BAZEL_FLAGS[@]}") \
    > "$RUN1_LOG" 2>&1
run1_rc=$?
echo ""

mapfile -t FAILED < <(_parse_failed_targets "$RUN1_LOG")

if [ ${#FAILED[@]} -eq 0 ]; then
    # Exit code 0 = all green.  Anything else without a named failed test
    # means bazel never got to run the suite (build error, bad flag, ...),
    # which must not be reported as success.
    if [ "$run1_rc" -ne 0 ]; then
        echo "Error: bazel exited $run1_rc without naming a failed test." >&2
        echo "       Likely a build or configuration error; see $RUN1_LOG" >&2
        _retain_logs
        exit "$run1_rc"
    fi
    echo "All tests passed -- nothing to update."
    exit 0
fi

echo "${#FAILED[@]} target(s) failed:"
printf '  %s\n' "${FAILED[@]}" | head -20
[ ${#FAILED[@]} -gt 20 ] && echo "  ... and $(( ${#FAILED[@]} - 20 )) more"
echo ""

# ---------------------------------------------------------------------------
# Step 2: copy goldens out of bazel-testlogs for the failed targets.
# ---------------------------------------------------------------------------
echo "=== Step 2/4: Updating goldens from bazel-testlogs ==="
declare -a UPDATED=()
# Failures this script cannot fix by rewriting a golden.  They are still
# failures: the final report must not claim success while they stand.
declare -a UNRESOLVED=()
for label in "${FAILED[@]}"; do
    _update_goldens_for_target "$label"
    if [ "$updated_any" -eq 1 ]; then
        UPDATED+=("$label")
    else
        UNRESOLVED+=("$label")
    fi
done
echo ""

if [ ${#UPDATED[@]} -eq 0 ]; then
    echo "No goldens were updated -- every failure is something other than a"
    echo "golden mismatch (crash, timeout, metrics, or a real regression)."
    echo "  (see $RUN1_LOG)"
    _retain_logs
    exit 1
fi

if [ "$DRY_RUN" -eq 1 ]; then
    echo "Dry run: ${#UPDATED[@]} target(s) would have goldens rewritten."
    echo "Re-run without -n to apply."
    exit 0
fi

echo "${#UPDATED[@]} target(s) had goldens rewritten."
echo ""

# ---------------------------------------------------------------------------
# Step 3: re-run ONLY the targets whose goldens changed, and converge.
#
# Scoped deliberately: a target that passed in step 1 is untouched by these
# rewrites, so re-running it can only cost time.  Bazel would also happily
# serve a cache hit for it, but the summary would then be noise.
#
# Why this needs a second pass ("embedded diff" convergence)
#   Several tests diff a secondary output themselves (diff_files on a DEF)
#   and print the verdict INTO the run log -- e.g. gpl's simple01 emits
#   "Differences found at line 962." when its .defok does not match.  That
#   makes the .ok golden depend on whether the OTHER goldens were already
#   correct when the log was captured:
#
#     pass 1: .defok is stale -> log contains "Differences found"
#             -> both .defok and .ok are rewritten, but the .ok just captured
#                records the failure that the .defok fix has now removed
#     pass 2: .defok is correct -> log is clean -> .ok is rewritten again,
#             this time from a log that reflects a fully-consistent tree
#
#   So one copy pass is provably not enough whenever a test has both a log
#   golden and a self-diffed output golden.  The ctest script handles this as
#   a separate "step 1b" that greps committed .ok files for the marker; doing
#   it as a convergence loop here is strictly more general, because it also
#   catches the case where the marker was never committed in the first place.
#   Two extra passes are plenty in practice -- the dependency is one level
#   deep -- and the loop stops as soon as a pass changes nothing.
# ---------------------------------------------------------------------------
echo "=== Step 3/4: Re-running the ${#UPDATED[@]} updated target(s) ==="

MAX_PASSES=3
pass=1
# Re-run the updated targets AND their language siblings: a shared golden
# means an update driven by the tcl run also changes what the py run sees.
mapfile -t RETRY < <(_add_language_siblings "${UPDATED[@]}")
if [ ${#RETRY[@]} -eq 0 ]; then
    # The sibling query failed for some reason; fall back to what we know.
    RETRY=("${UPDATED[@]}")
fi
if [ ${#RETRY[@]} -gt ${#UPDATED[@]} ]; then
    echo "  including $(( ${#RETRY[@]} - ${#UPDATED[@]} )) language sibling(s)" \
        "that share an updated golden"
fi
declare -a STILL_FAILING=()
run2_rc=0

while :; do
    echo "  pass $pass: re-running ${#RETRY[@]} target(s) (log: $RUN2_LOG.$pass)"
    (cd "$REPO_ROOT" && "$BAZEL" test "${RETRY[@]}" \
        --keep_going --test_output=summary "${BAZEL_FLAGS[@]}") \
        > "$RUN2_LOG.$pass" 2>&1
    run2_rc=$?

    mapfile -t STILL_FAILING < <(_parse_failed_targets "$RUN2_LOG.$pass")

    # Green, or out of passes: either way this loop is done.
    if [ ${#STILL_FAILING[@]} -eq 0 ] || [ "$pass" -ge "$MAX_PASSES" ]; then
        cp "$RUN2_LOG.$pass" "$RUN2_LOG" 2> /dev/null
        break
    fi

    # A still-failing target may simply have had its log golden captured while
    # a sibling golden was still stale (see the comment above).  Re-copy and
    # try again; if nothing changes, the failure is real and we stop.
    echo "  pass $pass: ${#STILL_FAILING[@]} still failing -- re-copying goldens"
    declare -a RECONVERGED=()
    for label in "${STILL_FAILING[@]}"; do
        _update_goldens_for_target "$label"
        [ "$updated_any" -eq 1 ] && RECONVERGED+=("$label")
    done

    if [ ${#RECONVERGED[@]} -eq 0 ]; then
        # Nothing left to change, so another run would be identical.
        cp "$RUN2_LOG.$pass" "$RUN2_LOG" 2> /dev/null
        break
    fi

    RETRY=("${RECONVERGED[@]}")
    pass=$((pass + 1))
done
echo ""

# ---------------------------------------------------------------------------
# Step 4: report.
# ---------------------------------------------------------------------------
echo "=== Step 4/4: Result ==="
if [ ${#STILL_FAILING[@]} -gt 0 ]; then
    echo "WARNING: still failing after the golden update:"
    printf '  %s\n' "${STILL_FAILING[@]}"
    echo "  A refreshed golden that still does not match is not a golden"
    echo "  problem: expect a crash, a timeout, nondeterministic output, or a"
    echo "  genuine regression.  Inspect before committing: $RUN2_LOG"
    _retain_logs
    exit 1
fi

if [ "$run2_rc" -ne 0 ]; then
    echo "WARNING: bazel exited $run2_rc without naming a failed test."
    echo "  (see $RUN2_LOG)"
    _retain_logs
    exit "$run2_rc"
fi

# The updated targets are green, but targets skipped in step 2 were never
# fixed and never re-run.  Saying "all pass" here would be false: they are
# still failing, this script just cannot fix them by rewriting a golden.
if [ ${#UNRESOLVED[@]} -gt 0 ]; then
    echo "Updated targets pass, but ${#UNRESOLVED[@]} failure(s) remain that a"
    echo "golden update cannot fix:"
    printf '  %s\n' "${UNRESOLVED[@]}"
    echo "  These were skipped in step 2 (see the reason printed there) and"
    echo "  are still failing.  They need a code or test fix: $RUN1_LOG"
    _retain_logs
    echo ""
    if [ -n "$(git -C "$REPO_ROOT" diff --stat -- '*ok')" ]; then
        echo "Goldens changed in the working tree:"
        git -C "$REPO_ROOT" diff --stat -- '*ok' | sed 's/^/  /'
        echo ""
        echo "Review the diff before committing: these are CI's reference outputs."
    fi
    exit 1
fi

echo "All updated targets pass under Bazel -- the build CI gates on."
echo ""
golden_diff="$(git -C "$REPO_ROOT" diff --stat -- '*ok')"
if [ -n "$golden_diff" ]; then
    echo "Goldens changed in the working tree:"
    echo "$golden_diff" | sed 's/^/  /'
    echo ""
    echo "Review the diff before committing: these are CI's reference outputs."
else
    # The tests failed, goldens were rewritten, and the tree is nonetheless
    # clean: the regenerated content equals what is already committed.  That
    # means the goldens were never the problem -- the working tree had a
    # stale/edited golden, or the failure was environmental.  Worth saying
    # explicitly, because a blank diff otherwise reads like a malfunction.
    echo "No golden differs from HEAD: the regenerated content matches what is"
    echo "already committed, so nothing needs to be committed.  The step-1"
    echo "failures came from goldens that were locally modified, not from a"
    echo "change in behaviour."
fi

if [ "$KEEP_LOGS" -eq 1 ]; then
    echo ""
    echo "Logs kept in: $LOG_DIR"
fi
