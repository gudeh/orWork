#!/bin/bash

DESIGNS_DIR="./designs"

for platform in "$DESIGNS_DIR"/*; do
    if [ -d "$platform" ]; then
        platform_name=$(basename "$platform")

        for design in "$platform"/*; do
            if [ -d "$design" ]; then
                design_name=$(basename "$design")

                make check_rudy DESIGN_CONFIG="$DESIGNS_DIR/$platform_name/$design_name/config.mk"
            fi
        done
    fi
done
