# -*- coding: utf-8 -*-

import logging

import jieba
from PIL import ImageFile
from jieba import analyse
from rule.common.DFA import dfa_init
from rule.common.func import setup_logger

ImageFile.LOAD_TRUNCATED_IMAGES = True

jieba.load_userdict('file/keywords.txt')
analyse.set_stop_words('file/stopwords.txt')

GAO_DOU_TAGS = []
GIRL_TAGS = []

KW_BF = None

setup_logger('store', 'store.log', format='%(asctime)s %(filename)s %(levelname)s %(message)s')

store_logger = logging.getLogger('store')

def app_load():
    pass
    # dfa_init()