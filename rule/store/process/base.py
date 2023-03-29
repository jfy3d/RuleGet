# -*- coding: utf-8 -*-
import json
import os
import random
import re
import time
import traceback
from urllib.parse import urljoin

import MySQLdb
import requests
from PIL import Image
from PIL import ImageFile
from pymysql.err import IntegrityError, OperationalError
from requests.adapters import HTTPAdapter
from requests.exceptions import ProxyError
from scrapy import Selector
from urllib3.exceptions import MaxRetryError

import settings
from rule.common.data import USER_AGENTS
from rule.common.db.cache import redis_client
from rule.common.db.database import bucket
from rule.common.face import get_crop_by_face
from rule.common.func import is_valid_jpg
from rule.common.func import md5, count_qrcode, get_rnd_id, get_filename_ext
from rule.store.loader import store_logger as logger

ImageFile.LOAD_TRUNCATED_IMAGES = True

WATER_MARK = '?x-oss-process=style/wm'


class Processor(object):
    attach_list = []
    img_tag_re = '<img.*? src="([^""]*)".*?>'
    min_thumb_width = 240
    min_thumb_height = 180
    img_quality = 75
    thumb_keep_gif = False

    def __init__(self, entity):
        self.entity = entity
        self.attach_list = []
        self.db_name = self.entity['_config']['db']
        self.index = 0
        # 区分大图模式， 大图模式git不做缩略图处理
        if entity.get('channel') in ['美女', '搞逗', '美图']:
            self.thumb_keep_gif = True
        else:
            self.thumb_keep_gif = False
        if entity.get('content_type', '1') == 2:
            self.img_tag_re = '<img.*? src="([^""]*)".*?><spilt>'

    def headers(self):
        headers = {
            "Accept": "image/png,image/svg+xml,image/jpeg,image/gif;q=0.8,video/*;q=0.8,*/*;q=0.5",
            "Accept-Encoding": "deflate, sdch",
            "Accept-Language": "zh-CN,zh;q=0.8",
            "Connection": "keep-alive",
        }
        headers['User-Agent'] = USER_AGENTS[random.randint(0, len(USER_AGENTS) - 1)]
        headers['Referer'] = self.entity.get('original_url', '')
        return headers

    def parse_article(self):
        logger.info('<%s> [%s] 处理文章 : %s %s', self.entity['_config'].get('id'), self.entity['id'], self.entity['title'],
                    self.entity.get('original_url'))

        article = {
            'id': self.entity['id'],
            'title': self.entity['title'],

            'summary': self.entity.get('summary'),
            'channel': self.entity.get('channel'),
            'article_tag': self.entity.get('article_tag'),
            'keywords': self.entity.get('keywords'),
            'source': self.entity.get('source', self.entity.get('_config').get('account')),
            'source_url': self.entity.get('source_url'),
            'app_url': self.entity.get('app_url', ''),
            # 'app_url': u'http://haowai.com/a/{0}'.format(self.entity['id']),
            'comment_count': self.entity.get('comment_count', 0),
            'author_id': self.entity.get('author_id'),
            'content_type': self.entity.get('content_type', '1'),
            'read_count': self.entity.get('read_count', 0),
            'mark_count': self.entity.get('mark_count', 0),
            'createdate': self.entity.get('createdate'),
            'flag_status': self.entity.get('flag_status', 0),  # flag_status默认是0
            'flag_delete': self.entity.get('flag_delete', 0),
            'share_count': self.entity.get('share_count', 0),
            'flag_comment': self.entity.get('flag_comment', 0),
            'flag_valid': self.entity.get('flag_valid', 0),
            'interception': int(self.entity.get('interception', self.entity.get('_config').get('interception'))),
            'sensitive': self.entity.get('sensitive', '0'),
            'edit': self.entity.get('edit', 0),
            'img_count': self.entity.get('img_count', 0),  # todo
            'operator': self.entity.get('operator', ''),
            # 'source_type': self.entity.get('source', self.entity.get('_config').get('source')),
            'source_type': self.entity.get('_config').get('source'),
            'flag_author': self.entity.get('flag_author', '可忽略'),
            'article_type': self.entity.get('article_type', 0),
            'operator_second': self.entity.get('operator_second', ''),
            'redis': self.entity.get('redis', 0),
            'recmd': self.entity.get('recmd', -1),
            'get_time': self.entity.get('get_time'),
            'gossip': self.entity.get('gossip', ''),
            'summary_tag': self.entity.get('summary_tag', ''),
            'recommend_count': self.entity.get('recommend_count', 0)
        }
        logger.info('图片提取正则 %s', self.img_tag_re)
        article['content'] = re.sub(self.img_tag_re, self.fetch_image, self.entity['content'])
        # 判断美图、搞逗的图片数量
        if self.thumb_keep_gif:
            content_img = Selector(text=article['content'])
            img_count = content_img.xpath('//img').extract()
            article['img_count'] = len(img_count)
        if self.entity.get('content_type', '1') == 2:
            article['content'] = re.sub('<hr>  <hr>','<hr>',article['content'])
        logger.info('<%s> [%s] 文章处理完成: %s', self.entity['_config'].get('id'), self.entity['id'], self.entity['title'])
        return article

    # 保存到 Elasticsearch
    def save_es(self, article):
        # ES 需要转日期格式
        _start_time = time.time()
        body = article.copy()
        del body['gossip']
        body['createdate'] = body['createdate'].replace(' ', 'T')
        body['get_time'] = body['get_time'].replace(' ', 'T')
        # r = esdb.index(index="idx_article", doc_type='article', id=article['id'], body=body)
        # logger.info('<%s> [%s] 文章保存到ES: %s r: %s time: %s', self.entity['_config'].get('id'), article['id'],
        #             article['title'], r
        #             , time.time() - _start_time)

    # 图片存储到OSS
    # file_path 本地路径  uri oss 存放路径
    # uri 首字母不能加 /
    def upload_oss(self, file_path, uri):
        _start_time = time.time()
        if uri.startswith('/'):
            uri = uri[1:]
        try:
            result = bucket.put_object_from_file(uri, file_path)
            logger.info('<%s> [%s] 文件保存到 oss: %s time: %s %s', self.entity['_config'].get('id'), self.entity['id'],
                        file_path, time.time() - _start_time,
                        result.status)
        except Exception as e:
            logger.error('<%s> [%s] 文件保存到 OSS 异常', self.entity['_config'].get('id'), self.entity['id'])
            logger.error(traceback.format_exc())
            try:
                time.sleep(3)
                result = bucket.put_object_from_file(uri, file_path)
                logger.info('<%s> [%s] 重试 文件保存到 oss: %s time: %s %s', self.entity['_config'].get('id'),
                            self.entity['id'], file_path,
                            time.time() - _start_time, result.status)
            except Exception as e:
                logger.error('<%s> [%s] 文件保存到 OSS 再次异常', self.entity['_config'].get('id'), self.entity['id'])
                logger.error(traceback.format_exc())
                return False
        return result

    # 存储到数据库
    def save(self):
        is_success = False
        article = self.parse_article()
        if len(self.attach_list) == 0:
            logger.error('无图')
            return False

        # 存入反查列表状态判断
        if self.db_name == 'haowai':
            self.entity['_config']['status'] = 5
        else:
            self.entity['_config']['status'] = 4
        # 入库前再次确定文章内容有图片
        content_img = Selector(text=article['content'])
        img_count = content_img.xpath('//img').extract()
        if len(img_count) == 0 or len(self.attach_list) == 0:

            logger.error('<%s> [%s] 正文检查无图片 ', self.entity['_config'].get('id'), article['id'])
            return False
        article['img_count'] = len(img_count)
        # conn = conn_pool.get_conn()
        conn = MySQLdb.connect(host=os.getenv('DB_HOST', 'hwdbhost'),
                               port=3306,
                               user='hw',
                               passwd=os.getenv('DB_PASS', ''),
                               db='haowai',
                               charset='utf8')
        cursor = None
        try:
            cursor = conn.cursor()
            if self.db_name == 'haowai':
                _sql = 'INSERT INTO ' + self.db_name + '.article(' \
                                                       'id,title,content,summary,channel,article_tag,' \
                                                       'keywords,source,source_url,app_url,comment_count,author_id,' \
                                                       'content_type,read_count,mark_count,createdate,flag_status,flag_valid,' \
                                                       'flag_delete,share_count,flag_comment,interception,`sensitive`,edit,' \
                                                       'img_count,operator,get_time,source_type,flag_author,article_type,' \
                                                       'operator_second,redis,recmd,recommend_count)' \
                                                       'VALUES(%s,%s,%s,%s,%s,%s,' \
                                                       '%s,%s,%s,%s,%s,%s,' \
                                                       '%s,%s,%s,%s,%s,%s,' \
                                                       '%s,%s,%s,%s,%s,%s,' \
                                                       '%s,%s,%s,%s,%s,%s,' \
                                                       '%s,%s,%s,%s)'
                _param = (
                    article['id'], article['title'], article['content'],
                    article['summary'], article['channel'], article['article_tag'],
                    article['keywords'], article['source'], article['source_url'],
                    article['app_url'], int(article['comment_count']), article['author_id'],
                    article['content_type'], int(article['read_count']), int(article['mark_count']),
                    article['createdate'], int(article['flag_status']), int(article['flag_valid']),
                    int(article['flag_delete']), int(article['share_count']), int(article['flag_comment']),
                    article['interception'], article['sensitive'], int(article['edit']),
                    int(article['img_count']), article['operator'], article['get_time'],
                    article['source_type'], article['flag_author'], article['article_type'],
                    article['operator_second'], int(article['redis']), article['recmd'], article['recommend_count']
                )

            else:
                _sql = 'INSERT INTO ' + self.db_name + '.article(' \
                                                       'id,title,content,summary,channel,article_tag,' \
                                                       'keywords,source,source_url,comment_count,author_id,' \
                                                       'content_type,read_count,mark_count,createdate,flag_status,flag_valid,' \
                                                       'flag_delete,flag_comment,interception,`sensitive`,edit,' \
                                                       'img_count,get_time,source_type,flag_author,' \
                                                       'redis,recmd)' \
                                                       'VALUES(%s,%s,%s,%s,%s,%s,' \
                                                       '%s,%s,%s,%s,%s,' \
                                                       '%s,%s,%s,%s,%s,%s,' \
                                                       '%s,%s,%s,%s,%s,' \
                                                       '%s,%s,%s,%s,' \
                                                       '%s,%s)'
                _param = (
                    article['id'], article['title'], article['content'],
                    article['summary'], article['channel'], article['article_tag'],
                    article['keywords'], article['source'], article['source_url'],
                    int(article['comment_count']), article['author_id'],
                    article['content_type'], int(article['read_count']), int(article['mark_count']),
                    article['createdate'], int(article['flag_status']), int(article['flag_valid']),
                    int(article['flag_delete']), int(article['flag_comment']),
                    article['interception'], article['sensitive'], int(article['edit']),
                    int(article['img_count']), article['get_time'],
                    article['source_type'], article['flag_author'],
                    int(article['redis']), article['recmd'],
                )

            # todo 完成参数

            cursor.execute(_sql,
                           _param
                           )

            for attach in self.attach_list:
                _sql = 'INSERT INTO ' + self.db_name + \
                       '.article_attach(id,file_type,file_path,article_id,img_width,img_height)'
                _sql = _sql + 'VALUES(%s,%s,%s,%s,%s,%s)'
                cursor.execute(_sql,
                               (
                                   get_rnd_id(), attach['file_type'], attach['file_path'],
                                   article['id'], attach['img_width'], attach['img_height']
                               )
                               )
                logger.info(attach)
                if len(self.attach_list) == 2:
                    break
            conn.commit()
            if self.db_name == 'haowai':
                self.save_es(article)

            is_success = True
            logger.info('<%s> [%s] 文章入库 : %s %s', self.entity['_config']['id'], article['id'], self.db_name,
                        article['title'])
        except IntegrityError as e:
            traceback.print_exc()
            logger.error('<%s> [%s] 文章入库错误 IntegrityError %s', self.entity['_config']['id'], article['id'],
                         article['title'])
            logger.error(traceback.format_exc())
            logger.warning(_param)
            conn.rollback()


        except OperationalError as e:
            traceback.print_exc()
            logger.error('<%s> [%s] 文章入库错误 OperationalError %s', self.entity['_config']['id'], article['id'],
                         article['title'])
            logger.error(traceback.format_exc())
            logger.warning(_param)
            logger.warning(self.attach_list)
            conn.rollback()
            self.entity['fail_return'] = 1
            redis_client.lpush(settings.ARTICLE_QUEUE_KEY, json.dumps(self.entity))
            logger.error('<%s> [%s] 文章入库错误 返还队列 %s %s', self.entity['_config'].get('id'), self.entity['id'],
                         self.entity['title'],
                         self.entity['original_url'])
        except Exception as ef:
            logger.error(ef)
            conn.rollback()
            logger.error('<%s> [%s] 文章入库错误  Exception: %s', self.entity['_config']['id'], article['id'],
                         article['title'])
            logger.error('其他错误')
            logger.error(traceback.format_exc())

        finally:

            if cursor:
                cursor.close()
            conn.close()
        return is_success

    # 下载图片
    def download_image(self, url):
        logger.info('<%s> [%s] 开始下载图片 >> %s', self.entity['_config'].get('id'), self.entity['id'], url)
        _start_time = time.time()
        request = requests.Session()
        request.mount('http://', HTTPAdapter(max_retries=3))
        request.mount('https://', HTTPAdapter(max_retries=3))
        r = request.get(url, stream=True, headers=self.headers(), proxies=settings.PROXY_SERVER, timeout=90)
        _content_type = r.headers.get('content-type', 'image/jpg')
        _file_size = -1
        _value_len = r.headers.get('content-length', '')
        if _value_len.isdigit():
            _file_size = int(_value_len)
        logger.info('<%s> [%s] download image >> %s size:%s', self.entity['_config'].get('id'), self.entity['id'], url,
                    _file_size)
        if r.status_code != 200 or (0 < _file_size != len(r.content)) or \
                (_file_size == -1 and get_filename_ext(url, _content_type) == 'jpg' and not is_valid_jpg(r.content)):
            time.sleep(1)
            logger.error('<%s> [%s] 图片下载状态 code : %s %s size:%s', self.entity['_config'].get('id'), self.entity['id'],
                         r.status_code, url,
                         r.headers.get('content-length', -1))
            r = request.get(url, stream=True, headers=self.headers(), proxies=settings.PROXY_SERVER, timeout=90)
            logger.info('<%s> [%s] 重新 图片下载状态 %s', self.entity['_config'].get('id'), self.entity['id'], r.status_code)
            _file_size = -1
            _value_len = r.headers.get('content-length', '')
            if _value_len.isdigit():
                _file_size = int(_value_len)
            if r.status_code != 200 or (0 < _file_size != len(r.content)):
                logger.error('<%s> [%s] 图片下载状态 再次失败 size: %s', self.entity['_config'].get('id'), self.entity['id'],
                             r.headers.get('content-length', -1))

            else:
                logger.info('<%s> [%s] 图片重新下载成功 -- %s', self.entity['_config'].get('id'), self.entity['id'], url)
                return r
        else:
            logger.info('<%s> [%s] 图片下载耗时: %s', self.entity['_config'].get('id'), self.entity['id'],
                        time.time() - _start_time)
            return r

        return None

    def create_dir(self, path):
        if not os.path.exists(path):
            logger.info('<%s> [%s] 创建目录 %s', self.entity['_config'].get('id'), self.entity['id'], path)
            os.makedirs(path)
            os.system('chmod -R 777 {0}'.format(path))

    # 使用OSS方式缩略图
    def thumb_image(self, url, thumb_w, thumb_h, format, src_path, width, height):
        logger.info('<%s> [%s] 生成缩略图 %s', self.entity['_config'].get('id'), self.entity['id'], src_path)
        _format_param = ''
        if self.thumb_keep_gif:
            return url
        if format == 'GIF':
            if not self.thumb_keep_gif:
                _format_param = '/format,jpg'
        _crop_param = ''
        if not self.thumb_keep_gif:
            _face_start = time.time()
            location = None
            try:
                location = get_crop_by_face(src_path, width, height, thumb_w, thumb_h)
                logger.info('<%s> [%s] 人脸识别 : %s', self.entity['_config'].get('id'), self.entity['id'],
                            time.time() - _face_start)
            except MemoryError as e:
                logger.error('人脸截取 --MemoryError--')
                logger.error(traceback.format_exc())
            except:
                logger.error('人脸截取 --timeout--')
                logger.error(traceback.format_exc())
            if location is not None:
                _x, _y, _w, _h = location
                _crop_param = '/crop,x_{0},y_{1},w_{2},h_{3}'.format(_x, _y, _w, _h)
        _resise_param = '/resize,m_fill,h_{0},w_{1}'.format(thumb_h, thumb_w)
        _thumb_link = '{0}?x-oss-process=image{1}{2}{3}'.format(url, _crop_param, _resise_param, _format_param)
        return _thumb_link

    def base_url(self):
        return self.entity.get('original_url')

    """
    正则批处理图片
    """

    def fetch_image(self, matched):
        logger.info('<%s> [%s] 获取图片 >> %s', self.entity['_config'].get('id'), self.entity['id'], 'fetch_image')
        _start_time = time.time()
        tag = matched.group()
        src = matched.group(1)
        # 判断是否是智能分发
        if src.startswith('http'):
            logger.info('<%s> [%s] 原地址 %s', self.entity['_config'].get('id'), self.entity['id'], src)
            url = src
        else:
            url = urljoin(self.base_url(), src)
            logger.info('<%s> [%s] 结合地址 %s %s', self.entity['_config'].get('id'), self.entity['id'], src, url)
        article_id = self.entity['id']
        _content_type = ''
        try:
            r = self.download_image(url)
            if r is None:
                return ''
            _content_type = r.headers.get('content-type', 'image/jpg')
        except (MaxRetryError, ProxyError) as re:
            logger.error(traceback.format_exc())
            try:
                r = self.download_image(url)
            except:
                return ''
        except Exception as e:
            logger.error('<%s> [%s] 图片下载失败 !! %s', self.entity['_config'].get('id'), self.entity['id'], url)
            logger.error(traceback.format_exc())
            return ''
        # 处理
        filename = "{0}_{1}.{2}".format(article_id, md5(url.encode("utf-8")), get_filename_ext(src, _content_type))
        dpath = time.strftime('%Y%m%d')
        _real_dir = '%s%s/cache/%s' % (
            settings.STORE_ROOT, settings.UPLOAD_PATH, dpath
        )

        _real_path = '%s%s/cache/%s/%s' % (
            settings.STORE_ROOT, settings.UPLOAD_PATH, dpath, filename
        )

        self.create_dir(_real_dir)

        link = '%s%s/cache/%s/%s' % (
            settings.IMG_DOMAIN, settings.UPLOAD_PATH, dpath, filename
        )

        _start_time_write = time.time()
        logger.info('<%s> [%s] 图片写入磁盘 %s', self.entity['_config'].get('id'), self.entity['id'], _real_path)
        with open(_real_path, 'wb') as fd:
            fd.write(r.content)
            # for chunk in r.iter_content(chunk_size=4096):
            #     fd.write(chunk)
            fd.close()

        logger.info('<%s> [%s] 图片写入 %s %s 耗时: %s', self.entity['_config'].get('id'), self.entity['id'], url,_real_path,
                    time.time() - _start_time_write)

        try:
            img = Image.open(_real_path)
            if img.mode != 'RGB' and img.format != 'GIF':
                img = img.convert('RGB')
        except Exception as e:
            logger.error('<%s> [%s] 图片打开失败 : %s %s %s %s', self.entity['_config'].get('id'), self.entity['id'],
                         _real_path, url,
                         self.entity['original_url'], src)
            logger.error(traceback.format_exc())
            return ''

        if count_qrcode(img) > 0:
            logger.info('<%s> [%s] 发现含有二维码图片 : %s from article %s %s', self.entity['_config'].get('id'),
                        self.entity['id'],
                        url, article_id, self.entity['source_url'])
            os.remove(_real_path)
            return ''

        iw, ih = img.size
        logger.info('<%s> [%s] w:%d h:%d format: %s', self.entity['_config'].get('id'), self.entity['id'], iw, ih,
                    img.format)

        if img.format not in settings.SUPPORT_IMG:
            logger.warning('{0} 不支持的图片格式 {1} {2}'.format(img.format, url, _real_path))

        _resize = False

        if (['PNG', 'JPEG', None].__contains__(img.format) and iw > 1000) or img.format == 'WEBP':
            _start_convert_time = time.time()
            cp_cmd = 'cp {0} {1}.bak'.format(_real_path, _real_path)
            os.system(cp_cmd)
            cmd = 'convert {0} +antialias -quality {1} -resize "1000" {2}' \
                .format(_real_path, self.img_quality, _real_path)
            os.system(cmd)
            _resize = True
            logger.info("<%s> [%s] 超大图片缩小 %s time: %s", self.entity['_config'].get('id'), self.entity['id'], _real_path,
                        time.time() - _start_convert_time)

        if self.entity['_config'].get('img_margin', '') != '' and img.format != 'GIF':
            _cut_size = self.entity['_config'].get('img_margin', '')

            if _resize:
                img = Image.open(_real_path)
            iw_one, ih_one = img.size
            _top = 0
            _bottom = ih_one
            _left = 0
            _right = 0
            if _cut_size.find('|') > 0:
                _left, _top, _right, _bottom = _cut_size.strip().split('|')
                if _left.find('.') > 0:
                    _left = int(float(_left) * iw_one)
                if _top.find('.') > 0:
                    _top = int(float(_top) * ih_one)
                if _right.find('.') > 0:
                    _right = int(float(_right) * iw_one)
                if _bottom.find('.') > 0:
                    _bottom = int(float(_bottom) * ih_one)
            else:
                if _cut_size.startswith('top'):
                    _top = int(_cut_size.split('_')[1])
                else:
                    _bottom = int(_cut_size.split('_')[1])
            region = img.crop((int(_left), int(_top), iw_one - int(_right), ih_one - int(_bottom)))
            iw = iw_one - int(_right)
            ih = ih_one - int(_bottom)
            region.save(_real_path)
            logger.info('<%s> [%s] 图片去水印截取  %s -resize %s  %s w %s h %s', self.entity['_config'].get('id'),
                        self.entity['id'], _real_path, _cut_size,
                        self.entity['source_url'], iw, ih)

        ur = self.upload_oss(_real_path, link.replace(settings.IMG_DOMAIN, '')[1:])

        while not ur:
            time.sleep(300)
            ur = self.upload_oss(_real_path, link.replace(settings.IMG_DOMAIN, '')[1:])


        _img_format = img.format
        if _img_format is None:
            _img_format = get_filename_ext(url, _content_type).upper()
            logger.warning('[{0}] >>> 指定新扩展名 {1} {2}'.format(self.entity['id'], url, _img_format))

        logger.info('准备生成缩略图 w:{0} h:{1} index:{2} format: {3}'.format(iw, ih, self.index, _img_format))
        # 生成缩略图
        if iw >= self.min_thumb_width and ih >= self.min_thumb_height \
                and self.index <= 2 and settings.SUPPORT_IMG.__contains__(_img_format):

            _thumb_w = iw
            _thumb_h = ih

            if self.thumb_keep_gif:
                if iw > self.min_thumb_width * 3:
                    _thumb_w = self.min_thumb_width * 3
                    _thumb_h = int(_thumb_h * self.min_thumb_width * 3 / iw)
            else:
                _thumb_w = self.min_thumb_width
                _thumb_h = self.min_thumb_height

            _thumb_link = self.thumb_image(link, _thumb_w, _thumb_h, img.format, _real_path, iw, ih)

            self.attach_list.append({
                'file_type': 1,
                'file_path': _thumb_link,
                'img_width': _thumb_w,
                'img_height': _thumb_h
            })
            self.index += 1
            logger.info('<%s> [%s] |%s| thumb缩略图链接 %s', self.entity['_config'].get('id'), self.entity['id'],
                        self.entity.get('channel'), _thumb_link)

        logger.info('<%s> [%s] 图片处理耗时: %s', self.entity['_config'].get('id'), self.entity['id'],
                    time.time() - _start_time)
        _water_mark = ''
        if self.entity['_config']['random'] == '智能' and img.format != 'GIF':
            _water_mark = WATER_MARK
        if self.entity.get('content_type', '1') == 2:
            # self.img_tag_re = '<img.*? src="([^""]*)".*?><spilt>'
            return "<img src=\"{0}{1}\"/><spilt>".format(link, _water_mark)

        if self.entity.get('_config').get('source') == '嵌入分发' and self.entity.get('source', self.entity.get('_config').get('account')) == '环球网':
            return '<img src=\"{0}{1}\" style="display:block"/>'.format(link, _water_mark)

        return "<img src=\"{0}{1}\"/>".format(link, _water_mark)


class BaseProcessor(Processor):
    def parse_article(self):
        article = Processor.parse_article(self)
        return article


class WeixinProcessor(Processor):
    img_tag_re = '<img.*?data-src="([^""]*)".*?>'


