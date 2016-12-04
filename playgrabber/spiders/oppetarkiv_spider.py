# oppetarkiv_spider.py
#
# Download all available episodes of a TV show from oppetarkiv.se.
#
# Created by magicus <mag@icus.se> 2014-02-25
#
# -*- coding: utf-8 -*-

# FIXME: Should be rewritten to use http://www.svt.se/videoplayer-api/video/ like svtplay spider.

from subprocess import call
import re
import json
import glob

from scrapy.spider import Spider
from scrapy.selector import Selector
from scrapy.http import Request

from scrapy import signals
from scrapy.signalmanager import SignalManager
from scrapy.xlib.pydispatch import dispatcher

from playgrabber.items import PlayGrabberItem
from playgrabber.items import ShowInfoItem
from playgrabber.pipelines import RecordDownloadedPipeline
from playgrabber.pipelines import FilterRecordedPipeline

class PlayGrabberOppetArkivSpider(Spider):
    name = 'playgrabberoppetarkiv'
    allowed_domains = ['oppetarkiv.se']
    target_resolution = '1280x720'

    # Download information file name, hidden by default
    show_info_file = '.playgrabber-show.json'

    def find_shows_in_base(self, base):
        urls = []
        for filename in glob.glob(base + "/*/" + self.show_info_file):
            try:
                with open(filename, 'r') as file:
                    line = file.readline()
                    show_item = json.loads(line)
                    show_url = show_item['show_url']
                    urls.append(show_url)
            except:
                raise "Failed to open show info file: " + filename
        return urls

    # Accepted argument:
    #  'url'  = svtplay.se start URL
    #  'out'  = output directory to store downloaded files in
    #  'base' = base directory in which to create output directory based
    #           on show name.
    def __init__(self, url=None, out=None, base=None, *args, **kwargs):
        super(PlayGrabberOppetArkivSpider, self).__init__(*args, **kwargs)
        SignalManager(dispatcher.Any).connect(self.closed_handler, signal=signals.spider_closed)
        if out==None and base==None:
            raise Exception('Must provide argument "-a out=..." or "-a base=..."')
        if out!=None and base!=None:
            raise Exception('Cannot provide both argument "-a out=..." and "-a base=..."')
        if url==None and base==None:
            raise Exception('Must provide argument "-a url=..." or "-a base=..."')
        if url:
            self.start_urls = [url]
        else:
            self.start_urls = self.find_shows_in_base(base)
        self.output_dir = out
        self.output_base_dir = base

    # This is called when spider is done
    def closed_handler(self, spider):
        spider.log("==== Summary of downloaded videos ====")
        #for item in FilterRecordedPipeline.stored_items:
        for item in RecordDownloadedPipeline.stored_items:
            spider.log("Downloaded: '%s - %s' as %s/%s.%s" %  (item['show_title'], item['episode_title'], item['output_dir'], item['basename'], item['video_suffix']))

    # Return a proper title to apply to this season
    def get_show_and_season_title(self, item):
        show_id = item['show_id']
        season_id = item['season_id']
        show_url= item['show_url']
        output_dir = item['output_dir']

        updated = False

        try:
            with open(output_dir + '/' + self.show_info_file, 'r') as file:
                line = file.readline()
                show_item = json.loads(line)
                show_season_title_map = show_item['show_season_title_map']
        except:
            # If the file does not exist, we create a new show_item.
            show_item = ShowInfoItem()
            show_item['output_dir'] = output_dir
            show_item['show_url'] = show_url

            # First attempt is to name the season using using season_id
            # to Snn.
            if season_id != '00':
                show_season_title_map = { show_id: '.S' + season_id}
            else:
                # If we have no season_id and we are creating this file,
                # assume seasons are not relevant and use the empty string
                # as season name.
                show_season_title_map = { show_id: ''}

            show_item['show_season_title_map'] = show_season_title_map
            show_season_id_map = { show_id: season_id}
            show_item['show_season_id_map'] = show_season_id_map
            show_item['get_subtitles'] = True
            show_item['filter_out'] = ''

            updated = True

        try:
            show_season_id_map = show_item['show_season_id_map']
        except:
            show_season_id_map = { show_id: season_id}
            updated = True

        if not show_season_title_map.has_key(show_id):
            # First attempt is to name the season using using season_id
            # to Snn.
            if season_id != '00':
                show_season_title_map[show_id] = '.S' + season_id
            else:
                # Let's use the fallback: 'Show-nnnn' using show_id.
                show_season_title_map[show_id] = '.Show-' + show_id

            show_season_id_map[show_id] = season_id
            updated = True

        try:
            show_title = show_item['show_title']
            if show_title == '':
                # This should not happen but treat it as missing value
                raise
        except:
            # Read the value from the [episode] item, if missing from the show_item
            show_title = item['show_title']
            show_item['show_title'] = show_title
            updated = True

        if updated:
            # Save it back to disk if needed
            show_item['show_season_title_map'] = show_season_title_map
            show_item['show_season_id_map'] = show_season_id_map
            # First, create output dir if not alreay existing
            mkdir_cmd_line="mkdir -p '" + output_dir + "'"
            self.log('Executing: ' + mkdir_cmd_line)
            result_code = call(mkdir_cmd_line, shell=True)
            if result_code != 0:
                 raise "Failed to create directory " + output_dir

            with open(output_dir + '/' + self.show_info_file, 'w') as file:
                line = json.dumps(dict(show_item)) + '\n'
                file.write(line)

        season_title = show_season_title_map[show_id]
        return show_title + season_title

    # Default parse method, entry point
    def parse(self, response):
        # Call this page again and make sure we get all episodes

        if response.url.startswith("http://www.oppetarkiv.se/etikett/titel/"):
            show_base_url = response.url
        else:
            sel = Selector(response)
            try:
                # If this is the page of a single episode, get the base page,
                # i.e. all videos with the same title tag.
                show_base_url = sel.xpath("//dl[@class='svtoa-data-list']/dd/a/@href").re("(.*/etikett/titel/.*)")[0]
                if not show_base_url.startswith("http://www.oppetarkiv.se"):
                    show_base_url = 'http://www.oppetarkiv.se' + show_base_url
            except:
                raise Exception('Cannot extract a proper show base URL from %s' % response.url)

        # Start at page 1
        all_episodes_url = show_base_url.split('?')[0] + '?sida=1&sort=tid_stigande'
        return Request(all_episodes_url, callback=self.parse_all_episodes)

    def parse_all_episodes(self, response):
        # Figure out next page of the show base URL
        old_base_url_parts = re.search("(http://www.oppetarkiv.se/etikett/titel/.*sida=)([0-9]*)(&sort=tid_stigande)", response.url).groups()
        new_base_url = old_base_url_parts[0] + str(int(old_base_url_parts[1]) + 1) + old_base_url_parts[2]

        # Now extract all episodes and grab each of them
        sel = Selector(response)
        all_episode_bases = sel.xpath("//div[@role='main']/section//a/@href").extract()
        if not all_episode_bases[0].startswith("http://www.oppetarkiv.se"):
          all_episode_urls = []
          for base in all_episode_bases:
            episode_url = 'http://www.oppetarkiv.se' + base
            all_episode_urls.append(episode_url)
        else:
          all_episode_urls = all_episode_bases

        try:
          # Sometimes the link to next page is picked up in our link to episodes
          all_episode_urls.remove(new_base_url)
        except:
          pass

        for test_url in all_episode_urls:
          if re.search("&sort=tid_stigande&dir=-1", test_url):
            all_episode_urls.remove(test_url)

        if not all_episode_urls:
            self.log("No episodes available for show %s" % response.url)
        else:
            # Not really used for oppetarkiv.se
            original_show_id = '00000'

            # Get the show short name
            url_name_parts = re.search("(http://www.oppetarkiv.se/etikett/titel/)([^/\?]*)(/?\?sida=.*)", response.url).groups()
            show_short_name = url_name_parts[1]

            # Construct the show URL using short name and well-known prefix
            show_url = "http://www.oppetarkiv.se/etikett/titel/" + show_short_name

            if self.output_dir!=None:
                # Use the explicit output dir
                output_dir=self.output_dir
            else:
                # Create a output dir based on a base dir and the show title
                show_title = sel.xpath("//head/meta[@property='og:title']/@content").re('([^|]*) | [^|]*|.*')[0]
                output_dir=self.output_base_dir + '/' + show_title

            requests = []

            # Add all found episode urls
            for url in all_episode_urls:
                self.log("URL is %s" % url)
                request = Request(url, callback=self.parse_single_episode)
                item = PlayGrabberItem()
                item['output_dir'] = output_dir
                item['show_short_name'] = show_short_name
                item['show_url'] = show_url
                # Store the original show id (to be able to detect mixing of seasons)
                item['original_show_id'] = original_show_id
                # Pass on the item for further populating
                request.meta['episode-item'] = item
                requests.append(request)

            # Call ourself again with the next page of the show base URL
            request = Request(new_base_url, callback=self.parse_all_episodes)
            requests.append(request)

            return requests

    def parse_single_episode(self, response):
        # Grab essential data about this episode
        sel = Selector(response)

        # First grab show title and season
        try:
            show_title_and_season_id = sel.xpath("//header[@class='svtoa_video-area__header']/h1/span[@class='svt-text-margin-extra-small svt-display-block']/text()").re("[\n\t ]*(.*) - S.*song ([0-9]*)[\n\t ]*")
            show_title = show_title_and_season_id[0]
            season_id = show_title_and_season_id[1].zfill(2)
        except:
            # Assume no season specified
            try:
                show_title = sel.xpath("//header[@class='svtoa_video-area__header']/h1/span[@class='svt-text-margin-extra-small svt-display-block']/text()").re("[\n\t ]*(.*)[\n\t ]*")[0]
                season_id = '00'
            except:
                show_title = sel.xpath("//header[@class='svtoa_video-area__header']/h1/text()").re("[\n\t ]*(.*)[\n\t ]*")[0]
                season_id = '00'

        # We don't have access to the show_id here. As a safety measure, use the video id.
        # Hopefully we can overwrite this when we have flashvars.
        #show_id = sel.xpath("//a[@id='player']/@data-id").extract()[0]
        show_id = 0

        try:
            episode_id = sel.xpath("//header[@class='svtoa_video-area__header']/h1/span[@class='svt-heading-s svt-display-block']/text()").re("Avsnitt ([0-9]*) av*")[0].zfill(2)
        except:
            try:
                episode_id = sel.xpath("//header[@class='svtoa_video-area__header']/h1/span[@class='svt-heading-s svt-display-block']/text()").re("Del ([0-9]*) av*")[0].zfill(2)
            except:
                episode_id = '00'

        # A nice and robust URL, of the format:
        # http://www.svtplay.se/video/4711/episode-short-name
        try:
            episode_url = sel.xpath("//head/meta[@property='og:url']/@content").extract()[0]
        except:
            # As fallback, use provided url instead of fancy one.
            episode_url = response.url

        # A computer-friendly short version of the title, suitable to use as filename etc.
        episode_short_name = episode_url.split('/')[-1]

        # Retrieve the partially filled-in item and append more data
        item = response.meta['episode-item']

        item['episode_url']        = episode_url
        item['show_id']            = show_id
        item['show_title']         = show_title
        item['episode_id']         = episode_id
        item['episode_short_name'] = episode_short_name
        item['season_id']          = season_id

        # The "?type=embed" extension can really be read from the html code,
        # but it never seems to change so take the easy way out. :-)
        # With the embedded version, the "flashvars" are available which
        # will point to the HLS stream.
        request = Request(episode_url + '?type=embed', callback=self.parse_flashvars)
        # Pass on the item for further populating
        request.meta['episode-item'] = item

        return request

    def parse_flashvars(self, response):
        sel = Selector(response)

        # The data we're looking for is encoded as json in a
        # <object>...<param name="flashvars" value="json={...}">.
        flashvars_string = sel.xpath("//object[@class='svtplayer-jsremove']/param[@name='flashvars']/@value").re('json=(.*)')[0]
        # Parse the string to a json object.
        flashvars_json = json.loads(flashvars_string)

        # Retrieve the partially filled-in item and append more data
        item = response.meta['episode-item']

        # Get the episode title
        try:
            episode_title = flashvars_json["context"]["title"]
            if episode_title == "":
                episode_title = None
        except:
            episode_title = None

        try:
            video_id = flashvars_json["statistics"]["programId"].split("-")
            # If successful, let it override
            item['show_id'] = video_id[0]
            item['episode_id'] = video_id[1]
        except:
            pass

        try:
            item['show_title'] = flashvars_json["context"]["programTitle"]
        except:
            pass

        ## Calculate a suitable base name
        basename_title = episode_title
        if episode_title == None or re.search(r'/', basename_title):
            # The episode has no real title, just a 'day/month [hour:minute]' fake title,
            # or another title with a slash.
            # This is no good as filename, use the short name instead.
            basename_title = item['episode_short_name']

        # Get a suitable show/season title. Typically this is '<show_title>.S<season_id>'
        show_and_season_title = self.get_show_and_season_title(item)
        # We assume episode id is the episode number
        # Append on show/season_title to create an episode basename like this:
        # 'ShowName.Sxx.Exx.EpisodeName'
        basename = show_and_season_title + '.E' + item['episode_id'] + '.' + basename_title

        item['episode_title']      = episode_title
        item['basename']           = basename

        # Now locate subtitles
        try:
            subtitles_url = flashvars_json["video"]["subtitleReferences"][0]["url"]
            if subtitles_url == "":
                subtitles_url = None
        except:
            subtitles_url = None
        # Assume format is .srt
        subtitles_suffix = 'srt'

        item['subtitles_url']    = subtitles_url
        item['subtitles_suffix'] = subtitles_suffix

        video_references = flashvars_json["video"]["videoReferences"]
        # Typically, this array contains two elements, "flash" and "ios".
        # "ios" contains the HLS entry point we need.
        for ref in video_references:
            if ref['playerType'] == 'ios':
                video_master_url = ref['url']

        if video_master_url:
            self.log("video master URL %s" % video_master_url)
            # dont_filter is True, since this is on svtplay*.akamaihd.net, outside allowed_domains.
            request = Request(video_master_url, callback=self.parse_master_m3u8, dont_filter=True)
            # Pass on the item for further populating
            request.meta['episode-item'] = item
            return request
        else:
            raise("Cannot locate video master URL!")

    def parse_master_m3u8(self, response):
        # Now we got ourself an m3u8 (m3u playlist in utf-8) file in
        # the response. The URL we're looking for is preceeded by a
        # comment stating the proper resolution.
        get_next = False
        video_url = None
        for line in response.body.splitlines():
            if get_next:
                video_url = line
                break
            if re.search(r'RESOLUTION=' + self.target_resolution, line):
                get_next = True
        if video_url == None:
            raise("Cannot locate video URL of requested resolution")

        # Assume mp4 is a good suffix.
        video_suffix = 'mp4'
        # We've been parsing HLS all along.
        video_format = 'HLS'

        # Retrieve the partially filled-in item and complete it
        item = response.meta['episode-item']
        item['video_url']        = video_url
        item['video_suffix']     = video_suffix
        item['video_format']     = video_format
        return item
