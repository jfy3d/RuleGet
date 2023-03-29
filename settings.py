# -*- coding: utf-8 -*-
import os

REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = 6379
CONFIG_KEY = 'crawler_config'
CRAWLER_POS_KEY = 'crawler_pos:{0}'
LOG_PATH = os.getenv('LOG_PATH')
CRAWLER_ERROR_LIST_KEY = 'crawler_error_list'
ARTICLE_QUEUE_KEY = 'article_queue'

PROXY_SERVER = {
    'http': os.getenv('CRAWLER_PROXY'),
    'https': os.getenv('CRAWLER_PROXY')
}

# 注意 过滤器有执行顺序
ITEM_FILTER = [
    'rule.store.process.filter.base.SourceFilter',
    'rule.store.process.filter.base.WordFilter',
    'rule.store.process.filter.base.WordReplaceFilter',
    'rule.store.process.filter.base.ContentTagFilter',
    'rule.store.process.filter.base.SummaryFilter',
]

SUPPORT_IMG = ['PNG', 'JPEG', 'GIF', 'WEBP', 'JPG']

# 图片存储根目录
STORE_ROOT = os.getenv('STORE_ROOT')
# 图片相对路径
UPLOAD_PATH = os.getenv('UPLOAD_PATH')
# 图片访问域名
IMG_DOMAIN = os.getenv('IMG_DOMAIN')

MAX_PROCESS = 1
