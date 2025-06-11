import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from PIL import Image

image_dir = './'
output_dir = './histograms'
os.makedirs(output_dir, exist_ok=True)

def concatenate_images_with_titles(image_paths, output_path):
    image_paths.sort()
    images = []
    
    # Try to open images; if an image is missing, use a placeholder
    for image_path in image_paths:
        try:
            images.append(Image.open(image_path))
        except FileNotFoundError:
            # Print a message for missing files and create a placeholder
            print(f"Warning: Image file not found: {image_path}. Using a placeholder.")
            placeholder = Image.new('RGB', (300, 300), (255, 255, 255))  # White square as placeholder
            images.append(placeholder)
    
    fig = plt.figure(figsize=(18, 8))
    gs = gridspec.GridSpec(1, 3, width_ratios=[1, 1, 1])

    for i in range(3):  # Loop over 3 slots
        ax = plt.subplot(gs[i])
        if i < len(images):
            img = np.array(images[i])
            ax.imshow(img)
            ax.set_title(os.path.basename(image_paths[i]) if i < len(image_paths) else "Placeholder", fontsize=14)
        else:
            # If no image available, fill with a blank area
            placeholder = np.ones((300, 300, 3), dtype=np.uint8) * 255
            ax.imshow(placeholder)
            ax.set_title("Placeholder", fontsize=14)
        ax.axis('off')
    
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()

files = os.listdir(image_dir)

grouped_images = {}
total_images_found = 0
total_concatenated_built = 0

for file in files:
    if file.endswith('.png'):
        key = file.split('stg3')[0]
        if key not in grouped_images:
            grouped_images[key] = []
        grouped_images[key].append(os.path.join(image_dir, file))
        total_images_found += 1

for key, image_paths in grouped_images.items():
    # We proceed with the images even if fewer than 3 are available
    output_path = os.path.join(output_dir, f'{key}_concatenated.png')
    concatenate_images_with_titles(image_paths, output_path)
    print(f'Saved concatenated image: {output_path}')
    total_concatenated_built += 1

# Summary of results
print(f'Total images found: {total_images_found}')
print(f'Total concatenated images built: {total_concatenated_built}')

print('Image concatenation complete.')
