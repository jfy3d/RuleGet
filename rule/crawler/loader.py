# -*- coding: utf-8 -*-

import logging

from rule.common.func import setup_logger

setup_logger('crawler', 'crawler.log', format='%(asctime)s %(filename)s %(lineno)d %(levelname)s %(message)s')

crawler_logger = logging.getLogger('crawler')


def record_duplicate(crawler_id, title, url, remark=''):
    crawler_logger.info(u'DUP | %s | %s | %s | %s' % (crawler_id, url, title, remark))


# id 来源ID  title 文章标题   url 文章地址 9 标题有广告词
def record_ad(crawler_id, title, url, remark=''):
    crawler_logger.info(u'AD | %s | %s | %s | %s' % (crawler_id, url, title, remark))


# id 来源ID  title 文章标题   url 文章地址
def record_nopic(crawler_id, title, url):
    crawler_logger.warn(u'NOPIC | %s | %s | %s' % (crawler_id, url, title))


def record_cache(crawler_id, title, url):
    crawler_logger.info(u'CACHE | %s | %s | %s' % (crawler_id, url, title))


# id 来源ID  title 文章标题   url 文章地址
def record_filter(crawler_id, title, url):
    crawler_logger.info(u'FILTER | %s | %s | %s' % (crawler_id, url, title))


def record_fail(crawler_id, title, url, remark=''):
    crawler_logger.error(u'FAIL | %s | %s | %s' % (crawler_id, url, title))