# -*- coding: UTF-8 -*-

import pymysql
import os
import threading
import oss2
from elasticsearch import Elasticsearch
import traceback
from DBUtils.PooledDB import PooledDB


auth = oss2.Auth(os.getenv('OSS_APPKEY'), os.getenv('OSS_APPSECRET'))
bucket = oss2.Bucket(auth, os.getenv('OSS_API'), os.getenv('OSS_BUCKET'))
es = Elasticsearch(os.getenv('ES_HOST'))

cfg = {
    'host': os.getenv('DB_HOST', ''),
    'database': 'crawler',
    'user': 'dev',
    'password': os.getenv('DB_PASS', ''),
    'mincached': 5,
    'maxcached': 30,
    'maxusage': 30,
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,
}


class ConnectionPool:
    pool = None

    def __init__(self):
        self.pool = PooledDB(pymysql, **cfg)

    def return_conn(self, conn):
        conn.close()

    def get_conn(self):
        try:
            return self.pool.connection()
        except Exception as e:
            return None


conn_pool = ConnectionPool()


def get_data_list(sql, params=None):
    _conn = conn_pool.get_conn()
    try:
        _cursor = _conn.cursor()
        _cursor.execute(sql, params)
        _list = _cursor.fetchall()
        _conn.commit()
        _cursor.close()
    except Exception as ex:
        print(ex)
        traceback.print_exc()
    finally:
        conn_pool.return_conn(_conn)
    return _list


def get_data(sql, param=None):
    _conn = conn_pool.get_conn()
    try:
        _cursor = _conn.cursor()
        _cursor.execute(sql, param)
        _data = _cursor.fetchone()
        _conn.commit()
        _cursor.close()
    except Exception as ex:
        print(ex)
        traceback.print_exc()
        return None
    finally:
        conn_pool.return_conn(_conn)
    return _data


def exec_sql(sql, param=None):
    _conn = conn_pool.get_conn()
    _result = True
    try:
        _cursor = _conn.cursor()
        _cursor.execute(sql, param)
        _conn.commit()
    except Exception as e:
        _conn.rollback()
        _result = False
    finally:
        if _cursor:
            _cursor.close()
        conn_pool.return_conn(_conn)
    return _result


def exec_sql(sql, param=None):
    _conn = conn_pool.get_conn()
    _result = True
    _cursor = None
    try:
        _cursor = _conn.cursor()
        _cursor.execute(sql, param)
        _conn.commit()
    except Exception as e:
        _conn.rollback()
        logger.error(sql)
        logger.error(traceback.format_exc())
        _result = False
    finally:
        if _cursor:
            _cursor.close()
        conn_pool.return_conn(_conn)
    return _result
