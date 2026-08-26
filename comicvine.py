import requests
import logging
import hashlib
from collections import deque
import pickle
from os import path

from slugify import slugify

from blinkenlight import COLORS, show_color


class ComicCollisionError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class ComicVine:
    def __init__(
        self,
        api_key,
        random,
        base_url="https://comicvine.gamespot.com/api/",
        headers={"User-Agent": "Python Comic Vine Random Image Client"},
        dedupe=False,
        history_size=122,
    ):
        self.api_key = api_key
        self.random = random
        self.base_url = base_url
        self.headers = headers

        self.dedupe = dedupe
        self.call_map = []

        if self.dedupe is True:
            self.seen = deque(maxlen=history_size)
            self.task_list = deque()
            self.query = None
            self.last_chance = False
            self.bummer = None
            if path.isfile("seen_comics.pickle"):
                with open("seen_comics.pickle", "rb") as f:
                    self.seen = pickle.load(f)
                    # Need to grow and shrink here if history_size differs from len
                    if history_size != self.seen.maxlen:
                        old_max = self.seen.maxlen
                        self.seen = deque(self.seen, maxlen=history_size)
                        logging.warn(
                            f"Reconfigured seen list from {old_max} to maxlen of {history_size}"
                        )

    def build_tasklist(self, *args):
        self.reset()
        search_type = args[0]
        self.query = args[1:]
        print(f"Building tasklist {search_type} with query {self.query}")
        if search_type == "Volume":
            self.task_list.append(self.get_random_volume_url)
            self.task_list.append(self.get_random_comic_url)
        else:
            self.task_list.append(self.get_character_url)
            self.task_list.append(self.get_random_character_appearance_url)
        self.task_list.append(self.get_random_image_url)

        return self

    def run(self):
        try:
            while self.task_list:
                task = self.task_list.popleft()
                logging.debug(f"Calling {task} with {self.query}")
                self.query = task(*self.query)
        except ComicCollisionError as ce:
            if self.last_chance is not True:
                history = self.rewind()
                self.reset()
                [self.task_list.append(e[0]) for e in history]
                self.query = history[0][2]
                self.last_chance = True
                logging.debug(
                    f"Rerunning {self.task_list} with initial query {self.query}"
                )
            else:
                return self.bummer

        if self.last_chance is True and self.task_list:
            self.query = self.run()

        return self.query

    def reset(self):
        self.task_list.clear()
        self.call_map.clear()
        self.query = None
        self.last_chance = False

    def get_hash(self, item: str) -> str:
        return hashlib.sha256(item.encode()).hexdigest()

    def add_hash(self, hash: str):
        self.seen.append(hash)
        with open("seen_comics.pickle", "wb") as f:
            pickle.dump(self.seen, f, pickle.HIGHEST_PROTOCOL)

    def rewind(self) -> str or bool:
        for call in reversed(self.call_map):
            function, choices, query = call
            if choices > 2:
                call_index = [
                    i for i, call in enumerate(self.call_map) if call[0] == function
                ][0]
                return self.call_map[call_index:]

    def set_random(self, rng):
        self.random = rng

    # Get 100 volumes (max) matching name and return a random api detail url from it
    def get_random_volume_url(self, *args) -> str:
        show_color(COLORS["TEAL"])
        query, random_volume, *discard = args
        self.call_map = []
        params = {
            "api_key": self.api_key,
            "format": "json",
            "field_list": "name,id,api_detail_url,start_year,count_of_issues",
            "filter": f"name:{query}",
            "limit": 100,
        }
        response = requests.get(
            f"{self.base_url}volumes/", headers=self.headers, params=params
        )
        response.raise_for_status()
        data = response.json()
        response.close()
        results = data.get("results", [])
        results.sort(key=lambda x: x["count_of_issues"], reverse=True)
        if results:
            for idx, volume in enumerate(results, 1):
                logging.info(
                    f"{idx}: {volume['name']} (ID: {volume['id']}, Start Year: {volume.get('start_year', 'N/A')})"
                )

            if random_volume is True:
                # Pick a random volume from the search results
                chosen = self.random.choice(results)
                api_detail_url = chosen["api_detail_url"]
                self.call_map.append((self.get_random_volume_url, len(results), args))
                logging.info(
                    f"Randomly selected: {chosen['name']} (ID: {chosen['id']}) {api_detail_url}"
                )
            else:
                # Pick the first volume from the search results
                chosen = results[0]
                logging.info(
                    f"Picked first result: {chosen['name']} (ID: {chosen['id']}) {chosen['api_detail_url']}"
                )
            return (chosen["api_detail_url"],)
        else:
            raise ValueError(f"No volumes found for {query}.")

    # Find all characters matching name, sort by how many comics they've appeared in (descending)
    # and return the api url for more detail from the most popular one
    def get_character_url(self, *args) -> str:
        show_color(COLORS["TEAL"])
        query, *discard = args
        logging.debug(args)
        logging.debug(query)
        self.call_map = []
        params = {
            "api_key": self.api_key,
            "format": "json",
            "filter": f"name:{query}",
            "field_list": "name,api_detail_url,count_of_issue_appearances",
            "limit": 100,
        }
        response = requests.get(
            f"{self.base_url}characters/", headers=self.headers, params=params
        )
        response.raise_for_status()
        data = response.json()
        response.close()
        results = data.get("results", [])
        results.sort(key=lambda x: x["count_of_issue_appearances"], reverse=True)
        if results:
            chosen = results[0]
            logging.info(
                f"Chosen {chosen['name']} appeared in {chosen['count_of_issue_appearances']} comics"
            )
            return (chosen["api_detail_url"],)
        else:
            raise ValueError(f"No character url found for {query}.")

    # Use the api detail url from above and return a random comic api url from all the comics they appeared in
    def get_random_character_appearance_url(self, *args) -> str:
        show_color(COLORS["TURQOISE"])
        api_detail_url, *discard = args
        params = {
            "api_key": self.api_key,
            "format": "json",
            "field_list": "name,volume,issue_credits",
            "limit": 100,
        }
        response = requests.get(api_detail_url, headers=self.headers, params=params)
        response.raise_for_status()
        data = response.json()
        response.close()
        results = data.get("results", {})
        if results:
            chosen = self.random.choice(results["issue_credits"])
            num_issue_credits = len(results["issue_credits"])
            api_detail_url = chosen["api_detail_url"]
            self.call_map.append(
                (self.get_random_character_appearance_url, num_issue_credits, args)
            )
            logging.info(
                f"Chose issue {chosen['site_detail_url']} out of {num_issue_credits} appearances"
            )
            return (api_detail_url,)
        else:
            raise ValueError(f"No character url found for {query}.")

    # Use the api detail url from /volumes and return a random comic api url from all its comics
    def get_random_comic_url(self, *args) -> str:
        show_color(COLORS["TURQOISE"])
        volume_detail_url, *discard = args
        params = {"api_key": self.api_key, "format": "json"}
        response = requests.get(volume_detail_url, headers=self.headers, params=params)
        response.raise_for_status()
        data = response.json()
        response.close()
        results = data.get("results", [])
        if results:
            issue = self.random.choice(results["issues"])
            num_issues = len(results["issues"])
            api_detail_url = issue["api_detail_url"]
            self.call_map.append((self.get_random_comic_url, num_issues, args))
            logging.info(f"Chose issue {issue['issue_number']} out of {num_issues}")
            return (api_detail_url,)
        else:
            raise ValueError("No comic issues found for the specified series.")

    # So both routes (/volumes and /characters) lead here.  Get the detail about the issue
    # collate both the original cover and any special covers and pick a random image
    # Returns the image url and a potential resource name to save
    def get_random_image_url(self, *args) -> (str, str):
        show_color(COLORS["BLUE"])
        logging.debug(f"get_random_image_url {args}")
        comic_url, *discard = args
        # Once we know the volume ID we can do a second API call to fetch a list of issues and pick a random cover image
        params = {"api_key": self.api_key, "format": "json"}
        response = requests.get(f"{comic_url}", headers=self.headers, params=params)
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
            image_link = self.random.choice(images)
            image_name = slugify(
                f"{issue['volume']['name']} {issue['name']} {issue['issue_number']}_{issue['id']}",
                allow_unicode=True,
                separator=" ",
            )

            self.call_map.append((self.get_random_image_url, len(images), args))

            logging.debug(f"Decision tree {self.call_map}")

            if self.dedupe is True:
                issue_hash = self.get_hash(image_link)
                if issue_hash in self.seen:
                    self.bummer = (image_link, image_name)
                    if self.last_chance is True:
                        logging.info("Dedupe comic: Failure - returning original")
                    raise ComicCollisionError(f"Comic collision on {image_link}")
                else:
                    self.add_hash(issue_hash)

            if self.last_chance is True:
                logging.info("Dedupe comic: Success")
            return image_link, image_name
        else:
            raise ValueError("No comic issues found for the specified series.")
