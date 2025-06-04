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

# Find and copy final placement files with renaming
find ./reports -type f -name "*final_placement.webp" | while read filepath; do
    # Extract platform and design from the path
    platform=$(echo "$filepath" | awk -F'/' '{print $(NF-3)}')
    design=$(echo "$filepath" | awk -F'/' '{print $(NF-2)}')

    # Build new filename
    new_filename="${platform}-${design}-final_placement.webp"

    # Copy with new name
    cp "$filepath" "$destination_folder/$new_filename"
done

# Create a subdirectory for histograms
mkdir -p "$destination_folder/histograms"

echo "CSV, PNG, and renamed final placement files copied to $destination_folder."
