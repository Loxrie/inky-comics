"""
Python script to fetch a randomised comic cover from the Comic Vine API and show it on an Inky Impression display.
You will need to sign up for an API key at https://comicvine.gamespot.com/api/ to use this script.
Change the search query to the comic series you want to display!
"""

import logging
import random
from io import BytesIO
import requests
from PIL import Image
import os
import sys

from slugify import slugify

DEBUG = os.environ.get("DEBUG") == "1"

# Settings
from settings import (
    SEARCH_QUERIES,
    RANDOM_VOLUME,
    SAVE_PATH,
    API_KEY,
    BASE_URL,
    HEADERS,
    NEW_COMIC_PLEASE,
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


def find_volume_id(api_key, query):
    # Our first API call finds a list of volumes that match the search query, and then picks one
    params = {
        "api_key": api_key,
        "format": "json",
        "query": query,
        "resources": "volume",
        "limit": 10 if RANDOM_VOLUME[query] else 1,
    }
    response = requests.get(f"{BASE_URL}search/", headers=HEADERS, params=params)
    response.raise_for_status()
    data = response.json()
    response.close()
    results = data.get("results", [])
    if results:
        for idx, volume in enumerate(results, 1):
            logging.info(
                f"{idx}: {volume['name']} (ID: {volume['id']}, Start Year: {volume.get('start_year', 'N/A')})"
            )

        if RANDOM_VOLUME[query] is True:
            # Pick a random volume from the search results
            chosen = random.choice(results)
            logging.info(
                f"Randomly selected: {chosen['name']} (ID: {chosen['id']}) {chosen['api_detail_url']}"
            )
        else:
            # Pick the first volume from the search results
            chosen = results[0]
            logging.info(
                f"Picked first result: {chosen['name']} (ID: {chosen['id']}) {chosen['api_detail_url']}"
            )
        return chosen["api_detail_url"]
    else:
        raise ValueError(f"No volumes found for {query}.")


def get_character_url(api_key, query):
    # Our first API call finds a list of volumes that match the search query, and then picks one
    params = {
        "api_key": api_key,
        "format": "json",
        "filter": f"name:{query}",
        "field_list": "name,api_detail_url,count_of_issue_appearances",
        "sort": "count_of_issue_appearances:desc",
        "limit": 100,
    }
    response = requests.get(f"{BASE_URL}characters/", headers=HEADERS, params=params)
    response.raise_for_status()
    data = response.json()
    response.close()
    results = data.get("results", [])
    if results:
        chosen = results[0]
        logging.info(
            f"Chosen {chosen['name']} appeared in {chosen['count_of_issue_appearances']} comics"
        )
        return chosen["api_detail_url"]
    else:
        raise ValueError(f"No character url found for {query}.")


def get_random_character_appearance(api_key, api_detail_url):
    # Takes a character detail url from a characters search and extracts a random issue they appeared in
    params = {
        "api_key": api_key,
        "format": "json",
        "field_list": "name,volume,issue_credits",
        "limit": 100,
    }
    response = requests.get(api_detail_url, headers=HEADERS, params=params)
    response.raise_for_status()
    data = response.json()
    response.close()
    results = data.get("results", {})
    if results:
        chosen = random.choice(results["issue_credits"])
        logging.info(f"Chose issue {chosen['name']}")
        return chosen["api_detail_url"]
    else:
        raise ValueError(f"No character url found for {query}.")


def get_random_comic(api_key, volume_detail_url):
    # Once we know the volume ID we can do a second API call to fetch a list of issues and pick a random cover image
    params = {"api_key": api_key, "format": "json"}
    response = requests.get(volume_detail_url, headers=HEADERS, params=params)
    response.raise_for_status()
    data = response.json()
    response.close()
    results = data.get("results", [])
    if results:
        issue = random.choice(results["issues"])
        logging.info(
            f"Chose issue {issue['issue_number']} out of {len(results['issues'])}"
        )
        return issue["api_detail_url"]
    else:
        raise ValueError("No comic issues found for the specified series.")


def get_random_comic_image(api_key, comic_url):
    # Once we know the volume ID we can do a second API call to fetch a list of issues and pick a random cover image
    params = {"api_key": api_key, "format": "json"}
    response = requests.get(f"{comic_url}", headers=HEADERS, params=params)
    response.raise_for_status()
    data = response.json()
    response.close()
    issue = data.get("results", [])
    if issue:
        # print a link to the issue page on Comic Vine
        images = [issue["image"]["original_url"]] + [
            image["original_url"] for image in issue["associated_images"]
        ]
        logging.info(f"Random image selected from a choice of {len(images)}")
        logging.info(f"Find out more: {issue['site_detail_url']}")
        image_link = random.choice(images)
        image_name = slugify(
            f"{issue['volume']['name']} {issue['name']} {issue['issue_number']}_{issue['id']}",
            allow_unicode=True,
            separator=" ",
        )
        return image_link, image_name
    else:
        raise ValueError("No comic issues found for the specified series.")


def get_image_from_url(image_url, name):
    # Display image on Inky Impression
    response = requests.get(image_url)
    response.raise_for_status()
    image = Image.open(BytesIO(response.content))
    response.close()
    if SAVE_PATH is not None:
        image.save(f"{SAVE_PATH}/{name}.png")
    return image


def display_image_on_inky(image):
    # Rotate the image if it is taller than it is wide
    if image.height > image.width:
        image = image.rotate(-90, expand=True)

    image = image.resize(inky_display.resolution)
    inky_display.set_image(image, saturation=0.5)
    logging.info("Updating Inky Impression!")
    inky_display.show()


def displayComic():
    try:
        # Seed RNG
        random.seed(None, version=2)
        # Pick a random search term from the list
        search_type, search_query = random.choice(SEARCH_QUERIES)
        logging.info(f"Chose type {search_type} query {search_query}")
        comic_image_url = None
        image_name = None
        if search_type == "Volume":
            volume_detail_url = find_volume_id(API_KEY, search_query)
            random_comic_url = get_random_comic(API_KEY, volume_detail_url)
            comic_image_url, comic_name = get_random_comic_image(
                API_KEY, random_comic_url
            )
        elif search_type == "Character":
            character_url = get_character_url(API_KEY, search_query)
            random_comic_url = get_random_character_appearance(API_KEY, character_url)
            comic_image_url, image_name = get_random_comic_image(
                API_KEY, random_comic_url
            )
        if comic_image_url is not None:
            logging.info(f"Would open : {comic_image_url}")
            image = get_image_from_url(comic_image_url, image_name)
            display_image_on_inky(image)
    except Exception as e:
        logging.exception(e)
        raise


def displayPoster(file):
    try:
        if DEBUG is False:
            display_image_on_inky(Image.open(file))
    except Exception as e:
        logging(f"Error: {e}")


if __name__ == "__main__":
    if os.path.isfile(NEW_COMIC_PLEASE):
        if os.path.getsize(NEW_COMIC_PLEASE) == 0:
            displayComic()
        else:
            with open(NEW_COMIC_PLEASE, "r") as file:
                poster = file.read().rstrip()
                displayPoster(poster)
        os.remove(NEW_COMIC_PLEASE)
    else:
        displayComic()
