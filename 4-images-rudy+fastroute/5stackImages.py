import os
import shutil
from PIL import Image

# Set your two input folders here
input_folder1 = 'TSC-15-equivMaster'
input_folder2 = 'SCI2-PR'

# Subfolder where histograms are located
histogram_subfolder = 'histograms'

# Output folder
output_folder = 'output-stacked'

# Refresh output folder (delete and recreate)
if os.path.exists(output_folder):
    shutil.rmtree(output_folder)
os.makedirs(output_folder, exist_ok=True)

# Paths to histogram folders
hist_folder1 = os.path.join(input_folder1, histogram_subfolder)
hist_folder2 = os.path.join(input_folder2, histogram_subfolder)

# Get list of PNG files in both folders
files1 = set(f for f in os.listdir(hist_folder1) if f.endswith('.png'))
files2 = set(f for f in os.listdir(hist_folder2) if f.endswith('.png'))

# Count images in each folder
count1 = len(files1)
count2 = len(files2)

# Find matching file names
common_files = files1.intersection(files2)
matched_count = len(common_files)

generated_count = 0
for file_name in common_files:
    path1 = os.path.join(hist_folder1, file_name)
    path2 = os.path.join(hist_folder2, file_name)

    # Open images
    img1 = Image.open(path1)
    img2 = Image.open(path2)

    # Make sure they have the same width
    max_width = max(img1.width, img2.width)
    new_height = img1.height + img2.height

    # Create a new blank image
    combined_img = Image.new('RGB', (max_width, new_height))

    # Paste both images
    combined_img.paste(img1, (0, 0))
    combined_img.paste(img2, (0, img1.height))

    # Save to output folder
    output_path = os.path.join(output_folder, file_name)
    combined_img.save(output_path)
    generated_count += 1

    print(f"Saved stacked image: {output_path}")

# Final summary report
print("\n=== Summary ===")
print(f"Images in {hist_folder1}: {count1}")
print(f"Images in {hist_folder2}: {count2}")
print(f"Matching files: {matched_count}")
print(f"Total images generated: {generated_count}")
