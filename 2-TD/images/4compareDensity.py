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
    images = [Image.open(image) for image in image_paths]
    
    fig = plt.figure(figsize=(18, 8))
    gs = gridspec.GridSpec(1, 3, width_ratios=[1, 1, 1])

    for i, image_path in enumerate(image_paths):
        ax = plt.subplot(gs[i])
        img = np.array(images[i])
        ax.imshow(img)
        ax.set_title(os.path.basename(image_path), fontsize=14)
        ax.axis('off')
    
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()

files = os.listdir(image_dir)

grouped_images = {}
for file in files:
    if file.endswith('.png'):
        key = file.split('_')[0]
        if key not in grouped_images:
            grouped_images[key] = []
        grouped_images[key].append(os.path.join(image_dir, file))

for key, image_paths in grouped_images.items():
    if len(image_paths) == 3:
        output_path = os.path.join(output_dir, f'{key}_concatenated.png')
        concatenate_images_with_titles(image_paths, output_path)
        print(f'Saved concatenated image: {output_path}')

print('Image concatenation complete.')
