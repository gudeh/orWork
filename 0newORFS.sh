#!/bin/bash

# Check if no parameter is provided
if [ $# -eq 0 ]; then
    echo "Error: No integer parameter provided. Please provide an integer."
    echo "Usage: $0 <integer>"
    exit 1
fi

# Check if the provided parameter is a valid integer
if ! [[ "$1" =~ ^[0-9]+$ ]]; then
    echo "Error: '$1' is not a valid integer. Please provide a valid integer."
    echo "Usage: $0 <integer>"
    exit 1
fi

# Assign the integer parameter to a variable
my_integer=$1

# Create a directory based on the integer parameter
directory_name="${my_intger}OpenROAD-flow-scripts"

# Clone the repository into the created directory
git clone --recursive git@github.com:user/repo.git "$directory_name"
