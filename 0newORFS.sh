#!/bin/bash

# This script sets up a repository with multiple remotes and configures submodules accordingly.
# Usage:
#   ./script_name.sh <remote_type> <directory_name>
# Arguments:
#   remote_type     - Type of remote to set as the current remote (options: private, upstream, myORFS).
#   directory_name  - Name of the directory where the repository will be cloned.
# Example:
#   ./script_name.sh upstream OpenROAD-flow-scripts

# Function to determine if a string is an integer
is_integer() {
    [[ "$1" =~ ^[0-9]+$ ]]
}

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
        upstream|*)
            echo "git@github.com:The-OpenROAD-Project/OpenROAD-flow-scripts.git"
            ;;
    esac
}

# Function to get the submodule repository remote URL
get_git_sub_remote() {
    local remote_type="$1"
    case "$remote_type" in
        myOR)
            echo "git@github.com:gudeh/OpenROAD.git"
            ;;
        private)
            echo "git@github.com:The-OpenROAD-Project-private/OpenROAD.git"
            ;;
        upstream|*)
            echo "git@github.com:The-OpenROAD-Project/OpenROAD.git"
            ;;
    esac
}

# Ensure a remote type is provided
if [[ -z "$1" || -z "$2" ]]; then
    echo "Usage: $0 <remote_type> <directory_name>"
    echo "Remote types: private, upstream, myORFS"
    exit 1
fi

remote_type="$1"
directory_name="$2"

# Validate remote type
if [[ ! "$remote_type" =~ ^(private|upstream|myORFS)$ ]]; then
    echo "Invalid remote type: $remote_type"
    echo "Valid options are: private, upstream, myORFS"
    exit 1
fi

# Set and clone the main repository
main_remote=$(get_git_remote "$remote_type")
echo "Cloning into $directory_name from $main_remote"
git clone --recursive "$main_remote" "$directory_name"

# Navigate to the cloned directory
cd "$directory_name" || exit 1

git remote add upstream "$(get_git_remote upstream)"
git remote add private "$(get_git_remote private)"
git remote add myORFS "$(get_git_remote myORFS)"
echo "Added remotes: upstream, private, and myORFS"

git fetch --all --prune

# Remove the default origin remote
git remote remove origin
echo "Removed default origin remote"

# Navigate to the OpenROAD submodule
cd tools/OpenROAD || exit 1

sub_remote=$(get_git_sub_remote "$remote_type")
git remote add upstream "$(get_git_sub_remote upstream)"
git remote add private "$(get_git_sub_remote private)"
git remote add myOR "$(get_git_sub_remote myOR)"
echo "Added remotes: upstream, private, and myOR for the submodule"

git fetch --all --prune

# Remove the default origin remote for the submodule
git remote remove origin
echo "Removed default origin remote for the submodule"

# Return to the main directory
cd ../../..

echo "Remote configuration completed successfully."
