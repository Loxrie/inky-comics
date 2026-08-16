# Comic Cover displayer for Inky Impression

## Description

Inspired by and based on the original comic.py sample from Pimoroni.  Original description:

### Original

- [comic.py](#comicpy)
  - [About Comic Vine](#about-comic-vine)
  - [Pre-requisites](#pre-requisites)
  - [Usage](#usage)
  - [Notes](#notes)

You can find a more detailed run down of how to use this script in our Learn Guide:

- [Learn: Displaying Comics on Inky Impression](https://learn.pimoroni.com/article/comics-on-inky-impression)

### Expanded

Expanded to include:
- Skeleton service for auto start
- Pick another random image via buttons
- Pick another random image via cron
- Pipe in a specific image via file

## About Comic Vine

Comic Vine is an awesome online database of comic book information. It has a free API that can be used to search and retrieve detailed information about comics, including cover images, issue details, and more. Check it out at https://comicvine.gamespot.com/ !

## Pre-requisites

You'll need to have the Inky library installed and your virtual environment activated: `source ~/.virtualenvs/pimoroni/bin/activate` + the additional package from requirements.txt (slugify).

OR

The requirements from requirements.txt and the inky package.  Which isn't there for reasons (such as enabling DEBUG)

## Usage

### Configuration

1. Get a Comic Vine API key: [https://comicvine.gamespot.com/api/](https://comicvine.gamespot.com/api/)
2. Create a settings.py with an API_KEY variable for your key.
3. Create the following two variables SEARCH_QUERIES and RANDOM_VOLUME

Array of tuples, first value must be "Volume" or "Character", experiment here. Some query terms work better as Character, others as Volume.  I found it particularly repetitive with Poison Ivy with the default code.

```
SEARCH_QUERIES = [
    ("Volume", "2000 AD"),
    ("Volume", "Darkminds"),
    ("Volume", "Witchblade"),
    ("Volume", "Paprika"),
    ("Volume", "Sunstone"),
    ("Character", "Poison Ivy"),
    ("Volume", "Harley Quinn"),
    ("Character", "Vampirella"),
    ("Character", "Jenny Sparks")
]
```

It comes down to whether you just want covers from Batman comics, or covers from comics Batman has appeared in?

RANDOM_VOLUME is an array of dict, with the key as a value from your search query.  If a search is Volume, the query should be present here.  As an example setting "2000 AD" to True gives lots of smaller results rather than the epic multi thousand issue run of the original 2000 AD.

```
RANDOM_VOLUME = {
    "2000 AD": False,
    "Darkminds": True,
    "Witchblade": True,
    "Paprika": True,
    "Sunstone": True,
    "Harley Quinn": True,
    "Vampirella": True
}
```

### Via Command Line

1. Run the script: `python comic.py`
2. The script will fetch a random comic cover and display it on your Inky Impression.

### Via systemd

1. Edit menu.sh and comic-menu.service with your user and group info, correcting paths as needed.
2. `sudo cp comic-menu.service /etc/systemd/service/`
3. `sudo systemctl daemon-reload`
4. Configure to run on boot `sudo systemctl enable comic-menu`
5. Start the service now `sudo systemctl start comic-menu`

### With the service running via systemd

Display new comics by making a file called `.new.comic.please` in the same dir as comic.py.  The file will get picked up, when a new comic is found and about to be displayed the file will be erased.

So crontab line might look like:

```
0 0,6,12,18 * * * touch /home/user/comic/.new.comic.please
```

for a new comic every 6 hours.

You can also put a full path to an image into the file which will then be displayed.

e.g.

```
echo -n "/home/user/Pictures/bob.jpg" > /home/user/comic/.new.comic.please
```

##License

Will add a new LICENSE (prob GPLv3) shortly.

This project contains code originally written and provided by Pimoroni under the MIT license included here as required:

```
MIT License

Copyright (c) 2018 Pimoroni Ltd.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
