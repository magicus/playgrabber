# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: http://doc.scrapy.org/en/latest/topics/item-pipeline.html

import json
import re
from subprocess import call

from scrapy.exceptions import DropItem

class FilterRecordedPipeline(object):
    # Download information file name, hidden by default
    info_file = '.playgrabber.json'

    # Return the value of filter_out, or the empty string if no filter exists
    def get_filter_out(self, item, spider):
        try:
            output_dir = item['output_dir']
            with open(output_dir + '/' + spider.show_info_file, 'r') as file:
                line = file.readline()
                show_item = json.loads(line)
                filter_out = show_item['filter_out']
                return filter_out
        except:
            # If the value or file does not exist, assume we should not filter out
            # and return an empty filter
            return ''

    def get_recorded_items(self, output_dir):
        # Note: This is inefficient: read and parse the whole json file
        # each time, without any caching. Should be enough for now,
        # though.
        recorded_items = []
        try:
            with open(output_dir + '/' + self.info_file, 'r') as file:
                for line in file:
                    item = json.loads(line)
                    recorded_items.append(item)
        except:
            # If the file does not exists, our list of recorded items is empty.
            pass
        return recorded_items

    def is_item_in_records(self, item, recorded_items):
        # Note: This is an inefficient linear search. Should be enough
        # for now, though.
        for i in recorded_items:
            # Best match is if unique_video_id matches, but older videos may
            # not have that field.
            if 'unique_video_id' in i:
              if i['unique_video_id'] == item['unique_video_id']:
                return True

            # As a fallback, consider it a match if show and episode id matches.
            if i['show_id'] == item['show_id'] and i['episode_id'] == item['episode_id']:
                return True
        return False

    def process_item(self, item, spider):
        # Check if item is already recorded
        output_dir = item['output_dir']
        recorded_items = self.get_recorded_items(output_dir)
        if self.is_item_in_records(item, recorded_items):
            raise DropItem('Already recorded item, dropping %s:%s.' % (item['show_short_name'], item['episode_short_name']))

        # Check if we should filter out episode based on title
        filter_out = self.get_filter_out(item, spider)
        if filter_out != '':
            # If the filter is not empty, check if it matches
            if re.search(filter_out, item['episode_title']):
                # We match. Filter out.
                raise DropItem('Filtering out item due to match with "%s", dropping %s:%s.' % (filter_out, item['show_short_name'], item['episode_short_name']))

        # Otherwise, pass it on to downloaded
        return item

class DownloaderPipeline(object):

    # Return True if we should download subtitles, False otherwise.
    def should_get_subtitles(self, item, spider):
        try:
            output_dir = item['output_dir']
            with open(output_dir + '/' + spider.show_info_file, 'r') as file:
                line = file.readline()
                show_item = json.loads(line)
                get_subtitles = show_item['get_subtitles']
                return get_subtitles
        except:
            # If the value or file does not exist, assume we should get subtitles
            return True

    def call_command(self, cmd_line, action_desc, item, spider):
        spider.log('Executing: ' + cmd_line)
        result_code = call(cmd_line, shell=True)
        if result_code != 0:
             raise DropItem('Failed to ' + action_desc + '. Result code: %i, command line: %r' % (result_code, cmd_line))

    def process_item(self, item, spider):
        if item['video_format'] != 'HLS':
             raise DropItem('Video format unknown: %s' % item)

        # Extract basename
        basename = item['basename']

        # Command lines to run to download this data.

        # First, create output dir if not alreay existing
        output_dir = item['output_dir']
        mkdir_cmd_line="mkdir -p '" + output_dir + "'"
        self.call_command(mkdir_cmd_line, 'create output directory', item, spider)

        # Then download subtitles if available
        subtitles_url = item['subtitles_url']
        subtitles_suffix = item['subtitles_suffix']
        if subtitles_url != None:
            if self.should_get_subtitles(item, spider):
                wget_cmd_line = "wget -O '" + output_dir + '/' + basename + '.' + subtitles_suffix + "' '" + subtitles_url + "'"
                self.call_command(wget_cmd_line, 'download subtitles', item, spider)
            else:
                spider.log('Not downloading subtitles from %s' % subtitles_url)

        # Then download video
        video_url = item['video_url']
        video_suffix = item['video_suffix']
        ffmpeg_cmd_line  = "ffmpeg -y -i '" + video_url + "' -acodec copy -vcodec copy -absf aac_adtstoasc '" + output_dir + '/' + basename + '.' + video_suffix + "'"
        self.call_command(ffmpeg_cmd_line, 'download video', item, spider)

        return item

class RecordDownloadedPipeline(object):
    # Download information file name, hidden by default
    info_file = '.playgrabber.json'
    stored_items = []

    def record_item(self, item):
        # At this point, we can be sure that the output dir is alreay existing
        self.stored_items.append(item)
        output_dir = item['output_dir']
        with open(output_dir + '/' + self.info_file, 'a') as file:
            line = json.dumps(dict(item)) + '\n'
            file.write(line)

    def process_item(self, item, spider):
        # Record that we got it now
        self.record_item(item)
        return item
