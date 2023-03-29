# -*- coding: utf-8 -*-

import json
import os

from apscheduler.schedulers.background import BackgroundScheduler
from flask import request

from rule.common.db.cache import redis_client, redis_client2
from rule.control.loader import app, logger
from rule.control.service import create_task, create_task_test
from rule.crawler.service import start_crawler
from rule.store.consumer import start_store
from twisted.internet import reactor

# from rule.common.DFA import GOSSIP_DFA

scheduler = BackgroundScheduler()

MAX_STORE_PROCESS = int(os.getenv('MAX_STORE_PROCESS', 9))
MAX_SPIDER_PROCESS = int(os.getenv('MAX_SPIDER_PROCESS', 8))


# web控制台
@app.route('/console')
def console():
    flag = request.args.get('flag')
    if flag in action:
        return action[flag]()
    logger.info('scheduler state : %d' % scheduler.state)
    return 'state: %d' % scheduler.state


# 入库服务配置，控制并发
@app.route('/store')
def store():
    flag = request.args.get('flag')
    _status = int(redis_client.get('STORE_RUN').decode('utf-8'))
    if flag == 'config':
        config = {}
        if int(redis_client.get('STORE_RUN').decode('utf-8')) == 1:
            _article_list_count = redis_client.llen('article_list')
            _process_count = int(_article_list_count / 150)
            if _process_count == 0:
                _process_count = 1
        else:
            config['run'] = False
            _process_count = 0
        if _process_count > MAX_STORE_PROCESS:
            _process_count = MAX_STORE_PROCESS
            if len(redis_client.keys('store_server:*')) > 0:
                _process_count = int(_process_count / len(redis_client.keys('store_server:*')))
        config['process_count'] = _process_count
        return json.dumps(config)
    elif flag == 'start':
        return store_start()
    elif flag == 'stop':
        return store_stop()
    return 'STORE_RUN: {0} {1}'.format('开启' if _status == 1 else '暂停',
                                       """<p><a href='/store?flag={0}'>{1}</a></p>""".format(
                                           'stop' if _status == 1 else 'start', '暂停' if _status == 1 else '开启'))


# 爬虫服务配置，控制并发
@app.route('/spider')
def spider():
    flag = request.args.get('flag')
    _status = int(redis_client.get('SPIDER_RUN').decode('utf-8'))
    if flag == 'config':
        config = {}
        if int(redis_client.get('SPIDER_RUN').decode('utf-8')):
            _article_list_count = redis_client.llen('spider_config')
            _process_count = int(_article_list_count / 200)
            if _process_count == 0:
                _process_count = 1
        else:
            config['run'] = False
            _process_count = 0
        if _process_count > MAX_STORE_PROCESS:
            _process_count = MAX_STORE_PROCESS
            if len(redis_client.keys('spider_server:*')) > 0:
                _process_count = int(_process_count / len(redis_client.keys('spider_server:*')))
        config['process_count'] = _process_count
        return json.dumps(config)
    elif flag == 'start':
        return spider_start()
    elif flag == 'stop':
        return spider_stop()
    return 'SPIDER_RUN: {0} {1}'.format('开启' if _status == 1 else '暂停',
                                        """<p><a href='/spider?flag={0}'>{1}</a></p>""".format(
                                            'stop' if _status == 1 else 'start', '暂停' if _status == 1 else '开启'))


@app.route('/bot')
def bot():
    redis_client.setex('bot_process', 1, 2000)
    return 'ok'


# 入库和爬虫状态
@app.route('/state')
def state():
    status = {}
    _spiders = redis_client.keys('spider_server:*')
    _sp = []
    for s in _spiders:
        _sp.append(s.decode('utf-8'))
    status['爬虫服务'] = _sp
    _stores = redis_client.keys('store_server:*')
    _st = []
    for s in _stores:
        _st.append(s.decode('utf-8'))
    status['入库服务'] = _st
    status['爬虫状态'] = '开启' if int(redis_client.get('SPIDER_RUN').decode('utf-8')) == 1 else '暂停'
    status['入库状态'] = '开启' if int(redis_client.get('STORE_RUN').decode('utf-8')) == 1 else '暂停'
    status['来源数'] = len(redis_client.keys('spider_pos*'))
    status['BGC队列'] = redis_client.llen('spider_config')
    status['入库队列'] = redis_client.llen('article_list')
    status['文章缓存'] = []
    status['控制台'] = ['http://172.16.1.9:5000/store', 'http://172.16.1.9:5000/spider']
    status['bot'] = redis_client.exists('bot_process')
    _cache_source_keys = redis_client.keys('article_list_cache:*')
    status['bot_c'] = len(redis_client.keys('comment_list*'))
    for key in _cache_source_keys:
        status['文章缓存'].append({
            key.decode('utf-8'): redis_client.llen(key)
        })
    return json.dumps(status)


# 恢复服务
def sche_start():
    logger.info('restart scheduler')
    scheduler.resume()


# 暂停服务
def sche_stop():
    logger.info('pause   scheduler')
    scheduler.pause()


# 爬虫暂停
def spider_stop():
    redis_client.set('SPIDER_RUN', 0)
    return 'SPIDER_RUN: {0}'.format(0)


# 爬虫启动
def spider_start():
    redis_client.set('SPIDER_RUN', 1)
    return 'SPIDER_RUN: {0}'.format(1)


# 入库暂停
def store_stop():
    redis_client.set('STORE_RUN', 0)
    return 'STORE_RUN: {0}'.format(0)


# 入库启动
def store_start():
    redis_client.set('STORE_RUN', 1)
    return 'STORE_RUN: {0}'.format(1)


action = {
    'start': sche_start,
    'stop': sche_stop,
    'spider_stop': spider_stop,
    'spider_start': spider_start,
    'store_stop': store_stop,
    'store_start': store_start
}

redis_client.set('CRAWLER_RUN', 1)
redis_client.set('STORE_RUN', 1)

# 启动服务
# if __name__ == '__main__':
logger.info('server start mode: %s', os.getenv('RUN_MODE', 'dev'))
# 定时执行
if os.getenv('RUN_MODE') == 'production':
    # 加载爬取任务
    try:
        # scheduler.add_job(create_task, 'cron', second='0', minute='0',
        #                   hour='2,4,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23')
        scheduler.add_job(create_task, 'cron', second='0', minute='*/30')
        scheduler.start()
        start_crawler()
        start_store()
        logger.info('| scheduler start |')
        reactor.run()
    except KeyboardInterrupt as e:
        scheduler.shutdown()
else:
    logger.info('run DEV 。。。')
    create_task_test('7')
    start_crawler()
    # start_store()
    logger.info('all service start 。。。')
    reactor.run()


