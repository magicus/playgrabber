PlayGrabber
===========

PlayGrabber allows the user to download all episodes of a show on svtplay.se.
It works like a modern-day VCR, which you can program to download new episodes
on a regular basis of your favourite shows.

It is distributed under the GPLv3 license.

Requirements
============

PlayGrabber requires Python and the [Scrapy](http://scrapy.org) web scraping framework.

While PlayGrabber should not technically require Linux, it has been developed on Linux
and only tested on Linux. It is probably more or less painless to get it to work on other
unix-like platforms (like Mac OS X), and more or less painful to get it to work on Windows.

What's it for?
==============

PlayGrabber can be used in several ways:
1. To download all episodes that are available right now for a show on svtplay.se
2. To check a show or collection of show for new episodes, and download them

While 1 is useful, 2 is what makes PlayGrabber shine! The typical usecase is that
you add a new show for "watching" by PlayGrabber, and then regularly (typically,
once every night) run PlayGrabber and let it grab new episodes for your show(s).

If you want to check more than a single show, you will need a 'base' directory, 
in which all your shows are stored. The base directory will to contain
a bunch of subdirectories, one for each show.

If you are interested in just a single show, you can instead use a specific 'out' directory.
PlayGrabber will assume that the show is inside this directory, and not a level down as
with the base directory.

If you want to add a new show, you will need to specify it's URL. Just go to the show
in question on your web browser. Any episode will do, although I find it easiest to
go to the start page of the show e.g. by searching for it. Copy the URL from the browser
and use that.

If you just want to check a previously added show or list of shows, you don't need to
specify any URL.

Usage
=====

To run PlayGrabber, cd to the playgrabber directory and run
    scrapy crawl playgrabber [options]
where options are:

`-a url=<URL>` -- To specify an URL, e.g. `-a url=http://www.svtplay.se/foo-show`

`-a out=<directory>` -- To specify an 'out' directory, see above. Cannot be combined with -a base.

`-a base=<directory>` -- To specify a 'base' directory, see above. Cannot be combined with -a out.

`-o <json-output>` -- Store information about downloaded shows as a json file. (This functionality is build-in in scrapy,
but can often come in handy.)

Hints
=====
For efficient use, designate a base directory, e.g. /movies/PlayGrabber. Now you can add the show
"Foo Show" by 
    scrapy crawl playgrabber -a base=/movies/PlayGrabber -a url=http://www.svtplay.se/foo-show

PlayGrabber will automatically create a directory based on the name of the show ("Foo Show"), and
download the available episodes with names like "Foo Show.S01.E01.The mystery begins". Both the video
(as .mp4) and the subtitles, if available, (as .srt) will be downloaded for each episode.

When this is done, you can at any time check for and download new episodes like this:
    scrapy crawl playgrabber -a base=/movies/PlayGrabber

I recommend you create a simple script to do this for you. For instance, create
    /usr/local/bin/update-playgrabber.sh with:
    #!/bin/bash
    cd /opt/playgrabber
    TODAY=`date +"%Y-%m-%d"`
    scrapy crawl playgrabber -a base=/movies/PlayGrabber -o /var/log/playgrabber/$TODAY.json > /var/log/playgrabber/$TODAY.log 2>&1

This assumes that you have stored PlayGrabber in /opt/playgrabber, and that the user running the script have write permissions to /var/log/playgrabber.
It will store logs with downloaded files as *.json and the verbose scrapy output as *.log.

To have this script run at 4 am every night, run 'crontab -e' and add the following line:
    04 00 * * * /usr/local/bin/update-playgrabber.sh

Advanced topics
===============
PlayGrabber stores information about the show and downloaded episodes in two hidden files, 
.playgrabber.json and .playgrabber-show.json. 

The file .playgrabber.json contains information about all your downloaded episodes. If you delete this file, PlayGrabber
will forget about all your downloaded files. Do not do this, unless you really want that to happen.

The file .playgrabber-show.json contains general information about the show. A few fields in this file is possible to edit by
a text editor, to modify the behavior of PlayGrabber for that show:

* show_title: You can modify this to use another name for the show when creating filenames.
* get_subtitles: The default value is true. If set to false, no subtitles will be downloaded.
* filter_out: See below.
* show\_season\_title\_map: See below.

It is not recommended to modify any other values.

filter_out
----------
If this is non-empty, it is interpreted as a regex that is matched against the episode name. If it matches, the episode is *not* downloaded. Use this to e.g. filter out "syntolkat".

show\_season\_title\_map
---------------------
svtplay.se does not use season numbering internally, but instead uses a show id. PlayGrabber does some heuristics to
try to get a good season number to use (or none for shows where season is not applicable), but it can fail sometimes.

If your shows end up named "Foo Show.Show-4711.E01.Wtf", you can change this here. Locate ".Show-4711" in the map,
and modify it to a better value. Note that you will probably want to keep the leading dot.

