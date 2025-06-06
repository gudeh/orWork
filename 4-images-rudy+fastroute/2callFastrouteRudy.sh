#!/bin/bash

set -e

DESIGNS_DIR="./designs"
MAX_JOBS=3

for platform in "$DESIGNS_DIR"/*; do
    if [ -d "$platform" ]; then
        platform_name=$(basename "$platform")
        jobs=0

        for design in "$platform"/*; do
            if [ -d "$design" ]; then
                export design_name=$(basename "$design")		

		command="make check_rudy STAGE=3_3_place_gp DESIGN_CONFIG=\"$DESIGNS_DIR/$platform_name/$design_name/config.mk\" my_design_name=$design_name"
                eval $command &
                echo -e "\n->$command"
		
                command="make check_fastroute STAGE=5_1_grt DESIGN_CONFIG=\"$DESIGNS_DIR/$platform_name/$design_name/config.mk\" my_design_name=$design_name"
                eval $command &
                echo -e "\n->$command"

		command="make check_fastroute STAGE=5_2_route DESIGN_CONFIG=\"$DESIGNS_DIR/$platform_name/$design_name/config.mk\" my_design_name=$design_name"
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
