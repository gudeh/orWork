#!/bin/bash

# Find the first .zip file in the current directory
ZIP_FILE=$(find . -maxdepth 1 -type f -name "*.zip" | head -n 1)

# Check if a zip file was found
if [[ -z "$ZIP_FILE" ]]; then
  echo "No zip file found in the current directory."
  exit 1
fi

echo "Found zip file: $ZIP_FILE"

# Create a temporary extraction directory
TEMP_DIR="temp_extracted"

# Unzip the contents to the temporary directory
unzip "$ZIP_FILE" -d "$TEMP_DIR"

# Move everything from archive/flow to the current directory
if [[ -d "$TEMP_DIR/archive/flow" ]]; then
  mv "$TEMP_DIR/archive/flow/"* .
  echo "Extraction complete!"
else
  echo "The expected path 'archive/flow' was not found in the zip file."
fi

# Remove the temporary extraction directory
rm -rf "$TEMP_DIR"
