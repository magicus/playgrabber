# ur_spider.py
#
# Download all available episodes of a TV show from ur.se.
# 
# Created by magicus <mag@icus.se> 2015-02-24
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
from scrapy.signalmanager import SignalManager
from scrapy.xlib.pydispatch import dispatcher

from playgrabber.items import PlayGrabberItem
from playgrabber.items import ShowInfoItem
from playgrabber.pipelines import RecordDownloadedPipeline
from playgrabber.pipelines import FilterRecordedPipeline

class PlayGrabberUrSpider(Spider):
    name = 'playgrabberur'
    allowed_domains = ['ur.se']
    target_resolution = '1280x720'
    # Disable hd to work around bug in v1.x of ffmpeg
    prefer_hd = False

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
        super(PlayGrabberUrSpider, self).__init__(*args, **kwargs)
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

    # Default parse method, entry point (parse_all_episodes)
    def parse(self, response):
        # Extract all episodes and grab each of them
        sel = Selector(response)
        all_episode_urls = sel.xpath("//section[@class='product-puff']/a[@class='puff tv video']/@href").extract()
        
        if not all_episode_urls:
            # Maybe this is a single episode, get the show base URL
            all_episode_urls = sel.xpath("//header[@class='video']//a/@href").extract()
            if not all_episode_urls:
                self.log("No episodes available for show %s" % response.url)
                return

        # Most of the useful data is in a json string argument to urPlayer.init
        init_data_string =  sel.xpath("//script/text()").re('urPlayer.init\((.*)\)')[0]
        # Parse the string to a json object.
        init_data = json.loads(init_data_string)
        
        try:
            show_id = str(init_data['series_id'])
        except:
            # If no show id is available, use episode id as fallback
            show_id = str(init_data['id'])

        try:
            show_title = init_data['series_title']
        except:
            # If no show title is available, use episode title as fallback
            show_title = init_data['title']

        # Get the show url from the rss link
        show_url_base = sel.xpath("//header[@class='video']//a/@href").extract()[0]
        show_url = 'http://www.ur.se' + show_url_base

        if self.output_dir!=None:
            # Use the explicit output dir
            output_dir=self.output_dir
        else:
            # Create a output dir based on a base dir and the show title
            output_dir=self.output_base_dir + '/' + show_title
            
        requests = []
        for url in all_episode_urls:
            request = Request('http://www.ur.se' + url, callback=self.parse_single_episode)
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
        
        # Retrieve the partially filled-in item and append more data
        item = response.meta['episode-item']

        # Most of the useful data is in a json string argument to urPlayer.init
        init_data_string =  sel.xpath("//script/text()").re('urPlayer.init\((.*)\)')[0]
        # Parse the string to a json object.
        init_data = json.loads(init_data_string)
        self.log('UR json data: %s' % init_data)

        # First grab show id and title (again...)
        try:
            show_id = str(init_data['series_id'])
        except:
            # If no show id is available, use episode id as fallback
            show_id = str(init_data['id'])

        try:
            show_title = init_data['series_title']
        except:
            # If no show title is available, use episode title as fallback
            show_title = init_data['title']

        # Not all videos has an episode id
        try:
            episode_id = sel.xpath("//div[@id='Om-programmet-content']//h3[@property='schema:partOfSeries']/text()").re('Avsnitt ([0-9]+)')[0].zfill(2)
        except:
            # Otherwise use the video id
            episode_id = str(init_data['id']).zfill(2)

        # A nice and robust URL, of the format:
        # http://www.svtplay.se/video/4711/episode-short-name
        try:
            episode_url = sel.xpath("//meta[@property='og:url']/@content").extract()[0]
        except:
            # As fallback, use provided url instead of fancy one.
            episode_url = response.url

        # A computer-friendly short version of the title, suitable to use as filename etc.
        episode_short_name = episode_url.split('/')[-1]
        
        # Get the show short name
        show_short_name = sel.xpath("//header[@class='video']//a/@href").re("/Produkter/(.*)")[0]

        # Get the episode title
        episode_title = sel.xpath("//meta[@property='schema:name']/@content").extract()[0]

        # Try to get the season id
        try:
            season_id = sel.xpath("//meta[@property='schema:name']/@content").re('S.song ([0-9]+)')[0].zfill(2)
        except:
            season_id = '00'

        # Locate subtitles
        all_subtitles = init_data['subtitles']
        if all_subtitles == "":
            subtitles_url = None
        else:
            # Check if this is new format
            if isinstance(all_subtitles, list):
                subtitles_url = all_subtitles[0]['file']
            else:
                # We just keep the first subtitle, hoping it's the one we want.
                subtitles_url = all_subtitles.split(',')[0]

        # Assume format is .tt
        subtitles_suffix = 'tt'

        # Create the video url.
        if not init_data['file_http_hd'] == "" and self.prefer_hd:
            # If we have a HD stream, use it
            video_base_name = init_data['file_http_hd']
        else:
            video_base_name = init_data['file_http']
        if video_base_name == "":
            raise Exception('Could not extract video_base_name')

        video_loadbalancer_hostname = init_data['streaming_config']['streamer']['redirect']
        video_hls_filename = init_data['streaming_config']['http_streaming']['hls_file']

        # ... and combine these into a winner!
        video_url = 'http://' + video_loadbalancer_hostname + '/' + video_base_name + video_hls_filename

        # Assume mp4 is a good suffix.
        video_suffix = 'mp4'
        # We've been parsing HLS all along.
        video_format = 'HLS'
        
        # Retrieve the partially filled-in item and complete it
        item = response.meta['episode-item']

        item['episode_title']      = episode_title
        item['subtitles_url']      = subtitles_url        
        item['subtitles_suffix']   = subtitles_suffix        
        item['episode_url']        = episode_url
        item['video_url']          = video_url        
        item['video_suffix']       = video_suffix        
        item['video_format']       = video_format        
        item['show_id']            = show_id
        item['show_short_name']    = show_short_name
        item['show_title']         = show_title
        item['episode_id']         = episode_id
        item['episode_short_name'] = episode_short_name
        item['season_id']          = season_id
        
        # Calculate a suitable base name
        # Get a suitable show/season title. Typically this is '<show_title>.S<season_id>'
        show_and_season_title = self.get_show_and_season_title(item)
        # We assume episode id is the episode number
        # Append on show/season_title to create an episode basename like this:
        # 'ShowName.Sxx.Exx.EpisodeName'
        basename = show_and_season_title + '.E' + item['episode_id'] + '.' + episode_title
        
        item['basename']           = basename

        return item
