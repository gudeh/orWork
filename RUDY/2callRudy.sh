#!/bin/bash

DESIGNS_DIR="./designs"
MAX_JOBS=5

for platform in "$DESIGNS_DIR"/*; do
    if [ -d "$platform" ]; then
        platform_name=$(basename "$platform")
        jobs=0

        for design in "$platform"/*; do
            if [ -d "$design" ]; then
                design_name=$(basename "$design")
                command="make check_rudy DESIGN_CONFIG=\"$DESIGNS_DIR/$platform_name/$design_name/config.mk\""
                # command="make check_final DESIGN_CONFIG=\"$DESIGNS_DIR/$platform_name/$design_name/config.mk\""
                eval $command &
                echo -e "\n->$command"

                let jobs+=1
                # Wait for all jobs to complete before starting new ones
                if (( jobs >= MAX_JOBS )); then
                    wait
                    jobs=0
                fi
            fi
        done

        wait  # Wait for the remaining background jobs to complete
    fi
done
