#!/bin/bash

# Check if no parameter is provided
# if [ $# -eq 0 ]; then
#     echo "Error: No parameter provided. Please provide an integer or a string for the folder name."
#     echo "Usage: $0 <integer|string>"
#     exit 1
# fi

# Function to check if the argument is a valid integer
is_integer() {
    [[ "$1" =~ ^[0-9]+$ ]]
}

# Check if the provided parameter is a valid integer or a string
if is_integer "$1"; then
    # It's an integer, use it in the directory name
    directory_name="${1}OpenROAD-flow-scripts"
else
    # It's a string, use it directly as the directory name
    directory_name="$1"
fi

# Create a directory based on the parameter
echo "Creating directory: $directory_name"
mkdir -p "$directory_name"  # -p to create nested directories if needed

# Clone the repository into the created directory
git clone --recursive git@github.com:gudeh/OpenROAD-flow-scripts.git "$directory_name"

cd "./$directory_name"

git remote add upstream git@github.com:The-OpenROAD-Project/OpenROAD-flow-scripts.git

#git fetch upstream

#git merge upstream/master

cd "./tools/OpenROAD"

git remote add upstream git@github.com:The-OpenROAD-Project/OpenROAD.git

#git fetch upstream

#git merge upstream/master

cd "../../"

# Uncomment the following line to build OpenROAD after cloning
# ./build_openroad.sh --local --nice --no_init
