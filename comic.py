"""
Python script to fetch a randomised comic cover from the Comic Vine API and show it on an Inky Impression display.
You will need to sign up for an API key at https://comicvine.gamespot.com/api/ to use this script.
"""

import requests
import logging
import secrets
from io import BytesIO
from PIL import Image, ImageOps
import os
import sys

from comicvine import ComicVine

# Run with DEBUG=1 python comic.py to use a mock display for testing without an Inky Impression
DEBUG = os.environ.get("DEBUG") == "1"

# Settings
from settings import (
    API_KEY,
    DEDUPE,
    HEADERS,
    HISTORY_SIZE,
    NEW_COMIC_PLEASE,
    PAD_IMAGE,
    PROCESS_IMAGE,
    RANDOM_VOLUME,
    SAVE_PATH,
    SEARCH_QUERIES,
)

logging.basicConfig(
    level=logging.INFO if DEBUG is False else logging.DEBUG,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Inky Impression display setup
if DEBUG is False:
    from inky.auto import auto

    inky_display = auto()
else:
    logging.debug("Mocking inky")
    from mockimpression import MockImpression

    inky_display = MockImpression(resolution=(1600, 1200))

cv = ComicVine(API_KEY, secrets, headers=HEADERS, dedupe=DEDUPE, history_size=HISTORY_SIZE)


def get_image_from_url(image_url, name):
    # Display image on Inky Impression
    response = requests.get(image_url)
    response.raise_for_status()
    image = Image.open(BytesIO(response.content))
    response.close()
    if SAVE_PATH is not None:
        image.save(f"{SAVE_PATH}/{name}.png")
    return image, name


def display_image_on_inky(image, name):
    # Rotate the image if it is taller than it is wide my inky is upside btw, you may want 90.
    if image.height > image.width:
        image = image.rotate(-90, expand=True)

    if PROCESS_IMAGE is True:
        logging.info("Processing image with quantize and floyd-steinberg dithering")
        # Without conver RGB the image becomes mode P, in mode P inky doesn't attempt
        # to enhance the image further (e.g. ignores saturation), try without convert('RGB')
        # for personal preference
        image = image.quantize(colors=256, dither=Image.Dither.FLOYDSTEINBERG).convert(
            "RGB"
        )

    if PAD_IMAGE is True:
        logging.info("Padding image")
        # This is handy, it maintains aspect ration but resizes image and then pads the space left
        # some comics look mighty weird when stretched wide to 3:4
        image = ImageOps.pad(
            image,
            inky_display.resolution,
            color="White",
            centering=(0.5, 0.5),
        )

    inky_display.set_image(image, saturation=0.5)
    logging.info("Updating Inky Impression!")
    inky_display.show()


def displayComic():
    try:
        comic_image_url = None
        random_comic_url = None

        # Pick a random search term from the list
        search_type, search_query = secrets.choice(SEARCH_QUERIES)
        logging.info(f"Chose type {search_type} query {search_query}")

        comic_image_url, image_name = cv.build_tasklist(search_type, search_query, RANDOM_VOLUME.get(search_query, None)).run()

        logging.info(f"Will open : {comic_image_url}")
        image, name = get_image_from_url(comic_image_url, image_name)
        display_image_on_inky(image, name)


        # if search_type == "Volume":
        #     volume_detail_url = cv.get_random_volume_url(
        #         search_query, RANDOM_VOLUME[search_query]
        #     )
        #     random_comic_url = cv.get_random_comic_url(volume_detail_url)

        # elif search_type == "Character":
        #     character_url = cv.get_character_url(search_query)
        #     random_comic_url = cv.get_random_character_appearance_url(character_url)

        # if random_comic_url is not None:
        #     comic_image_url, image_name = cv.get_random_image_url(random_comic_url)
        #     logging.info(f"Would open : {comic_image_url}")
        #     image, name = get_image_from_url(comic_image_url, image_name)
        #     display_image_on_inky(image, name)

    except Exception as e:
        logging.exception(e)
        raise


def displayPoster(file):
    try:
        display_image_on_inky(Image.open(file))
    except Exception as e:
        logging.exception(e)
        raise


if __name__ == "__main__":
    if len(sys.argv) > 1:
        poster = sys.argv[1]
        displayPoster(poster)
    elif os.path.isfile(NEW_COMIC_PLEASE):
        if os.path.getsize(NEW_COMIC_PLEASE) == 0:
            displayComic()
        else:
            with open(NEW_COMIC_PLEASE, "r") as file:
                poster = file.read().rstrip()
                displayPoster(poster)
        os.remove(NEW_COMIC_PLEASE)
    else:
        displayComic()
