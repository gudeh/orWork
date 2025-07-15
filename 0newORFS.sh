#!/bin/bash

# This script sets up a repository with multiple remotes and configures submodules accordingly.
# Usage:
#   ./script_name.sh <remote_type> <directory_name>
# Arguments:
#   remote_type     - Type of remote to set as the current remote (options: private, myORFS).
#   directory_name  - Name of the directory where the repository will be cloned.
# Example:
#   ./script_name.sh private OpenROAD-flow-scripts

# Function to get the main repository remote URL
get_git_remote() {
    local remote_type="$1"
    case "$remote_type" in
        myORFS)
            echo "git@github.com:gudeh/OpenROAD-flow-scripts.git"
            ;;
        private)
            echo "git@github.com:The-OpenROAD-Project-private/OpenROAD-flow-scripts.git"
            ;;
        *)
            echo "Unknown remote type: $remote_type"
            exit 1
            ;;
    esac
}

# Function to get the submodule repository remote URL
get_git_sub_remote() {
    local remote_type="$1"
    case "$remote_type" in
        myORFS)
            echo "git@github.com:gudeh/OpenROAD.git"
            ;;
        private)
            echo "git@github.com:The-OpenROAD-Project-private/OpenROAD.git"
            ;;
        *)
            echo "Unknown remote type: $remote_type"
            exit 1
            ;;
    esac
}

# Ensure required arguments are provided
if [[ -z "$1" || -z "$2" ]]; then
    echo "Usage: $0 <remote_type> <directory_name>"
    echo "Remote types: private, myORFS"
    exit 1
fi

remote_type="$1"
directory_name="$2"

# Validate remote type
if [[ ! "$remote_type" =~ ^(private|myORFS)$ ]]; then
    echo "Invalid remote type: $remote_type"
    echo "Valid options are: private, myORFS"
    exit 1
fi

# Clone the main repository
main_remote=$(get_git_remote "$remote_type")
echo "Cloning into $directory_name from $main_remote"
git clone --recursive "$main_remote" "$directory_name"

# Navigate to the cloned directory
cd "$directory_name" || exit 1

git remote add private "$(get_git_remote private)"
git remote add myORFS "$(get_git_remote myORFS)"
echo "Added remotes: private and myORFS"

git fetch --all --prune

# Remove the default origin remote
git remote remove origin
echo "Removed default origin remote"

# Navigate to the OpenROAD submodule
cd tools/OpenROAD || exit 1

sub_remote=$(get_git_sub_remote "$remote_type")
git remote add private "$(get_git_sub_remote private)"
git remote add myORFS "$(get_git_sub_remote myORFS)"
echo "Added remotes: private and myORFS for the submodule"

git fetch --all --prune

# Remove the default origin remote for the submodule
git remote remove origin
echo "Removed default origin remote for the submodule"

# Return to the main directory
cd ../../..

echo "Remote configuration completed successfully."
