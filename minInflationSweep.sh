#!/usr/bin/env bash

MIN_INFLATION_VALUES=(0.95)
MAX_INFLATION_VALUES=(3 1.33 1.1)
INFLATION_COEF_VALUES=(2 1.1 0.5)


DESIGN_CONFIG="designs/rapidus2hp/hercules_is_int/config.mk" 
#DESIGN_CONFIG="designs/rapidus2hp/gcd/config.mk"
PLATFORM=$(echo "$DESIGN_CONFIG" | cut -d'/' -f2)
DESIGN=$(echo "$DESIGN_CONFIG" | cut -d'/' -f3)

STRING_PARAM="$1"
# Set the maximum number of parallel jobs
MAX_PARALLEL_JOBS=4
# Calculate total number of jobs (Loop combinations + 1 fixed run)
TOTAL_JOBS=$(( ${#MIN_INFLATION_VALUES[@]} * ${#MAX_INFLATION_VALUES[@]} * ${#INFLATION_COEF_VALUES[@]} + 1 ))
CURRENT_JOB=0

# Define common arguments for all runs
BASE_ARGS="DESIGN_CONFIG=\"$DESIGN_CONFIG\" \
    PLATFORM_HOME=/workspace/rapidus/current/rapidus/ \
    SYNTH_HDL_FRONTEND=verific \
    FASTROUTE_TCL="/workspace/7ORFS/flow/fastroute.tcl" \
    $STRING_PARAM"

# --- Launch Single Fixed Default Run ---
CURRENT_JOB=$((CURRENT_JOB + 1))
echo "----------------------------------------"
echo "Launching fixed run (Job ${CURRENT_JOB}/${TOTAL_JOBS})"
CMD="make $BASE_ARGS FLOW_VARIANT=\"default\""
echo "Running: $CMD"
eval "$CMD" > "logs/default.log" 2>&1 &
# -------------------------------

for MIN_INFLATION in "${MIN_INFLATION_VALUES[@]}"; do
    for MAX_INFLATION in "${MAX_INFLATION_VALUES[@]}"; do
        for INFLATION_COEF in "${INFLATION_COEF_VALUES[@]}"; do
            
            CURRENT_JOB=$((CURRENT_JOB + 1))
            PERCENTAGE=$(( 100 * CURRENT_JOB / TOTAL_JOBS ))

            # 1. Check how many jobs are ACTUALLY running right now
            while (( $(jobs -r | wc -l) >= MAX_PARALLEL_JOBS )); do
                echo "Wait: Limit reached, waiting for a slot... (${PERCENTAGE}% of jobs launched)"
                wait -n  # Wait for ANY one job to finish
            done

            echo "----------------------------------------"
            echo "Launching job ${CURRENT_JOB}/${TOTAL_JOBS} (${PERCENTAGE}%): min=${MIN_INFLATION}, max=${MAX_INFLATION}, coef=${INFLATION_COEF}"
            
            # Construct the command string for the parameterized run
            CMD="make \
                $BASE_ARGS \
                FLOW_VARIANT=\"min${MIN_INFLATION}_max${MAX_INFLATION}_coef${INFLATION_COEF}\" \
                MIN_INFLATION=\"$MIN_INFLATION\" \
                MAX_INFLATION=\"$MAX_INFLATION\" \
                INFLATION_COEF=\"$INFLATION_COEF\""

            echo "Running: $CMD"

            # 2. Launch job in background
            eval "$CMD" > "logs/run_min${MIN_INFLATION}_max${MAX_INFLATION}_coef${INFLATION_COEF}.log" 2>&1 &

        done
    done
done

# Wait for the very last set of jobs to finish
echo "Waiting for all remaining jobs to complete..."
wait
echo "All jobs completed."


# --- Post-processing ---
echo "Starting post-processing..."

# Process Reports
REPORT_DIR="./reports/${PLATFORM}/${DESIGN}/"
if [ -d "$REPORT_DIR" ]; then
    cd "$REPORT_DIR" || { echo "Error: Failed to enter $REPORT_DIR"; exit 1; }
    
    if [ -f "/workspace/orWork/1reportsToCongestionImages.py" ]; then
        cp /workspace/orWork/1reportsToCongestionImages.py .
        python3 1reportsToCongestionImages.py || echo "Warning: 1reportsToCongestionImages.py failed"
    else
        echo "Error: /workspace/orWork/1reportsToCongestionImages.py not found"
    fi
    
    # Return to root of script execution
    cd - > /dev/null || exit 1
else
    echo "Error: Report directory $REPORT_DIR does not exist"
fi

# Process Logs
LOG_DIR="./logs/${PLATFORM}/${DESIGN}/"
if [ -d "$LOG_DIR" ]; then
    cd "$LOG_DIR" || { echo "Error: Failed to enter $LOG_DIR"; exit 1; }
    
    if [ -f "/workspace/orWork/1logsToWNSandRoutability.py" ]; then
        cp /workspace/orWork/1logsToWNSandRoutability.py .
        python3 1logsToWNSandRoutability.py || echo "Warning: 1logsToWNSandRoutability.py failed"
    else
        echo "Error: /workspace/orWork/1logsToWNSandRoutability.py not found"
    fi
    
    # Return to root
    cd - > /dev/null || exit 1
else
    echo "Error: Log directory $LOG_DIR does not exist"
fi

# Collect Results
# Use nullglob to avoid errors if no png files exist
shopt -s nullglob
cp ./reports/${PLATFORM}/${DESIGN}/*.png ./ 2>/dev/null || echo "No report PNGs found to copy."
cp ./logs/${PLATFORM}/${DESIGN}/*.png ./ 2>/dev/null || echo "No log PNGs found to copy."
shopt -u nullglob

echo "All reports and logs processed."