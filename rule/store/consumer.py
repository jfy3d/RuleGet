# -*- coding: utf-8 -*-
import json
import multiprocessing
import os
import socket
import threading
import time
import traceback

import settings

from rule.common.db.cache import redis_client
from rule.store.loader import store_logger as logger
from rule.common.record import record_error
from pymysql.err import IntegrityError, OperationalError
import os
import requests
import socket
import multiprocessing
from multiprocessing import cpu_count

CLASS_MAP = []
PACKAGE_MAP = {}

"""
获取处理器
"""
pool = None


def get_class(classname):
    _class = classname
    _path = _class.split('.')
    _module = '.'.join(_path[:-1])
    _module = '%s' % _module
    _name = _path[-1]
    if not CLASS_MAP.__contains__(_class):
        PACKAGE_MAP[_module] = __import__(_module, {}, {}, _name)
        CLASS_MAP.append(_class)
    return getattr(PACKAGE_MAP[_module], _name)


class Consumer:
    db_alive = True
    pool = None
    last_time = time.time()

    def __init__(self):
        myname = socket.getfqdn(socket.gethostname())
        # self.my_ip = socket.gethostbyname(myname)
        # th = threading.Thread(target=Consumer.alive, args=(self,))
        # th.setDaemon(True)
        # th.start()
        logger.info('Consumer init ...')

    def alive(self):
        global pool
        while True:
            # redis_client.setex('store_server:{0}_{1}'.format(self.my_ip, os.getpid()), '1', 70)
            time.sleep(60)
            stop_time = time.time() - self.last_time
            if stop_time > 600:
                pool.terminate()
                self.live_process()

    """
    订阅数据
    """

    def subscribe(self):
        logger.info('get from queue')
        self.live_process()

    def add_process(self, entity_list):
        self.pool = multiprocessing.Pool(processes=len(entity_list))
        for entity in entity_list:
            self.pool.apply_async(Consumer.store, (self, entity))
        self.pool.close()
        self.pool.join()

    def add_thread(self, entity_list):
        for _entity in entity_list:
            th = threading.Thread(target=Consumer.store, args=(self, _entity))
            th.setDaemon(True)
            th.start()
        th.join()

    # 进程方式
    def live_process(self):
        # global pool
        _process_count = cpu_count() + 1
        if _process_count > settings.MAX_PROCESS:
            _process_count = settings.MAX_PROCESS
        pool = multiprocessing.Pool(processes=_process_count)
        for _ in range(_process_count):
            pool.apply_async(Consumer.runner, (self,))
        pool.close()
        # pool.join()

        logger.info('pool create %s', _process_count)

    def process_callback(self):
        _entity = redis_client.rpop(settings.ARTICLE_QUEUE_KEY)
        if _entity:
            self.pool.apply_async(Consumer.store, (self, _entity))

    def runner(self):
        logger.info('create runner')
        while True:
            # redis_client.setex('store_server:{0}_{1}'.format(self.my_ip, os.getpid()), '1', 900)
            self.last_time = time.time()
            if get_max_process() > 0:
                _entity = redis_client.rpop(settings.ARTICLE_QUEUE_KEY)
                if _entity:
                    try:

                        # self.store(_entity)
                        proxy_run(self, _entity)

                    except:
                        logger.error('处理文章异常')
                        logger.error(traceback.format_exc())
                else:
                    time.sleep(20)
            else:
                time.sleep(20)
        return True

    """
    存储处理
    """

    def store(self, entity):
        # 对内容过滤
        _start_time = time.time()
        _entity_obj = json.loads(entity)
        try:
            for _filter_path in settings.ITEM_FILTER:
                _filter_class = get_class(_filter_path)
                _filter = _filter_class()
                # 如果触发过滤规则，中断丢掉文章不入库
                if not _filter.filter_item(_entity_obj):
                    logger.warning(_filter_path)
                    logger.warning('<%s> [%s] [%s] %s 未通过过滤规则丢弃 ', _entity_obj['_config']['id'], _entity_obj['id'],
                                   _entity_obj['title'],
                                   _entity_obj['source_url'])
                    return False
        except:
            logger.error('过滤异常！！！！！！')
            _error = traceback.format_exc()
            logger.error(_error)
            logger.error('<%s> [%s] [%s] %s 过滤异常 ', _entity_obj['_config']['id'], _entity_obj['id'],
                           _entity_obj['title'],
                           _entity_obj['source_url'])
            return False


        logger.info('<%s> [%s]  过滤耗时: %s', _entity_obj['_config']['id'], _entity_obj['id'],
                    time.time() - _start_time)
        try:
            processor_class = get_class(_entity_obj['_config']['processor'])
            processor = processor_class(_entity_obj)
            processor.save()
            logger.info('<%s> [%s]  完成处理耗时: %s', _entity_obj['_config']['id'], _entity_obj['id'],
                        time.time() - _start_time)
        except OperationalError as e:
            self.return_queue(entity)
            logger.error('发生异常文章放回队列 %s %s %s', _entity_obj['id'], _entity_obj['title'],
                         _entity_obj['original_url'])
            _error = traceback.format_exc()
            logger.error(_error)
            record_error('入库失败 {0} {1} {2} \n\n {3}'.format(_entity_obj['_config']['id'], _entity_obj['id'], _entity_obj['title'], _error))
            time.sleep(2)
        except OSError as e:
            _error = traceback.format_exc()
            logger.error('入库失败 {0} {1} {2} \n\n {3}'.format(_entity_obj['_config']['id'], _entity_obj['id'], _entity_obj['title'], _error))
            record_error('入库失败 {0} {1} \n\n {2}'.format(_entity_obj['id'], _entity_obj['title'], _error))
            time.sleep(2)
        except IntegrityError as e:
            _error = traceback.format_exc()
            logger.error('入库失败 {0} {1} {2} \n\n {3}'.format(_entity_obj['_config']['id'], _entity_obj['id'], _entity_obj['title'], _error))
            record_error('入库失败 {0} {1} \n\n {2}'.format(_entity_obj['id'], _entity_obj['title'], _error))
            time.sleep(2)
        except ModuleNotFoundError as e:
            self.return_queue(entity)
            _error = traceback.format_exc()
            logger.error('入库失败 {0} {1} {2} \n\n {3}'.format(_entity_obj['_config']['id'], _entity_obj['id'], _entity_obj['title'], _error))
            record_error(
                'ModuleNotFoundError 入库失败 {0} {1} \n\n {2}'.format(_entity_obj['id'], _entity_obj['title'],
                                                                                _error))
        except KeyboardInterrupt as e:
            logger.warning("KeyboardInterrupt 中断进程 消息回归队列")
            if _entity_obj:
                self.return_queue(_entity_obj)
        except TypeError as e:
            _error = traceback.format_exc()
            logger.warning("TypeError 中断进程 消息回归队列")
            record_error(
                'ModuleNotFoundError 入库失败 {0} {1} \n\n {2}'.format(_entity_obj['id'], _entity_obj['title'],
                                                                                _error))
        except:
            _error = traceback.format_exc()
            logger.warning("except default 中断进程 消息回归队列")
            record_error(
                'except 入库失败 {0} {1} \n\n {2}'.format(_entity_obj['id'], _entity_obj['title'],
                                                                   _error))

    def return_queue(self, entity):
        entity['fail_return'] = 1
        redis_client.lpush(settings.ARTICLE_QUEUE_KEY, entity)

    """
    队列里获取
    """

    def load(self):
        _list = []
        _count = 0
        logger.info('start load >>> fetch')
        _max_process = int(get_max_process())
        while _count < _max_process and self.db_alive:
            _entity = redis_client.rpop(settings.ARTICLE_QUEUE_KEY)
            if _entity is None:
                break
            else:
                _list.append(_entity)
                _count += 1
        if _count > 0:
            logger.info('%d item get ..', len(_list))
        return _list


def proxy_run(c, entity):
    c.store(entity)


# 获取启动进程数
def get_max_process():
    if os.getenv('RUN_MODE', 'dev') == 'dev':
        return settings.MAX_PROCESS
    center_url = 'http://{0}:5000/store?flag=config'.format(settings.REDIS_HOST)
    try:
        return settings.MAX_PROCESS
        response = requests.get(center_url, timeout=8)
        # if response.status_code == 200:
        #     _obj = json.loads(response.content)
        #     logger.info(_obj)
        #     _count = int(_obj['process_count'])
        #     if _count > settings.MAX_PROCESS:
        #         return settings.MAX_PROCESS
        #     else:
        #         return _count
    except:
        logger.error(traceback.format_exc())
        return settings.MAX_PROCESS
    return settings.MAX_PROCESS


def start_store():
    # app_load()
    # 创建队列订阅，处理队列中的文章
    consumer = Consumer()
    consumer.subscribe()
    logger.info('article store start !')