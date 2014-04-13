# playgrabber_spider.py
#
# Download all available episodes of a TV show from svtplay.se using the pirateplay.se API.
# 
# Created by magicus <mag@icus.se> 2014-02-25
#
# -*- coding: utf-8 -*-

from urllib import quote_plus
from subprocess import call
import re
import json

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

class PlayGrabberSpider(Spider):
    name = 'playgrabber'
    allowed_domains = ['svtplay.se']
    target_resolution = '1280x720'

    # Download information file name, hidden by default
    show_info_file = '.playgrabber-show.json'    

    # Accepted argument: 
    #  'url'  = svtplay.se start URL
    #  'out'  = output directory to store downloaded files in
    #  'base' = base directory in which to create output directory based
    #           on show name.
    def __init__(self, url=None, out=None, base=None, *args, **kwargs):
        super(PlayGrabberSpider, self).__init__(*args, **kwargs)
        SignalManager(dispatcher.Any).connect(self.closed_handler, signal=signals.spider_closed)
        if url==None: 
            raise Exception('Must provide argument "-a url=..."')
        if out==None and base==None: 
            raise Exception('Must provide argument "-a out=..." or "-a base=..."')
        if out!=None and base!=None:
            raise Exception('Cannot provide both argument "-a out=..." and "-a base=..."')
        self.start_urls = [url]
        self.output_dir = out
        self.output_base_dir = base

    # This is called when spider is done
    def closed_handler(self, spider):
        print "==== Summary of downloaded videos ===="
        #for item in FilterRecordedPipeline.stored_items:
        for item in RecordDownloadedPipeline.stored_items:
            print "Downloaded: '%s - %s' as %s/%s.%s" %  (item['show_title'], item['episode_title'], item['output_dir'], item['basename'], item['video_suffix'])

    # Return a proper title to apply to this season
    def get_season_title(self, show_id, show_url, output_dir):
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
            # If we create this file, default is that the first show_id gets the
            # empty string as season name.
            show_season_title_map = { show_id: ''}
            show_item['show_season_title_map'] = show_season_title_map
            updated = True
        
        if not show_season_title_map.has_key(show_id):
            # Let's add this season's default name, 'Show-NNN'
            show_season_title_map[show_id] = '.Show-' + show_id
            updated = True

        if updated:
            # Save it back to disk if needed
            show_item['show_season_title_map'] = show_season_title_map
            # First, create output dir if not alreay existing
            mkdir_cmd_line="mkdir -p '" + output_dir + "'"
            print 'Executing: ' + mkdir_cmd_line
            result_code = call(mkdir_cmd_line, shell=True)
            if result_code != 0:
                 raise "Failed to create directory " + output_dir
            
            with open(output_dir + '/' + self.show_info_file, 'w') as file:
                line = json.dumps(dict(show_item)) + '\n'
                file.write(line)

        season_title = show_season_title_map[show_id]
        return season_title

    # Default parse method, entry point
    def parse(self, response):
        # Call this page again and make sure we get all episodes
        all_episodes_url = response.url.split('?')[0] + '?tab=program&sida=99'
        return Request(all_episodes_url, callback=self.parse_all_episodes)

    def parse_all_episodes(self, response):
        # Now extract all episodes and grab each of them
        sel = Selector(response)
        all_episode_urls = sel.xpath("//div[@id='programpanel']//article/div[@class='playDisplayTable']/a[1]/@href").extract()
        # The video_id is in format 'show_id-episode_id'
        try:
            show_id = sel.xpath("//div[@class='playVideoBox']/a[@id='player']/@data-popularity-program-id").re('([0-9]*)-[0-9]*')[0]
        except:
            show_id = '00000'

        # Get the show url from the rss link
        show_url = sel.xpath("//link[@type='application/rss+xml']/@href").re('(.*)/rss.xml')[0]

        if self.output_dir!=None:
            # Use the explicit output dir
            output_dir=self.output_dir
        else:
            # Create a output dir based on a base dir and the show title
            show_title = sel.xpath("//div[@class='playVideoBox']//h1/text()").extract()[0]
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
        
        # First grab show title separately
        show_title = sel.xpath("//div[@class='playVideoBox']//h1/text()").extract()[0]

        # The video title is in format 'show_title - episode_title'
        # We can't use it for both show and episode title, since if there's
        # a " - " in either of them, we might split incorrectly.
        episode_title = sel.xpath("//div[@class='playVideoBox']/a[@id='player']/@data-title").re(show_title + ' - (.*)')[0]
        # The video_id is in format 'show_id-episode_id'
        try:
            video_id = sel.xpath("//div[@class='playVideoBox']/a[@id='player']/@data-popularity-program-id").re('([0-9]*)-([0-9]*)')
            show_id = video_id[0]
            episode_id = video_id[1]
        except:
            show_id = '00000'
            try:
                episode_id = sel.xpath("//div[@class='playVideoBox']/a[@id='player']/@data-json-href").re('/video/(.*)')[0]
            except:
                episode_id = '00'

        # A nice and robust URL to pass to pirateplay.se, of the format:
        # http://www.svtplay.se/video/4711/episode-short-name
        try:
            episode_url = sel.xpath("//div[@class='playVideoBox']/a[@id='player']/@data-popularity-url").extract()[0]
        except:
            # As fallback, use provided url instead of fancy one.
            episode_url = response.url

        # A computer-friendly short version of the title, suitable to use as filename etc.
        episode_short_name = episode_url.split('/')[-1]
        
        # Get the show short name from the rss link
        show_short_name = sel.xpath("//link[@type='application/rss+xml']/@href").re('http://[^/]*/(.*)/rss.xml')[0]

        # Retrieve the partially filled-in item and append more data
        item = response.meta['episode-item']

        ## Calculate a suitable base name
        basename_title = episode_title
        if re.search(r'/', basename_title):
            # The episode has no real title, just a 'day/month [hour:minute]' fake title,
            # or another title with a slash. 
            # This is no good as filename, use the short name instead.
            basename_title = episode_short_name
        
        season_title = self.get_season_title(show_id, item['show_url'], item['output_dir'])

        # We assume episode id is the episode number
        # Create an episode basename like this 'ShowName.(Show-xx.)Exx.EpisodeName'
        basename = show_title + season_title + '.E' + episode_id + '.' + basename_title
        
        item['episode_url']        = episode_url
        item['show_id']            = show_id
        item['show_short_name']    = show_short_name
        item['show_title']         = show_title
        item['episode_id']         = episode_id
        item['episode_short_name'] = episode_short_name
        item['episode_title']      = episode_title
        item['basename']           = basename

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
        flashvars_string = sel.xpath("//div[@class='svtFullFrame']/div[@id='player']/object[@class='svtplayer-jsremove']/param[@name='flashvars']/@value").re('json=(.*)')[0]
        # Parse the string to a json object.
        flashvars_json = json.loads(flashvars_string)
        
        # First locate subtitles
        try:
            subtitles_url = flashvars_json["video"]["subtitleReferences"][0]["url"]
        except:
            subtitles_url = None
        # Assume format is .srt
        subtitles_suffix = 'srt'
        
        # Retrieve the partially filled-in item and append more data
        item = response.meta['episode-item']
        item['subtitles_url']    = subtitles_url        
        item['subtitles_suffix'] = subtitles_suffix        

        video_references = flashvars_json["video"]["videoReferences"]
        # Typically, this array contains two elements, "flash" and "ios".
        # "ios" contains the HLS entry point we need.
        for ref in video_references:
            if ref['playerType'] == 'ios':
                video_master_url = ref['url']
        
        if video_master_url:
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
