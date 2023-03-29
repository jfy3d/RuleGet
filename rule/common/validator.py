# -*- coding: UTF-8 -*-

import re

from .bloom_filter import BloomFilter

BF = BloomFilter()


def filter_pun(string):
    r = r"[\s+\.\!\n\t\r\/_,$%^*(+\"\')]+|[+——()?【】《》“”‘’;；＂！，。·？、:：～~@#￥%……&*（）]+"
    return re.sub(r, '', string)


# 校验链接 redis方式
def dupe_url_check(url):
    if url.endswith('/'):
        url = url[:-1]
    # _fingerprint = md5(url.encode('utf-8'))
    # added = redis_client.sadd('had_url_get', _fingerprint)
    return BF.has_item(url) is False


# 校验标题 redis方式
def dupe_title_check(title, channel=''):
    # 根据频道独立过滤
    return BF.has_item(title) is False


# 校验链接 True 不重复可以解析， False 重复放弃
def validate_url(url):
    if dupe_url_check(url) is False:
        return False
    return True


# 校验标题 todo
def validate_title(title, channel=''):
    if dupe_title_check(filter_pun(title), channel) is False:
        return False
    return True
