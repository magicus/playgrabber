# playgrabber_spider.py
#
# Download all available episodes of a TV show from svtplay.se using the pirateplay.se API.
# 
# Created by magicus <mag@icus.se> 2014-02-25
#
# -*- coding: utf-8 -*-

from urllib import quote_plus

from scrapy.spider import Spider
from scrapy.selector import Selector
from scrapy.http import Request

from playgrabber.items import PlayGrabberItem

class PlayGrabberSpider(Spider):
    name = 'playgrabber'
    allowed_domains = ['svtplay.se', 'pirateplay.se']

    # Accepted argument: 
    #  'url'  = svtplay.se start URL
    #  'out'  = output directory to store downloaded files in
    #  'base' = base directory in which to create output directory based
    #           on show name.
    def __init__(self, url=None, out=None, base=None, *args, **kwargs):
        super(PlayGrabberSpider, self).__init__(*args, **kwargs)
        if url==None: 
            raise Exception('Must provide argument "-a url=..."')
        if out==None and base==None: 
            raise Exception('Must provide argument "-a out=..." or "-a base=..."')
        if out!=None and base!=None:
            raise Exception('Cannot provide both argument "-a out=..." and "-a base=..."')
        self.start_urls = [url]
        self.output_dir = out
        self.output_base_dir = base

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
        show_id = sel.xpath("//div[@class='playVideoBox']/a[@id='player']/@data-popularity-program-id").re('([0-9]*)-[0-9]*')[0]

        # Get the show url from the rss link
        show_url = sel.xpath("//link[@type='application/rss+xml']/@href").re('(.*)/rss.xml')[0]

        if self.output_dir!=None:
            # Use the explicit output dir
            output_dir=self.output_dir
        else:
            # Create a output dir based on a base dir and the show title
            # The video title is in format 'show_title - episode_title'
            show_title = sel.xpath("//div[@class='playVideoBox']/a[@id='player']/@data-title").re('(.*) - .*')[0]
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
        
        # The video title is in format 'show_title - episode_title'
        video_title = sel.xpath("//div[@class='playVideoBox']/a[@id='player']/@data-title").re('(.*) - (.*)')
        show_title = video_title[0]
        episode_title = video_title[1]
        # The video_id is in format 'show_id-episode_id'
        video_id = sel.xpath("//div[@class='playVideoBox']/a[@id='player']/@data-popularity-program-id").re('([0-9]*)-([0-9]*)')
        show_id = video_id[0]
        episode_id = video_id[1]

        # A nice and robust URL to pass to pirateplay.se, of the format:
        # http://www.svtplay.se/video/4711/episode-short-name
        episode_url = sel.xpath("//div[@class='playVideoBox']/a[@id='player']/@data-popularity-url").extract()[0]

        # A computer-friendly short version of the title, suitable to use as filename etc.
        episode_short_name = episode_url.split('/')[-1]
        
        # Get the show short name from the rss link
        show_short_name = sel.xpath("//link[@type='application/rss+xml']/@href").re('http://[^/]*/(.*)/rss.xml')[0]

        # Retrieve the partially filled-in item and append more data
        item = response.meta['episode-item']
        item['episode_url']        = episode_url
        item['show_id']            = show_id
        item['show_short_name']    = show_short_name
        item['show_title']         = show_title
        item['episode_id']         = episode_id
        item['episode_short_name'] = episode_short_name
        item['episode_title']      = episode_title

        request = Request('http://pirateplay.se/api/get_streams.xml?url=' + quote_plus(episode_url), callback=self.parse_pirateplay)
        # Pass on the item for further populating
        request.meta['episode-item'] = item
        return request

    def parse_pirateplay(self, response):
        sel = Selector(response)
        try:
            # URL containing subtitles
            subtitles_url = sel.xpath('//stream[1]/@subtitles').extract()[0]
        except IndexError:
            subtitles_url = None
        # Assume format is .srt
        subtitles_suffix = 'srt'

        try:
            # Suggested file suffix (typically .mp4)
            video_suffix = sel.xpath('//stream[1]/@suffix-hint').extract()[0]
        except IndexError:
            # Provide default value
            video_suffix = 'mp4'
        # URL for video stream
        video_url = sel.xpath('//stream[1]/text()').extract()[0]

        # Assume HLS which is only supported format at the moment.
        video_format = 'HLS'

        # Retrieve the partially filled-in item and complete it
        item = response.meta['episode-item']
        item['subtitles_url']    = subtitles_url        
        item['subtitles_suffix'] = subtitles_suffix        
        item['video_url']        = video_url        
        item['video_suffix']     = video_suffix        
        item['video_format']     = video_format        
        return item
