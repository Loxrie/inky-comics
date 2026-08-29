#!/usr/bin/env python3
import os
import comic
import gpiod
import gpiodevice
import time
import RPi.GPIO as GPIO

import json

SW_A = 5
SW_B = 6
SW_C = 25  # Set this value to '25' if you're using a Impression 13.3"
SW_D = 24

BUTTONS = [SW_A, SW_B, SW_C, SW_D]

LABELS = ["A", "B", "C", "D"]

GPIO.setmode(GPIO.BCM)

GPIO.setup(BUTTONS, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def handle_button(pin):
    time.sleep(0.02)
    if GPIO.input(pin) == GPIO.LOW:
        if pin == SW_A or pin == SW_D:
            comic.displayComic()


for button in BUTTONS:
    GPIO.add_event_detect(button, GPIO.FALLING, callback=handle_button, bouncetime=250)

configuration_mtime = 0
SETTINGS = "settings.json"

try:
    while True:
        mtime = os.stat(SETTINGS).st_mtime
        if mtime != configuration_mtime:
            configuration_mtime = mtime
            with open(SETTINGS, "r") as file:
                configuration = json.load(file)
                c = Comic(configuration)

        new_comic_file = configuration["new_comic_file"]
        if os.path.isfile(new_comic_file):
            print("Found new comic file.")
            if os.path.getsize(new_comic_file) == 0:
                c.displayComic()
            else:
                with open(new_comic_file, "r") as file:
                    poster = file.read().rstrip()
                    c.displayPoster(poster)
            os.remove(new_comic_file)
        time.sleep(0.5)
except KeyboardInterrupt:
    GPIO.cleanup()
