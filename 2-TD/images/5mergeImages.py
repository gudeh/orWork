import os
from PIL import Image, ImageOps, ImageDraw, ImageFont

def trim_whitespace(image):
    gray_image = image.convert("L")
    inverted_image = ImageOps.invert(gray_image)
    bbox = inverted_image.getbbox()
    
    if bbox:
        return image.crop(bbox)
    return image

# List of directories
directories =['./nightly4698/histograms/', './1non-virtual/histograms/', './2non-virtual/histograms/', './3non-virtual/histograms/']
output_dir = 'compare_density'

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Collect the union of image names across all directories
all_images = set()
for directory in directories:
    if os.path.exists(directory):
        all_images.update(os.listdir(directory))

# Load a default font (PIL should have at least one font installed)
try:
    font = ImageFont.load_default()
except IOError:
    font = None  # In case no font is available, PIL will use a fallback font

# Process each image across all directories
for image_name in all_images:
    images = []
    max_width = 0

    # Load each image, trim whitespace, and add to list
    for directory in directories:
        image_path = os.path.join(directory, image_name)
        
        if os.path.exists(image_path):
            img = Image.open(image_path)
            img = trim_whitespace(img)
            images.append((directory, img))
        else:
            print(f"Warning: {image_path} not found. Using a placeholder.")
            placeholder = Image.new('RGB', (300, 300), (255, 255, 255))  # White placeholder
            images.append((directory, placeholder))
        
        # Update max_width to ensure all images align
        max_width = max(max_width, images[-1][1].width)

    # Resize images to have the same width as the widest image
    resized_images = []
    for dir_name, img in images:
        if img.width != max_width:
            img = img.resize((max_width, int(img.height * (max_width / img.width))), Image.Resampling.LANCZOS)
        resized_images.append((dir_name, img))

    # Calculate total height for labels and images
    total_image_height = sum(img.height for _, img in resized_images) + len(directories) * 20  # Adjust spacing for labels
    combined_image = Image.new('RGB', (max_width, total_image_height), (255, 255, 255))  # White background for clarity

    # Paste each image with a label on top
    y_offset = 0
    draw = ImageDraw.Draw(combined_image)
    for dir_name, img in resized_images:
        # Draw the label above each image using the parent folder name before "histograms"
        label_text = os.path.basename(os.path.dirname(dir_name.rstrip('/')))
        draw.text((10, y_offset), label_text, fill="black", font=font)
        y_offset += 20  # Add space for the label
        
        # Paste the image below the label
        combined_image.paste(img, (0, y_offset))
        y_offset += img.height

    output_path = os.path.join(output_dir, image_name)
    combined_image.save(output_path)

    print(f"Saved combined image with labels: {output_path}")

print("Image processing with labels complete.")
