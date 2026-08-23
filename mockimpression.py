import logging
import numpy
from PIL import Image

DESATURATED_PALETTE = [
    [0, 0, 0],
    [255, 255, 255],
    [0, 255, 0],
    [0, 0, 255],
    [255, 0, 0],
    [255, 255, 0],
    [255, 140, 0],
    [255, 255, 255],
]

SATURATED_PALETTE = [
    [57, 48, 57],
    [255, 255, 255],
    [58, 91, 70],
    [61, 59, 94],
    [156, 72, 75],
    [208, 190, 71],
    [177, 106, 73],
    [255, 255, 255],
]


class MockImpression:
    def __init__(self, resolution):
        self.resolution = resolution
        self.image = None

    def set_image(self, image, saturation=0.5):
        # If quantize is used then image mode is P
        # If mode is P then set_image in inky skips this process, otherwise you get a very dark png
        if image.mode != "P":
            logging.info("Image is not in mode P, emulating Inky behaviour")
            saturation = float(0.5)
            palette = []
            for i in range(7):
                rs, gs, bs = [c * saturation for c in SATURATED_PALETTE[i]]
                rd, gd, bd = [c * (1.0 - saturation) for c in DESATURATED_PALETTE[i]]
                palette += [int(rs + rd), int(gs + gd), int(bs + bd)]
            palette += [255, 255, 255]
            palette_image = Image.new("P", (1, 1))
            palette_image.putpalette(palette + [0, 0, 0] * 248)
            image_core = image.im.convert("P", True, palette_image.im)
            self.image = Image.new("P", image.size)
            self.image.putpalette(palette_image.getpalette())
            self.image.putdata(image_core)
        else:
            logging.info("Image is already in mode P, skipping palette conversion")
            self.image = image

    def show(self):
        if self.image is not None:
            self.image.convert("RGB").rotate(90, expand=True).save(
                "debug_output_default.png"
            )
        else:
            logging.warning("No image set to display on mock Inky Impression")
