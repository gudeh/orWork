#!/bin/bash

#PLACE_DENSITY_VALUES=(0.1 0.53 0.6)
PLACE_DENSITY_VALUES=(0.54 0.55 0.56)

DESIGN_CONFIG="designs/rapidus2hp/hercules_is_int/config.mk"
#DESIGN_CONFIG="designs/rapidus2hp/gcd/config.mk"

STRING_PARAM="$1"
#SYNTH_HDL_FRONTEND=verific \

for PLACE_DENSITY in "${PLACE_DENSITY_VALUES[@]}"; do
    # Construct the command string clearly
    CMD="make \
    DESIGN_CONFIG='$DESIGN_CONFIG' \
    FLOW_VARIANT='$PLACE_DENSITY' \
    PLACE_DENSITY='$PLACE_DENSITY' \
    PLATFORM_HOME=/workspace/rapidus/current/rapidus/ \
    $STRING_PARAM"

    echo "----------------------------------------"
    echo "Check: Launching terminal for density ${PLACE_DENSITY}..."
    echo "Command: $CMD"
    echo "----------------------------------------"

    # Pass the variable to the terminal
    gnome-terminal -- bash -c "$CMD; exec bash"
    
    sleep 0.5
done

wait

echo "All jobs completed."
