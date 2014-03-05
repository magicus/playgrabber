# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: http://doc.scrapy.org/en/latest/topics/item-pipeline.html

from re import search
from subprocess import call

class DownloaderPipeline(object):
    def process_item(self, item, spider):
        if item['video_format'] != 'HLS':
             raise DropItem('Video format unknown: %s' % item)

        episode_title = item['episode_title']
        if search(r'.*/.* .*:.*', episode_title):
            # The episode has no real title, just a 'day/month hour:minute' fake title.
            # This is no good as filename, use the short name instead.
            episode_title = item['episode_short_name']
        
        show_id = item['show_id']
        original_show_id = item['original_show_id']
        if show_id != original_show_id:
            # This episode is from a different season than the original.
            # We can't know season number, but mark this as different
            season_title = '.Show-' + show_id
        else:
            # Otherwise we skip putting any season information in the name
            season_title = ''
        show_title = item['show_title']
        # We assume episode id is the episode number
        episode_id = item['episode_id']
        # Create an episode basename like this 'ShowName.(Show-xx.)Exx.EpisodeName'
        basename = show_title + season_title + '.E' + episode_id + '.' + episode_title
        
        # Command lines to run to download this data.
        
        # First, create output dir if not alreay existing
        output_dir = item['output_dir']
        mkdir_cmd_line="mkdir -p '" + output_dir + "'"
        print mkdir_cmd_line
        call(mkdir_cmd_line, shell=True)
        
        # Then download subtitles if available
        subtitles_url = item['subtitles_url']
        subtitles_suffix = item['subtitles_suffix']
        if subtitles_url != None:
            wget_cmd_line = "wget -O '" + output_dir + '/' + basename + '.' + subtitles_suffix + "' '" + subtitles_url + "'"
            print wget_cmd_line
            call(wget_cmd_line, shell=True)

        # Then download video
        video_url = item['video_url']
        video_suffix = item['video_suffix']
        ffmpeg_cmd_line  = "ffmpeg -i '" + video_url + "' -acodec copy -vcodec copy -absf aac_adtstoasc '" + output_dir + '/' + basename + '.' + video_suffix + "'"
        print ffmpeg_cmd_line
        call(ffmpeg_cmd_line, shell=True)

        return item
