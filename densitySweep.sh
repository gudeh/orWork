#!/bin/bash

PLACE_DENSITY_VALUES=(0.1 0.53 0.6 0.8)

DESIGN_CONFIG="designs/rapidus2hp/hercules_is_int/config.mk"

STRING_PARAM="$1"


for PLACE_DENSITY in "${PLACE_DENSITY_VALUES[@]}"; do
    echo "Opening terminal for PLACE_DENSITY=${PLACE_DENSITY}"

    # Construct the command string clearly
    CMD="make \
    DESIGN_CONFIG='$DESIGN_CONFIG' \
    FLOW_VARIANT='$PLACE_DENSITY' \
    PLACE_DENSITY='$PLACE_DENSITY' \
    SYNTH_HDL_FRONTEND=verific \
    PLATFORM_HOME=/workspace/rapidus/current/rapidus/ \
    $STRING_PARAM"

    # Pass the variable to the terminal
    gnome-terminal -- bash -c "$CMD; exec bash"
    
    sleep 0.5
done

wait

echo "All jobs completed."
