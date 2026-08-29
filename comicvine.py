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
        unicorn_pi=False,
    ):
        self.unicorn_pi = unicorn_pi
        self.api_key = api_key
        self.random = random
        self.base_url = base_url
        self.headers = headers

        self.dedupe = dedupe
        self.call_map = []

        if self.dedupe is True:
            self.seen = deque(maxlen=history_size)
            self.task_list = deque()
            self.last_call_result = None
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
        print(f"Building tasklist {search_type} with query {args}")
        if search_type == "Volume":
            search_params = {
                "query": args[1],
                "field_list": "id,name,api_detail_url,start_year,count_of_issues",
                "endpoint": "volumes",
                "random_choice": args[2],
                "sort_field": "count_of_issues",
                "logging_fields": ["id", "name", "start_year", "count_of_issues"],
                "log_results": True,
            }
            self.task_list.append((self.search, search_params))
            comic_params = {
                "field_name": "issues",
                "field_list": "id,name,api_detail_url,site_detail_url,issues",
                "logging_fields": ["id", "name", "site_detail_url"],
            }
            self.task_list.append((self.get_random_comic_url, comic_params))
        elif search_type == "Person":
            search_params = {
                "query": args[1],
                "field_list": "id,name,api_detail_url,site_detail_url",
                "endpoint": "people",
            }
            self.task_list.append((self.search, search_params))
            comic_params = {
                "field_name": "issues",
                "field_list": "id,name,issues,count_of_issues,site_detail_url",
                "logging_fields": ["id", "name", "site_detail_url"],
            }
            self.task_list.append((self.get_random_comic_url, comic_params))
        elif search_type == "Character":
            search_params = {
                "query": args[1],
                "field_list": "id,name,api_detail_url,site_detail_url",
                "endpoint": "characters",
            }
            self.task_list.append((self.search, search_params))
            comic_params = {
                "field_name": "issue_credits",
                "field_list": "id,name,volume,issue_credits",
                "logging_fields": ["id", "name", "site_detail_url"],
            }
            self.task_list.append((self.get_random_comic_url, comic_params))
        elif search_type == "Publisher":
            search_params = {
                "query": args[1],
                "field_list": "id,name,api_detail_url,site_detail_url",
                "endpoint": "publishers",
            }
            self.task_list.append((self.search, search_params))
            volume_params = {
                "field_name": "volumes",
                "field_list": "id,name,volumes",
                "logging_fields": ["id", "name", "site_detail_url"],
            }
            self.task_list.append((self.get_random_comic_url, volume_params))
            comic_params = {
                "field_name": "issues",
                "field_list": "id,name,api_detail_url,site_detail_url,issues",
                "logging_fields": ["id", "name", "site_detail_url"],
            }
            self.task_list.append((self.get_random_comic_url, comic_params))
        elif search_type == "Teams":
            search_params = {
                "query": args[1],
                "field_list": "id,name,api_detail_url,site_detail_url,count_of_isssue_appearances",
                "endpoint": "teams",
                "sort_field": "count_of_isssue_appearances",
                "logging_fields": [
                    "id",
                    "name",
                    "site_detail_url",
                    "count_of_isssue_appearances",
                ],
            }
            self.task_list.append((self.search, search_params))
            comic_params = {
                "field_name": "issue_credits",
                "field_list": "id,name,api_detail_url,site_detail_url,issue_credits",
                "logging_fields": ["id", "name", "site_detail_url"],
            }
            self.task_list.append((self.get_random_comic_url, comic_params))

        if len(self.task_list) > 0:
            self.task_list.append((self.get_random_image_url, {}))

        return self

    def run(self):
        try:
            while self.task_list:
                task, *rest = self.task_list.popleft()
                logging.debug(task)
                logging.debug(rest)
                query_params = dict(
                    rest[0] if len(rest) > 0 else {},
                    **(
                        self.last_call_result
                        if self.last_call_result is not None
                        else {}
                    ),
                )
                logging.debug(f"Calling {task} with {query_params}")
                self.last_call_result = task(**query_params)
        except ComicCollisionError as ce:
            if self.last_chance is not True:
                history = self.rewind()
                self.reset()
                [self.task_list.append(e[0]) for e in history]
                self.last_call_result = history[0][2]
                self.last_chance = True
                logging.debug(
                    f"Rerunning {self.task_list} with initial query {self.last_call_result}"
                )
            else:
                return self.last_call_result

        if self.last_chance is True and self.task_list:
            self.last_call_result = self.run()

        return self.last_call_result

    def reset(self):
        self.task_list.clear()
        self.call_map.clear()
        self.last_call_result = None
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

    def search(self, **kargs) -> str:
        if self.unicorn_pi:
            show_color(COLORS["TEAL"])

        query = kargs.get("query", None)
        if query is None:
            raise ValueError("query param is mandatory")
        field_list = kargs.get("field_list", None)
        if field_list is None:
            raise ValueError("query param is mandatory")
        endpoint = kargs.get("endpoint", None)
        if endpoint is None:
            raise ValueError("endpoint param is mandatory")

        random_choice = kargs.get("random_choice", False)
        sort_field = kargs.get("sort_field", None)
        return_field = kargs.get("return_field", "api_detail_url")
        logging_fields = kargs.get("logging_fields", ["name", "id"])
        log_results = kargs.get("log_results", False)

        self.call_map = []
        params = {
            "api_key": self.api_key,
            "format": "json",
            "field_list": field_list,
            "filter": f"name:{query}",
            "limit": 100,
        }
        response = requests.get(
            f"{self.base_url}{endpoint}/", headers=self.headers, params=params
        )
        response.raise_for_status()
        data = response.json()
        response.close()
        results = data.get("results", [])

        if sort_field is not None:
            results.sort(key=lambda x: x[sort_field], reverse=True)

        if results:
            if log_results is True:
                for idx, result in enumerate(results, 1):
                    logging.debug(
                        f"{idx}: "
                        + ", ".join(f"{v}: {result[v]}" for v in logging_fields)
                    )

            if random_choice is True:
                # Pick a random entry from the search results
                chosen = self.random.choice(results)
                api_detail_url = chosen["api_detail_url"]
                self.call_map.append((self.search, len(results), kargs))
                logging.info(
                    f"Randomly selected: "
                    + ", ".join(f"{v}: {chosen[v]}" for v in logging_fields)
                )
            else:
                # Pick the first volume from the search results
                chosen = results[0]
                logging.info(
                    f"Picked first result: "
                    + ", ".join(f"{v}: {chosen[v]}" for v in logging_fields)
                )

            return {"api_detail_url": chosen[return_field]}
        else:
            raise ValueError(f"No {endpoint} found for {query}.")

    # Use the api detail url from search and return a random comic api url from all its comics
    def get_random_comic_url(self, **kargs) -> str:
        if self.unicorn_pi:
            show_color(COLORS["TURQUOISE"])
        api_detail_url = kargs.get("api_detail_url")
        if api_detail_url is None:
            raise ValueError("api_detail_url param is mandatory")
        field_name = kargs.get("field_name")
        if field_name is None:
            raise ValueError("field_name param is mandatory")
        field_list = kargs.get("field_list", None)
        if field_list is None:
            raise ValueError("field_list param is mandatory")
        return_field = kargs.get("return_field", "api_detail_url")
        logging_fields = kargs.get("logging_fields", ["id", "site_detail_url"])

        params = {"api_key": self.api_key, "format": "json", "field_list": field_list}
        response = requests.get(api_detail_url, headers=self.headers, params=params)
        response.raise_for_status()
        data = response.json()
        response.close()
        results = data.get("results", {})
        if results:
            chosen = self.random.choice(results[field_name])
            logging.debug(chosen)
            num_issues = len(results[field_name])
            api_detail_url = chosen[return_field]
            logging.info(
                f"Randomly selected: "
                + ", ".join(f"{v}: {chosen[v]}" for v in logging_fields)
            )
            self.call_map.append((self.get_random_comic_url, num_issues, kargs))
            return {"api_detail_url": api_detail_url}
        else:
            raise ValueError("No comic issues found for the specified series.")

    # So all routes lead here.  Get the detail about the issue
    # collate both the original cover and any special covers and pick a random image
    # Returns the image url and a potential resource name to save
    def get_random_image_url(self, **kargs) -> (str, str):
        if self.unicorn_pi:
            show_color(COLORS["BLUE"])
        api_detail_url = kargs.get("api_detail_url")
        # Once we know the volume ID we can do a second API call to fetch a list of issues and pick a random cover image
        params = {"api_key": self.api_key, "format": "json"}
        response = requests.get(
            f"{api_detail_url}", headers=self.headers, params=params
        )
        response.raise_for_status()
        data = response.json()
        response.close()
        issue = data.get("results", [])
        if issue:
            # print a link to the issue page on Comic Vine
            images = [issue["image"]["original_url"]] + [
                image["original_url"] for image in issue["associated_images"]
            ]
            logging.info(f"Find out more: {issue['site_detail_url']}")
            image_url = self.random.choice(images)
            image_name = slugify(
                f"{issue['volume']['name']} {issue['name']} {issue['issue_number']}_{issue['id']}",
                allow_unicode=True,
                separator=" ",
            )

            self.call_map.append((self.get_random_image_url, len(images), kargs))

            if self.dedupe is True:
                issue_hash = self.get_hash(image_url)
                if issue_hash in self.seen:
                    self.bummer = {"image_url": image_url, "image_name": image_name}
                    if self.last_chance is True:
                        logging.info("Dedupe comic: Failure - returning original")
                    raise ComicCollisionError(f"Comic collision on {image_url}")
                else:
                    self.add_hash(issue_hash)

            if self.last_chance is True:
                logging.info("Dedupe comic: Success")
            return {"image_url": image_url, "image_name": image_name}
        else:
            raise ValueError("No comic issues found for the specified series.")
