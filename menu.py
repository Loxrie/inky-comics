#!/usr/bin/env python3
import os
import comic
import gpiod
import gpiodevice
import time
import RPi.GPIO as GPIO

from settings import NEW_COMIC_PLEASE

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

try:
    while True:
        if os.path.isfile(NEW_COMIC_PLEASE):
            print("Found new comic file.")
            if os.path.getsize(NEW_COMIC_PLEASE) == 0:
                comic.displayComic()
            else:
                with open(NEW_COMIC_PLEASE, "r") as file:
                    poster = file.read().rstrip()
                    comic.displayPoster(poster)
            os.remove(NEW_COMIC_PLEASE)
        time.sleep(0.5)
except KeyboardInterrupt:
    GPIO.cleanup()
