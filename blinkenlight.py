# See https://github.com/Loxrie/unicorn-daemon for context
import json

COLORS = {
    "GREEN":    (33, 127, 57),
    "TEAL":     (35, 187, 173),
    "TURQUOISE": (37, 217, 200),
    "BLUE":     (42, 190, 217),
    "PURPLE":   (128, 33, 104),
    "PINK":     (255, 109, 162),
    "HOTPINK":  (249, 38, 114),
    "OFF":      (0, 0, 0),
}

from settings import UNICORN_MODE


def show_color(color: (int, int, int)):
    if UNICORN_MODE is not True:
        return

    width = height = 8
    PIPE_PATH = "/tmp/unicornhat.pipe"

    def show(data):
        with open(PIPE_PATH, "w") as pipe:
            pipe.write(json.dumps(data) + "\n")
            pipe.flush()

    data = []
    for y in range(height):
        for x in range(width):
            data.append(((x, y), color))
    show(data)
