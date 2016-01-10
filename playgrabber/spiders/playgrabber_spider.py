# playgrabber_spider.py
#
# Download all available episodes of a TV show from svtplay.se.
# 
# Created by magicus <mag@icus.se> 2014-02-25
#
# -*- coding: utf-8 -*-

from subprocess import call
import re
import json
import glob

from scrapy.spider import Spider
from scrapy.selector import Selector
from scrapy.http import Request

from scrapy import signals
from scrapy import log

from scrapy.signalmanager import SignalManager
from scrapy.xlib.pydispatch import dispatcher

from playgrabber.items import PlayGrabberItem
from playgrabber.items import ShowInfoItem
from playgrabber.pipelines import RecordDownloadedPipeline
from playgrabber.pipelines import FilterRecordedPipeline

class PlayGrabberSpider(Spider):
    name = 'playgrabber'
    allowed_domains = ['svtplay.se']

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
        super(PlayGrabberSpider, self).__init__(*args, **kwargs)
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
                 raise Exception("Failed to create directory " + output_dir)
            
            with open(output_dir + '/' + self.show_info_file, 'w') as file:
                line = json.dumps(dict(show_item)) + '\n'
                file.write(line)

        season_title = show_season_title_map[show_id]
        return show_title + season_title

    # Default parse method, entry point
    def parse(self, response):
        sel = Selector(response)

        # If this is a show index page, we need to get the URL for a single episode
        # (anyone will do, let's take the latest)
        try:
            any_episode_base_url = sel.xpath('//a[@class="play_title-page-trailer__start-button"]/@href').extract()[0]
            any_episode_url = 'http://www.svtplay.se' + any_episode_base_url
        except:
            # Otherwise we assume this url is for a single episode and not an index
            # page, and use it directly
            any_episode_url = response.url
            
        # Call this page again and make sure we get all episodes
        all_episodes_url = any_episode_url.split('?')[0] + '?tab=program&sida=99'
        return Request(all_episodes_url, callback=self.parse_all_episodes)

    def parse_all_episodes(self, response):
        # Now extract all episodes and grab each of them
        sel = Selector(response)
        all_episode_urls = sel.xpath("//div[@id='more-episodes-panel']//article/a/@href").extract()
        
        if not all_episode_urls:
            self.log("No episodes available for show %s" % response.url)
        else:
            # The video_id is in format 'show_id-episode_id'
            try:
                show_id = sel.xpath("//section[@role='main']//a/@data-popularity-program-id").re('([0-9]*)-[0-9]*')[0]
            except:
                show_id = '00000'

            # Get the show url from the rss link
            show_url = sel.xpath("//link[@type='application/rss+xml']/@href").re('(.*)/rss.xml')[0]

            if self.output_dir!=None:
                # Use the explicit output dir
                output_dir=self.output_dir
            else:
                # Create a output dir based on a base dir and the show title
                show_title = sel.xpath("//div[@class='play_video-area-aside__info']/h1/a/text()").extract()[0]
                output_dir=self.output_base_dir + '/' + show_title
                
            requests = []
            for url in all_episode_urls:
                request = Request('http://www.svtplay.se' + url, callback=self.parse_single_episode)
                item = PlayGrabberItem()
                item['output_dir'] = output_dir
                item['show_url'] = show_url
                # Store the original show id (to be able to detect mixing of seasons)
                item['original_show_id'] = show_id
                # Pass on the item for further populating
                request.meta['episode-item'] = item
                requests.append(request)
            return requests

    def parse_single_episode(self, response):
        # Grab essential data about this episode
        sel = Selector(response)
        
        # First grab show title
        show_title = sel.xpath("//div[@class='play_video-area-aside__info']/h1/a/text()").extract()[0]

        # The video_id is in format 'show_id-episode_id'
        try:
            video_id = sel.xpath("//section[@role='main']//span/@data-popularity-program-id").re('([0-9]*)-([0-9]*)')
            show_id = video_id[0]
            episode_id = video_id[1]
        except:
            show_id = '00000'
            try:
                episode_id = sel.xpath("//section[@role='main']//a/@data-json-href").re('/video/(.*)')[0]
            except:
                episode_id = '00'

        # A nice and robust URL, of the format:
        # http://www.svtplay.se/video/4711/episode-short-name
        try:
            episode_url = sel.xpath("//section[@role='main']//a/@data-popularity-url").extract()[0]
        except:
            # As fallback, use provided url instead of fancy one.
            episode_url = response.url

        # A computer-friendly short version of the title, suitable to use as filename etc.
        episode_short_name = episode_url.split('/')[-1]
        
        # Get the show short name from the rss link
        show_short_name = sel.xpath("//link[@type='application/rss+xml']/@href").re('http://[^/]*/(.*)/rss.xml')[0]

        # Try to get the season id
        try:
            season_id = sel.xpath("//h2[@class='play_video-area-aside__sub-title']").re('song ([0-9]+)[ \t\n]*-')[0].zfill(2)
        except:
            season_id = '00'

        # Retrieve the partially filled-in item and append more data
        item = response.meta['episode-item']

        item['episode_url']        = episode_url
        item['show_id']            = show_id
        item['show_short_name']    = show_short_name
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
        video_master_url = None

        for ref in video_references:
            if ref['playerType'] == 'ios':
                video_master_url = ref['url']
        
        if video_master_url != None:
            item['video_master_url'] = video_master_url

            # dont_filter is True, since this is on svtplay*.akamaihd.net, outside allowed_domains.
            request = Request(video_master_url, callback=self.parse_master_m3u8, dont_filter=True)
            # Pass on the item for further populating
            request.meta['episode-item'] = item
            return request
        else:
            raise Exception("Cannot locate video master URL for %s!" % item['basename'])
        
    def parse_master_m3u8(self, response):
        # Retrieve the partially filled-in item
        item = response.meta['episode-item']

        # Now we got ourself an m3u8 (m3u playlist in utf-8) file in 
        # the response. We will aim to get the stream with the highest bandwidth
        # requirement, believing it to be of best quality.
        highest_bandwidth = 0
        next_bandwidth = 0
        video_url = None
        
        for line in response.body.splitlines():
            stream_description_match = re.search(r'^#EXT-X-STREAM-INF:.*BANDWIDTH=([0-9]+),', line)
            if stream_description_match:
                next_bandwidth = int(stream_description_match.group(1))
                if next_bandwidth >= highest_bandwidth:
                    highest_bandwidth = next_bandwidth
                    hls_stream_description = line
                else:
                    next_bandwidth = 0
            elif next_bandwidth != 0:
                video_url = line

        if video_url == None:
            self.log("Cannot locate a suitable video URL, using master url for %s" % item['basename'], level=log.WARNING)
            video_url = item['video_master_url']
        else:
            self.log("Located video for %s with the following HLS description: %s" % (item['basename'], hls_stream_description))

        # Assume mp4 is a good suffix.
        video_suffix = 'mp4'
        # We've been parsing HLS all along.
        video_format = 'HLS'
        
        # Complete the partially filled-in item
        item = response.meta['episode-item']
        item['video_url']        = video_url        
        item['video_suffix']     = video_suffix        
        item['video_format']     = video_format        
        return item
