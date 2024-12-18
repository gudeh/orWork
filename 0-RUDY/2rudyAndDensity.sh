#!/bin/bash

set -e

DESIGNS_DIR="./designs"
MAX_JOBS=10
LOG_FILE="orCalls.log"

# Ensure the log file is empty before starting
> "$LOG_FILE"

for platform in "$DESIGNS_DIR"/*; do
    if [ -d "$platform" ]; then
        platform_name=$(basename "$platform")
        jobs=0

        for design in "$platform"/*; do
            if [ -d "$design" ]; then
                export design_name=$(basename "$design")

                # Array of STAGE values
                #stages=("5_2_route" "4_cts" "3_3_place_gp" "3_5_place_dp")
                stages=("3_3_place_gp")

                # Array of commands
                commands=("make check_rudy")

                for stage in "${stages[@]}"; do
                    for command_base in "${commands[@]}"; do
                        command="$command_base STAGE=$stage DESIGN_CONFIG=\"$DESIGNS_DIR/$platform_name/$design_name/config.mk\" my_design_name=$design_name"
                        eval $command >> "$LOG_FILE" 2>&1 &
                        echo -e "\n->$command"
                        let jobs+=1

                        # Wait for all jobs to complete before starting new ones
                        if (( jobs >= MAX_JOBS )); then
                            wait
                            jobs=0
                        fi
                    done
                done
            fi
        done

        wait  # Wait for the remaining background jobs to complete
    fi
done
