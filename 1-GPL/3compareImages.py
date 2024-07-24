import os
from PIL import Image, ImageDraw, ImageFont

# input files comes from the 2callRudy + 3copyRUDYresults


def get_subdirectories(a_dir):
    return [os.path.join(a_dir, name) for name in os.listdir(a_dir)
            if os.path.isdir(os.path.join(a_dir, name))]

def find_matching_files(dir_paths):
    file_sets = [set(filter(lambda f: f.endswith('.png'), os.listdir(path))) for path in dir_paths]
    matching_files = set.intersection(*file_sets)
    return matching_files

def create_title_image(title, width, height, font_size=100, background_color="black", text_color="white"):
    """Create an image."""
    title_height = font_size + 10
    title_image = Image.new("RGB", (width, title_height), color=background_color)
    draw = ImageDraw.Draw(title_image)

    font = ImageFont.truetype("/usr/share/fonts/truetype/freefont/FreeMono.ttf", font_size)
    text_width, text_height = draw.textsize(title, font=font)
    text_x = (width - text_width) // 2
    text_y = (title_height - text_height) // 2

    draw.text((text_x, text_y), title, fill=text_color, font=font, antialias=True)

    return title_image


def combine_images(dir_paths, filenames, output_dir, cut_height=50):
    for filename in filenames:
        images = [Image.open(os.path.join(path, filename)) for path in dir_paths]
        total_width = sum(im.width for im in images)
        new_im = Image.new('RGB', (total_width, images[0].height - cut_height))

        x_offset = 0

        for i, im in enumerate(images):
            title = os.path.basename(dir_paths[i])
            title_im = create_title_image(title, im.width, cut_height)

            cut_box = (0, cut_height, im.width, im.height)
            im = im.crop(cut_box)

            new_im.paste(title_im, (x_offset, 0))
            new_im.paste(im, (x_offset, title_im.height))
            x_offset += im.width

        new_im.save(os.path.join(output_dir, 'combined_' + filename))


current_directory = os.getcwd()
subdirectories = get_subdirectories(current_directory)
matching_files = find_matching_files(subdirectories)
combine_images(subdirectories, matching_files, current_directory)
