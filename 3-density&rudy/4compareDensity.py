import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from PIL import Image

image_dir = './'
output_dir = './histograms'
os.makedirs(output_dir, exist_ok=True)

def concatenate_images_2rows(image_groups, output_path):
    fig = plt.figure(figsize=(18, 12))  # Increased height to fit two rows
    gs = gridspec.GridSpec(2, 3, height_ratios=[1, 1], width_ratios=[1, 1, 1])

    for row, image_paths in enumerate(image_groups):
        for col in range(3):
            ax = plt.subplot(gs[row, col])
            if col < len(image_paths):
                try:
                    img = Image.open(image_paths[col])
                    ax.imshow(np.array(img))
                    ax.set_title(os.path.basename(image_paths[col]), fontsize=12)
                except FileNotFoundError:
                    print(f"Warning: Image file not found: {image_paths[col]}. Using a placeholder.")
                    placeholder = np.ones((300, 300, 3), dtype=np.uint8) * 255
                    ax.imshow(placeholder)
                    ax.set_title("Placeholder", fontsize=12)
            else:
                placeholder = np.ones((300, 300, 3), dtype=np.uint8) * 255
                ax.imshow(placeholder)
                ax.set_title("Placeholder", fontsize=12)
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
            grouped_images[key] = {'density': [], 'rudy': []}

        full_path = os.path.join(image_dir, file)
        if 'Pdensity' in file:
            grouped_images[key]['density'].append(full_path)
        elif 'rudy' in file.lower():  # assuming filenames contain 'rudy'
            grouped_images[key]['rudy'].append(full_path)
        total_images_found += 1

for key, types in grouped_images.items():
    image_groups = [sorted(types['density']), sorted(types['rudy'])]
    output_path = os.path.join(output_dir, f'{key}_concatenated.png')
    concatenate_images_2rows(image_groups, output_path)
    print(f'Saved concatenated image: {output_path}')
    total_concatenated_built += 1

print(f'Total images found: {total_images_found}')
print(f'Total concatenated images built: {total_concatenated_built}')
print('Image concatenation complete.')
