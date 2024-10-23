# This scripts simply merges two images with matching names among two different folders.
# The two input direcotires paths must be set manually.
# One image goes on top of the other, trimming whitespace.
import os
from PIL import Image, ImageChops, ImageOps

def trim_whitespace(image):
    gray_image = image.convert("L")
    
    inverted_image = ImageOps.invert(gray_image)
    
    bbox = inverted_image.getbbox()
    
    if bbox:
        return image.crop(bbox)
    return image

dir1 = './nightly4624/histograms/'
dir2 = './SCI7/histograms/'
output_dir = 'compare_density'

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

images1 = set(os.listdir(dir1))
images2 = set(os.listdir(dir2))

matching_images = images1.intersection(images2)

for image_name in matching_images:
    img1_path = os.path.join(dir1, image_name)
    img2_path = os.path.join(dir2, image_name)
    
    img1 = Image.open(img1_path)
    img2 = Image.open(img2_path)
    
    img1 = trim_whitespace(img1)
    img2 = trim_whitespace(img2)
    
    if img1.width != img2.width:
        print(f"Warning: Skipping {image_name} because the images do not have the same width")
        continue
    
    new_width = img1.width
    new_height = img1.height + img2.height
    
    new_image = Image.new('RGB', (new_width, new_height))
    
    new_image.paste(img1, (0, 0))
    new_image.paste(img2, (0, img1.height))
    
    output_path = os.path.join(output_dir, image_name)
    new_image.save(output_path)

    print(f"Saved combined image: {output_path}")
