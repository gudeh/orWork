#!/bin/bash

is_integer() {
    [[ "$1" =~ ^[0-9]+$ ]]
}

get_git_remote() {
    local remote_type="${1:-upstream}"  # Default to 'upstream' if empty
    case "$remote_type" in
        origin)
            echo "git@github.com:gudeh/OpenROAD-flow-scripts.git"
            ;;
        private)
            echo "git@github.com:The-OpenROAD-Project-private/OpenROAD-flow-scripts.git"
            ;;
        *)  # Default is upstream
            echo "git@github.com:The-OpenROAD-Project/OpenROAD-flow-scripts.git"
            ;;
    esac
}

get_git_sub_remote() {
    local remote_type="${1:-upstream}"  # Default to 'upstream' if empty
    case "$remote_type" in
        origin)
            echo "git@github.com:gudeh/OpenROAD.git"
            ;;
        private)
            echo "git@github.com:The-OpenROAD-Project-private/OpenROAD.git"
            ;;
        *)  # Default is upstream
            echo "git@github.com:The-OpenROAD-Project/OpenROAD.git"
            ;;
    esac
}

# Validate and set directory name
if is_integer "$1"; then
    directory_name="${1}OpenROAD-flow-scripts"
else
    directory_name="$1"
fi

# Clone the repository
main_remote=$(get_git_remote "$2")
echo "Cloning into $directory_name from $main_remote"
git clone --recursive "$main_remote" "$directory_name"

# Navigate to the cloned directory
cd "./$directory_name"

# Fetch all changes and prune any stale branches
git fetch --all --prune

cd "./tools/OpenROAD"

# If separate repository handling is necessary, fetch and prune here as well
git fetch --all --prune

cd "../../../"

# Further commands to build or set up the environment
# ./build_openroad.sh --local --nice --no_init 
