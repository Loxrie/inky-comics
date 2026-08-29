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
import json

from comicvine import ComicVine
from blinkenlight import COLORS, show_color

# Run with DEBUG=1 python comic.py to use a mock display for testing without an Inky Impression
DEBUG = os.environ.get("DEBUG") == "1"

logging.basicConfig(
    level=logging.INFO if DEBUG is False else logging.DEBUG,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


class Comic:
    def __init__(
        self,
        config,
    ):
        self.cv = ComicVine(
            config["comicvine"]["api_key"],
            secrets,
            headers={"User-Agent": config["comicvine"]["user_agent"]},
            dedupe=config["dedupe"]["enabled"],
            history_size=config["dedupe"]["history_size"],
            unicorn_pi=config["unicornpi"],
        )

        self.new_comic_file = config["new_comic_file"]
        self.unicorn_pi = config["unicornpi"]
        self.queries = config["comics"]["queries"]
        self.paths = config["paths"]
        self.padding = config["image"].get("padding", False)
        self.processing = config["image"]["processing"]
        self.preset = config["image"]["preset"]
        self.intent = config["image"]["intent"]

        self.server = config["server"]
        self.client = config["client"]

        # Only import these if they will be used.
        # My Pi Zero W can take 1-2 minutes to run these and still crash
        # there's currently no code saying anything like oh shit this image is huge retreat retreat!
        if self.processing is True and self.preset is not None:
            from optimise import Optimise
            from suggestion import Suggestion

            self.suggestion = Suggestion
            self.optimise = Optimise

        # Inky Impression display setup
        if DEBUG is False and self.server["enabled"] is False:
            from inky.auto import auto

            self.inky_display = auto()
        else:
            from mockimpression import MockImpression

            self.inky_display = MockImpression(resolution=(1600, 1200))

    def get_image_from_url(self, image_url, name):
        if self.unicorn_pi:
            show_color(COLORS["PURPLE"])

        # Display image on Inky Impression
        response = requests.get(image_url)
        response.raise_for_status()
        image = Image.open(BytesIO(response.content))
        response.close()
        if self.paths["save"] is not None:
            image.save(f"{self.paths["save"]}/{name}.png")
        return image, name

    def display_image_on_inky(self, image, name):
        if self.unicorn_pi:
            show_color(COLORS["PINK"])

        # Rotate the image if it is taller than it is wide my inky is upside btw, you may want 90.
        if image.height > image.width:
            image = image.rotate(-90, expand=True)

        if self.client["enabled"] is True:
            logging.debug(
                "Client mode enabled, skipping processing converting to palette"
            )
            image = image.convert("P")

        if self.padding is True and self.processing is True and self.preset is not None:
            # We only want to do this to reduce load on processing as the pad function itself
            # does this step and more
            image = ImageOps.contain(
                image, self.inky_display.resolution, Image.Resampling.LANCZOS
            )
        else:
            image = image.resize(self.inky_display.resolution, Image.Resampling.LANCZOS)

        if self.processing is True:
            if self.preset is not None:
                logging.debug(
                    f"Processing image with {self.preset} preset and intent {self.intent}"
                )
                suggestion = self.suggestion(image, intent=self.intent)
                suggestion.suggest(preset=self.preset)
                image = (
                    self.optimise(
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
                logging.debug(
                    "Processing image with quantize and floyd-steinberg dithering"
                )
                image = image.quantize(colors=256, dither=Image.Dither.FLOYDSTEINBERG)

        if self.padding is True:
            logging.debug("Padding image")
            # This is handy, it maintains aspect ration but resizes image and then pads the space left
            # some comics look mighty weird when stretched wide to 3:4
            image = ImageOps.pad(
                image,
                self.inky_display.resolution,
                color="White" if self.preset is None else 1,
                centering=(0.5, 0.5),
            )

        if self.unicorn_pi:
            show_color(COLORS["HOTPINK"])

        if self.server["enabled"] is False:
            self.inky_display.set_image(
                image, saturation=0.5 if self.processing is False else 0
            )
            logging.info("Updating Inky Impression!")
            self.inky_display.show()
        elif self.server["enabled"] is True and DEBUG is False:
            logging.info("Uploading file to frame")
            image.save(f"{self.paths["cache"]}/{name}.png")
            subprocess.run(
                [
                    "scp",
                    f"{self.paths["cache"]}/{name}.png",
                    f"{self.server["client_pi"]}:{self.paths["upload"]}",
                ]
            )
            cmd_line = (
                f'echo "{self.paths["upload"]}/{name}.png"> "{self.new_comic_file}"'
            )
            subprocess.run(["ssh", self.server["client_pi"], cmd_line])

        if self.unicorn_pi:
            show_color(COLORS["OFF"])

    def displayComic(self):
        try:
            if self.unicorn_pi:
                show_color(COLORS["GREEN"])
            comic_image_url = None
            random_comic_url = None

            # Pick a random search term from the list
            query = secrets.choice(self.queries)
            logging.info(f"Chose type {query["type"]} query {query["query"]}")

            result = self.cv.build_tasklist(
                query["type"], query["query"], query.get("random", None)
            ).run()

            logging.info(f"Will open : {result["image_url"]}")
            if self.unicorn_pi:
                show_color(COLORS["PURPLE"])
            image, name = self.get_image_from_url(
                result["image_url"], result["image_name"]
            )
            self.display_image_on_inky(image, name)

        except Exception as e:
            logging.exception(e)
            raise

    def displayPoster(self, file):
        try:
            name = pathlib.Path(file).stem
            self.display_image_on_inky(Image.open(file), f"{name}_processed")
        except Exception as e:
            logging.exception(e)
            raise


if __name__ == "__main__":
    with open("settings.json", "r") as file:
        configuration = json.load(file)
    c = Comic(configuration)

    ncp = configuration["new_comic_file"]
    if len(sys.argv) > 1:
        poster = sys.argv[1]
        c.displayPoster(poster)
    elif os.path.isfile(ncp):
        if os.path.getsize(ncp) == 0:
            displayComic()
        else:
            with open(ncp, "r") as file:
                poster = file.read().rstrip()
                c.displayPoster(poster)
        os.remove()
    else:
        c.displayComic()
