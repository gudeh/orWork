#!/bin/bash

PLACE_DENSITY_VALUES=(0.15 0.20 0.201 0.22 0.24 0.25 0.26 0.28 0.30 0.35)

DESIGN_CONFIG="./designs/sky130hd/microwatt/config.mk"

STRING_PARAM="$1"


for PLACE_DENSITY in "${PLACE_DENSITY_VALUES[@]}"; do
    echo "Opening terminal for PLACE_DENSITY=${PLACE_DENSITY}"
    gnome-terminal -- bash -c "make DESIGN_CONFIG='$DESIGN_CONFIG' FLOW_VARIANT='$PLACE_DENSITY' PLACE_DENSITY='$PLACE_DENSITY' $STRING_PARAM; exec bash" #
    sleep 0.5
done

wait

echo "All jobs completed."
