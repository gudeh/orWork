import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from PIL import Image
import re

image_dir = './'
output_dir = './histograms'

# Refresh histograms directory
if os.path.exists(output_dir):
    for f in os.listdir(output_dir):
        os.remove(os.path.join(output_dir, f))
else:
    os.makedirs(output_dir)

alias_map = {
    'bp': 'black_parrot',
}

def normalize_key(raw_key):
    key = raw_key.replace('_top', '').replace('_bot', '').rstrip('_')
    for short, full in alias_map.items():
        pattern = r'\b' + re.escape(short) + r'\b'
        if re.search(pattern, key):
            key = re.sub(pattern, full, key)
    return key

def concatenate_images(final_img, density_imgs, rudy_imgs, output_path):
    if density_imgs:
        cols = max(len(density_imgs), len(rudy_imgs)) + 1
        fig = plt.figure(figsize=(5 * cols, 10))
        gs = gridspec.GridSpec(2, cols, width_ratios=[1] * cols)

        for col in range(cols):
            ax = plt.subplot(gs[0, col])
            if col == 0:
                placeholder = np.ones((300, 300, 3), dtype=np.uint8) * 255
                ax.imshow(placeholder)
                ax.set_title("Placeholder", fontsize=10)
            elif col - 1 < len(density_imgs):
                img_path = density_imgs[col - 1]
                try:
                    img = Image.open(img_path)
                    ax.imshow(np.array(img))
                    ax.set_title(os.path.basename(img_path), fontsize=10)
                except FileNotFoundError:
                    placeholder = np.ones((300, 300, 3), dtype=np.uint8) * 255
                    ax.imshow(placeholder)
                    ax.set_title("Missing", fontsize=10)
            ax.axis('off')

        for col in range(cols):
            ax = plt.subplot(gs[1, col])
            if col == 0:
                if final_img:
                    try:
                        img = Image.open(final_img)
                        ax.imshow(np.array(img))
                        ax.set_title(os.path.basename(final_img), fontsize=10)
                    except FileNotFoundError:
                        placeholder = np.ones((300, 300, 3), dtype=np.uint8) * 255
                        ax.imshow(placeholder)
                        ax.set_title("Missing", fontsize=10)
                else:
                    placeholder = np.ones((300, 300, 3), dtype=np.uint8) * 255
                    ax.imshow(placeholder)
                    ax.set_title("Missing", fontsize=10)
            elif col - 1 < len(rudy_imgs):
                img_path = rudy_imgs[col - 1]
                try:
                    img = Image.open(img_path)
                    ax.imshow(np.array(img))
                    ax.set_title(os.path.basename(img_path), fontsize=10)
                except FileNotFoundError:
                    placeholder = np.ones((300, 300, 3), dtype=np.uint8) * 255
                    ax.imshow(placeholder)
                    ax.set_title("Missing", fontsize=10)
            ax.axis('off')

    else:
        cols = 1 + len(rudy_imgs)
        fig = plt.figure(figsize=(5 * cols, 5))
        gs = gridspec.GridSpec(1, cols, width_ratios=[1] * cols)
        for col in range(cols):
            ax = plt.subplot(gs[0, col])
            if col == 0:
                if final_img:
                    try:
                        img = Image.open(final_img)
                        ax.imshow(np.array(img))
                        ax.set_title(os.path.basename(final_img), fontsize=10)
                    except FileNotFoundError:
                        placeholder = np.ones((300, 300, 3), dtype=np.uint8) * 255
                        ax.imshow(placeholder)
                        ax.set_title("Missing", fontsize=10)
                else:
                    placeholder = np.ones((300, 300, 3), dtype=np.uint8) * 255
                    ax.imshow(placeholder)
                    ax.set_title("Missing", fontsize=10)
            elif col - 1 < len(rudy_imgs):
                img_path = rudy_imgs[col - 1]
                try:
                    img = Image.open(img_path)
                    ax.imshow(np.array(img))
                    ax.set_title(os.path.basename(img_path), fontsize=10)
                except FileNotFoundError:
                    placeholder = np.ones((300, 300, 3), dtype=np.uint8) * 255
                    ax.imshow(placeholder)
                    ax.set_title("Missing", fontsize=10)
            ax.axis('off')

    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()

files = os.listdir(image_dir)

grouped_images = {}
total_images_found = 0
total_concatenated_built = 0

for file in files:
    if file.endswith('.png') or file.endswith('.webp'):
        if re.search(r'stg3_[45]', file):  # exclude stage 3_4 and 3_5
            continue

        match = re.split(r'-(stg3|stg5)_\d+|[-_]final_placement', file)
        if not match or not match[0]:
            continue
        key = normalize_key(match[0])

        if key not in grouped_images:
            grouped_images[key] = {'final': None, 'density': [], 'rudy': []}

        full_path = os.path.join(image_dir, file)
        if 'final_placement' in file:
            grouped_images[key]['final'] = full_path
        elif 'Pdensity' in file:
            grouped_images[key]['density'].append(full_path)
        elif 'rudy' in file.lower() or 'grt' in file.lower():
            grouped_images[key]['rudy'].append(full_path)

        total_images_found += 1

for key, types in grouped_images.items():
    density_imgs = sorted(types['density'])
    rudy_imgs = sorted(types['rudy'])

    output_path = os.path.join(output_dir, f'{key}_concatenated.png')
    concatenate_images(types['final'], density_imgs, rudy_imgs, output_path)
    print(f'Saved concatenated image: {output_path}')
    total_concatenated_built += 1

print(f'Total images found: {total_images_found}')
print(f'Total concatenated images built: {total_concatenated_built}')
print('Image concatenation complete.')
