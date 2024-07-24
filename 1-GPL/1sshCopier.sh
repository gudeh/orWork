#!/bin/bash

# The remote host name
REMOTE_HOST="augusto-1"

# Base directories for remote files
BASE_DIRS=("gplWithRudy" "standardGpl")

# Loop through each base directory
for BASE in "${BASE_DIRS[@]}"; do
  # The full path to the remote directory
  REMOTE_DIR="~/$BASE/flow/logs/"

  # Create the root directory locally
  mkdir -p ./$BASE

  # Get the list of first-level directories under each base directory
  DIRS=$(gcloud compute ssh $REMOTE_HOST --command "ls $REMOTE_DIR")

  # Loop through each directory in the base directory
  for DIR in $DIRS; do
    # Create a local directory structure including the base directory
    mkdir -p ./$BASE/$DIR

    # Copy each .log file from the second-level directory
    gcloud compute scp --recurse "$REMOTE_HOST:$REMOTE_DIR/$DIR/*.log" ./$BASE/$DIR/
  done
done
