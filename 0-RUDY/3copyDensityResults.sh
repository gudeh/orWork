#!/bin/bash
# retrieving rudy CSV and PNG files from report in each platform and design

destination_folder="evaluate_density"

# Check if the destination folder exists and create it if not
if [ ! -d "$destination_folder" ]; then
    mkdir "$destination_folder"
    echo "Created destination folder: $destination_folder"
else
    echo "Destination folder already exists: $destination_folder"
fi

# Find and copy CSV files
find ./reports -type f -name "*stg3*.csv" -exec cp {} "$destination_folder" \;

# Find and copy PNG files
find ./reports -type f -name "*stg3*.png" -exec cp {} "$destination_folder" \;

# Create a subdirectory for histograms
mkdir -p "$destination_folder/histograms"

echo "CSV and PNG files copied to $destination_folder."
