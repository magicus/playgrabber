# Define here the models for your scraped items
#
# See documentation in:
# http://doc.scrapy.org/en/latest/topics/items.html

from scrapy.item import Item, Field

class PlayGrabberItem(Item):
    # Basic options for PlayGrabber
    output_dir = Field()
    show_url = Field()
    original_show_id = Field()

    episode_url = Field()
    unique_video_id = Field()
    program_unique_id = Field()
    show_id = Field()
    show_short_name = Field()
    show_title = Field()
    episode_id = Field()
    episode_short_name = Field()
    episode_title = Field()
    season_id = Field()
    basename = Field()

    subtitles_url = Field()
    subtitles_suffix = Field()
    video_url = Field()
    video_suffix = Field()
    video_format = Field()
    video_master_url = Field()

class ShowInfoItem(Item):
    # Basic options for PlayGrabber
    output_dir = Field()
    show_url = Field()
    show_season_title_map = Field()
    show_season_id_map = Field()
    get_subtitles = Field()
    filter_out = Field()
    show_title = Field()
