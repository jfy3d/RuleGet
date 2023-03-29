# -*- coding: utf-8 -*-
import json
import time
from datetime import date
from datetime import datetime

from rule.common.db.cache import redis_client
from rule.common.db.database import conn_pool
from rule.common.func import CJsonEncoder
import settings
from rule.control.loader import logger



"""
加载来源
也可以是配置文件，需要和旧版程序区分
"""


def load_source():
    _now = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    _conn = conn_pool.get_conn()
    _cursor = _conn.cursor()
    _sql = """SELECT * FROM crawler_list WHERE now() BETWEEN begin_time AND end_time AND crawler<>'' AND flag_valid=1
         
         """
    _cursor.execute(_sql)
    _list = _cursor.fetchall()
    _conn.commit()
    _cursor.close()
    conn_pool.return_conn(_conn)
    return _list


def load_source_test(id):
    _now = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    _conn = conn_pool.get_conn()
    _cursor = _conn.cursor()
    _sql = """SELECT * FROM crawler_list where id='{0}'

         """.format(id)
    _cursor.execute(_sql)
    _list = _cursor.fetchall()
    _conn.commit()
    _cursor.close()
    conn_pool.return_conn(_conn)
    return _list

"""
来源配置加入redis队列
"""


def create_task():
    logger.info('start load source')
    _source_list = load_source()
    logger.info('load source : %d' % len(_source_list))
    for _source in _source_list:
        redis_client.lpush(settings.CONFIG_KEY, json.dumps(_source, cls=CJsonEncoder))
    logger.info('add queue finish')


def create_task_test(id):
    logger.info('start load source')
    _source_list = load_source_test(id)
    logger.info('load source : %d' % len(_source_list))
    for _source in _source_list:
        redis_client.lpush(settings.CONFIG_KEY, json.dumps(_source, cls=CJsonEncoder))
    logger.info('add queue finish')


