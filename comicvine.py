import requests
import logging

from slugify import slugify


class ComicVine:
    def __init__(
        self,
        api_key,
        random,
        base_url="https://comicvine.gamespot.com/api/",
        headers={"User-Agent": "Python Comic Vine Random Image Client"},
    ):
        self.api_key = api_key
        self.random = random
        self.base_url = base_url
        self.headers = headers

    def set_random(self, rng):
        self.random = rng

    # Not currently used, was replaced by get_random_volume_url
    def search(self, resource, query, random_volume=False) -> str:
        params = {
            "api_key": self.api_key,
            "format": "json",
            "query": query,
            "resources": resource,
            "limit": 10 if random_volume else 1,
        }
        response = requests.get(
            f"{self.base_url}search/", headers=self.headers, params=params
        )
        response.raise_for_status()
        data = response.json()
        response.close()
        results = data.get("results", [])
        if results:
            for idx, volume in enumerate(results, 1):
                logging.info(
                    f"{idx}: {volume['name']} (ID: {volume['id']}, Start Year: {volume.get('start_year', 'N/A')})"
                )

            if random_volume is True:
                # Pick a random volume from the search results
                chosen = self.random.choice(results)
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
            raise ValueError(f"No {resource} found for {query}.")

    # Get 100 volumes (max) matching name and return a random api detail url from it
    def get_random_volume_url(self, query, random_volume=False) -> str:
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

    # Find all characters matching name, sort by how many comics they've appeared in (descending)
    # and return the api url for more detail from the most popular one
    def get_character_url(self, query) -> str:
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
            return chosen["api_detail_url"]
        else:
            raise ValueError(f"No character url found for {query}.")

    # Use the api detail url from above and return a random comic api url from all the comics they appeared in
    def get_random_character_appearance_url(self, api_detail_url) -> str:
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
            logging.info(f"Chose issue {chosen['site_detail_url']}")
            return chosen["api_detail_url"]
        else:
            raise ValueError(f"No character url found for {query}.")

    # Use the api detail url from /volumes and return a random comic api url from all its comics
    def get_random_comic_url(self, volume_detail_url) -> str:
        params = {"api_key": self.api_key, "format": "json"}
        response = requests.get(volume_detail_url, headers=self.headers, params=params)
        response.raise_for_status()
        data = response.json()
        response.close()
        results = data.get("results", [])
        if results:
            issue = self.random.choice(results["issues"])
            logging.info(
                f"Chose issue {issue['issue_number']} out of {len(results['issues'])}"
            )
            return issue["api_detail_url"]
        else:
            raise ValueError("No comic issues found for the specified series.")

    # So both routes (/volumes and /characters) lead here.  Get the detail about the issue
    # collate both the original cover and any special covers and pick a random image
    # Returns the image url and a potential resource name to save
    def get_random_image_url(self, comic_url) -> (str, str):
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
            return image_link, image_name
        else:
            raise ValueError("No comic issues found for the specified series.")
