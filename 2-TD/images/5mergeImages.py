import os
from PIL import Image, ImageOps

def trim_whitespace(image):
    gray_image = image.convert("L")
    inverted_image = ImageOps.invert(gray_image)
    bbox = inverted_image.getbbox()
    
    if bbox:
        return image.crop(bbox)
    return image

dir1 = './nightly4624/histograms/'
dir2 = './SCI8-images/histograms/'
output_dir = 'compare_density'

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

images1 = set(os.listdir(dir1))
images2 = set(os.listdir(dir2))

# Use union of images to handle cases where images are missing in one of the directories
all_images = images1.union(images2)

for image_name in all_images:
    img1_path = os.path.join(dir1, image_name)
    img2_path = os.path.join(dir2, image_name)
    
    # Check if images exist and open them, use placeholders if missing
    img1 = None
    img2 = None
    
    if os.path.exists(img1_path):
        img1 = Image.open(img1_path)
        img1 = trim_whitespace(img1)
    else:
        print(f"Warning: {img1_path} not found. Using a placeholder.")
        img1 = Image.new('RGB', (300, 300), (255, 255, 255))  # White placeholder
    
    if os.path.exists(img2_path):
        img2 = Image.open(img2_path)
        img2 = trim_whitespace(img2)
    else:
        print(f"Warning: {img2_path} not found. Using a placeholder.")
        img2 = Image.new('RGB', (300, 300), (255, 255, 255))  # White placeholder

    # Adjust image widths to match the wider image
    max_width = max(img1.width, img2.width)
    if img1.width != max_width:
        img1 = img1.resize((max_width, int(img1.height * (max_width / img1.width))), Image.Resampling.LANCZOS)
    if img2.width != max_width:
        img2 = img2.resize((max_width, int(img2.height * (max_width / img2.width))), Image.Resampling.LANCZOS)
    
    # Create the combined image
    new_height = img1.height + img2.height
    new_image = Image.new('RGB', (max_width, new_height))
    
    new_image.paste(img1, (0, 0))
    new_image.paste(img2, (0, img1.height))
    
    output_path = os.path.join(output_dir, image_name)
    new_image.save(output_path)

    print(f"Saved combined image: {output_path}")

print("Image processing complete.")
