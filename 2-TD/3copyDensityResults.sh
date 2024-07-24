#!/bin/bash
# retrieving rudy CSV and PNG files from report in each platform and design

destination_folder="evaluate_density"

if [ ! -d "$destination_folder" ]; then
    mkdir "$destination_folder"
fi

for pattern in './reports/*/*/base/*3_*.csv' './reports/*/*/base/*3_*.png'; do
    find . -path "$pattern" -exec cp {} "$destination_folder" \;
done

mkdir "$destination_folder/histograms"

echo "Files copied to $destination_folder."
