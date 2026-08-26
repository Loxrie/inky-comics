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
import subprocess
import pathlib

from comicvine import ComicVine
from blinkenlight import COLORS, show_color

# Run with DEBUG=1 python comic.py to use a mock display for testing without an Inky Impression
DEBUG = os.environ.get("DEBUG") == "1"

# Settings
from settings import (
    API_KEY,
    DEDUPE,
    CACHE_PATH,
    CLIENT_MODE,
    CLIENT_PI,
    HEADERS,
    HISTORY_SIZE,
    NEW_COMIC_PLEASE,
    PAD_IMAGE,
    PROCESS_IMAGE,
    PROCESS_IMAGE_INTENT,
    PROCESS_IMAGE_PRESET,
    RANDOM_VOLUME,
    SAVE_PATH,
    SEARCH_QUERIES,
    SERVER_MODE,
)

# Run with DEBUG=1 python comic.py to use a mock display for testing without an Inky Impression
DEBUG = os.environ.get("DEBUG") == "1"

logging.basicConfig(
    level=logging.INFO if DEBUG is False else logging.DEBUG,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Only import these if they will be used.
# My Pi Zero W can take 1-2 minutes to run these and still crash
# there's currently no code saying anything like oh shit this image is huge retreat retreat!
if PROCESS_IMAGE is True and PROCESS_IMAGE_PRESET is not None:
    from optimise import Optimise
    from suggestion import Suggestion

# Inky Impression display setup
if DEBUG is False and SERVER_MODE is False:
    from inky.auto import auto

    inky_display = auto()
else:
    from mockimpression import MockImpression

    inky_display = MockImpression(resolution=(1600, 1200))

cv = ComicVine(API_KEY, secrets, headers=HEADERS, dedupe=DEDUPE, history_size=HISTORY_SIZE)


def get_image_from_url(image_url, name):
    show_color(COLORS["PURPLE"])
    # Display image on Inky Impression
    response = requests.get(image_url)
    response.raise_for_status()
    image = Image.open(BytesIO(response.content))
    response.close()
    if SAVE_PATH is not None:
        image.save(f"{SAVE_PATH}/{name}.png")
    return image, name


def display_image_on_inky(image, name):
    show_color(COLORS["PINK"])
    # Rotate the image if it is taller than it is wide my inky is upside btw, you may want 90.
    if image.height > image.width:
        image = image.rotate(-90, expand=True)

    if CLIENT_MODE is True:
        logging.info("Client mode enabled, skipping processing converting to palette")
        image = image.convert("P")

    if (
        PAD_IMAGE is True
        and PROCESS_IMAGE is True
        and PROCESS_IMAGE_PRESET is not None
    ):
        # We only want to do this to reduce load on processing as the pad function itself
        # does this step and more
        image = ImageOps.contain(
            image, inky_display.resolution, Image.Resampling.LANCZOS
        )
    elif PAD_IMAGE is False:
        image = image.resize(inky_display.resolution, Image.Resampling.LANCZOS)

    if PROCESS_IMAGE is True:
        if PROCESS_IMAGE_PRESET is not None:
            logging.info(
                f"Processing image with {PROCESS_IMAGE_PRESET} preset and intent {PROCESS_IMAGE_INTENT}"
            )
            suggestion = Suggestion(image, intent=PROCESS_IMAGE_INTENT)
            suggestion.suggest(preset=PROCESS_IMAGE_PRESET)
            image = (
                Optimise(
                    {
                        "imageAdjustmentOptions": {
                            "toneMapping": suggestion.tone_mapping(),
                            "dynamicRangeCompression": suggestion.dynamic_range_compression(),
                        },
                    }
                )
                .load(image)
                .apply_image_adjustments()
                .dither_canvas()
                .colour_mapping()
                .get_image()
            )
        else:
            logging.info(
                "Processing image with quantize and floyd-steinberg dithering"
            )
            image = image.quantize(colors=256, dither=Image.Dither.FLOYDSTEINBERG)

    if PAD_IMAGE is True:
        logging.info("Padding image")
        # This is handy, it maintains aspect ration but resizes image and then pads the space left
        # some comics look mighty weird when stretched wide to 3:4
        image = ImageOps.pad(
            image,
            inky_display.resolution,
            color="White" if PROCESS_IMAGE_PRESET is None else 1,
            centering=(0.5, 0.5),
        )

    show_color(COLORS["HOTPINK"])

    if SERVER_MODE is False:
        inky_display.set_image(image, saturation=0.5 if PROCESS_IMAGE is False else 0)
        logging.info("Updating Inky Impression!")
        inky_display.show()
    elif SERVER_MODE is True and DEBUG is False:
        logging.info("Uploading file to frame")
        image.save(f"{CACHE_PATH}/{name}.png")
        subprocess.run(
            ["scp", f"{CACHE_PATH}/{name}.png", "inkyframe.local:~/Pictures/Upload"]
        )
        cmd_line = (
            f'echo "/home/diziet/Pictures/Upload/{name}.png" '
            '> "/home/diziet/inkyimpression6/comics/.new.comic.please"'
        )
        subprocess.run(["ssh", "inkyframe.local", cmd_line])

    show_color(COLORS["OFF"])


def displayComic():
    try:
        show_color(COLORS["GREEN"])
        comic_image_url = None
        random_comic_url = None

        # Pick a random search term from the list
        search_type, search_query = secrets.choice(SEARCH_QUERIES)
        logging.info(f"Chose type {search_type} query {search_query}")

        comic_image_url, image_name = cv.build_tasklist(search_type, search_query, RANDOM_VOLUME.get(search_query, None)).run()

        logging.info(f"Will open : {comic_image_url}")
        show_color(COLORS["PURPLE"])
        image, name = get_image_from_url(comic_image_url, image_name)
        display_image_on_inky(image, name)

    except Exception as e:
        logging.exception(e)
        raise


def displayPoster(file):
    try:
        name = pathlib.Path(file).stem
        display_image_on_inky(Image.open(file), f"{name}_processed")
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
