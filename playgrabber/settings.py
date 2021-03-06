# Scrapy settings for playgrabber project
#
# For simplicity, this file contains only the most important settings by
# default. All the other settings are documented here:
#
#     http://doc.scrapy.org/en/latest/topics/settings.html
#

BOT_NAME = 'playgrabber'

SPIDER_MODULES = ['playgrabber.spiders']
NEWSPIDER_MODULE = 'playgrabber.spiders'

ITEM_PIPELINES = {
    'playgrabber.pipelines.FilterRecordedPipeline':   200,
    'playgrabber.pipelines.DownloaderPipeline':       800,
    'playgrabber.pipelines.RecordDownloadedPipeline': 900,
}

# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = 'playgrabber (+http://www.yourdomain.com)'

# Uncomment this for serial execution (easier to debug)
#CONCURRENT_REQUESTS = 1
