from urllib.parse import urljoin
from rule.crawler.loader import crawler_logger as logger, record_duplicate, record_filter, record_fail
import settings
from rule.common.db.cache import redis_client
from rule.common.func import get_rnd_id, extract_date, get_now, get_encodings_from_content
from rule.common.data import HEADERS, USER_AGENTS
from rule.common.validator import validate_title, validate_url
from rule.common.record import record_error
from requests.adapters import HTTPAdapter
import json
import random
import re
import requests
import traceback
import datetime
from lxml import etree
import jsonpath
import time


class BaseParse(object):
    last_url = None
    item = None
    crawler_param_config = {}
    ignore_valid = False
    body_text = ''

    def __init__(self, config):
        logger.info('<%s> (%s) 来源开始', config.get('id'), config.get('site_name'))
        self.xpath_list_link = config.get('xpath_list_link')
        self.xpath_list_title = config.get('xpath_list_title')
        self.xpath_title = config.get('xpath_title')
        self.xpath_body = config.get('xpath_body')
        self.config = config
        self.page_index = 1
        self.last_url = self.get_last_url()
        self.stop = False
        self.crawler_param_config = {}
        try:
            self.parse_crawler()
        except:
            logger.error(traceback.format_exc())

    # 加载配置表中扩展参数配置
    def parse_crawler(self):
        logger.info('<%s> (%s) BGC参数配置 : %s', self.config.get('id'), self.config.get('site_name'),
                    self.config['crawler'])
        _crawler_param = self.config['crawler'].split('?')
        if len(_crawler_param) > 1:
            _params = _crawler_param[1].split(':&')
            for _param in _params:
                _kv = _param.split(':=')
                logger.info('参数 %s', _kv)
                self.crawler_param_config[_kv[0]] = _kv[1]
                if _kv[0] == 'img_margin':
                    self.config[_kv[0]] = _kv[1]
        logger.info('<%s> (%s) BGC参数配置 : %s', self.config.get('id'), self.config.get('site_name'),
                    self.crawler_param_config)
        if int(self.crawler_param_config.get('no_valid', 0)) == 1 and self.get_last_url() is None:
            self.ignore_valid = True

    def get_last_url(self):
        url = redis_client.get(settings.CRAWLER_POS_KEY.format(self.config['id']))
        if url is not None:
            url = url.decode('utf-8')
        logger.info('<%s> (%s) 上次位置 : %s', self.config.get('id'), self.config.get('site_name'), url)
        return url

    def create_item(self):
        item = {'id': get_rnd_id()}
        _config = self.config
        if 'parse' in _config.keys():
            del _config['parse']
        item['_config'] = _config
        # 新上来源标志
        if self.last_url is None:
            item['is_new'] = 1
        return item

    # 请求
    def make_request(self, url):
        _req_count = 1
        request = requests.Session()
        request.mount('http://', HTTPAdapter(max_retries=5))
        request.mount('https://', HTTPAdapter(max_retries=5))
        try:
            resp = request.get(url,
                               headers=self._get_headers(self.crawler_param_config.get('site_url')),
                               proxies=settings.PROXY_SERVER,
                               timeout=20)
            while _req_count <= 3:
                if resp.status_code == 200:
                    break
                else:
                    time.sleep(2)
                    resp = request.get(url,
                                       headers=self._get_headers(self.crawler_param_config.get('site_url')),
                                       proxies=settings.PROXY_SERVER,
                                       timeout=20)
                    _req_count = _req_count + 1
            return resp
        except:
            logger.error(traceback.print_exc())
            time.sleep(2)
            return request.get(url,
                               headers=self._get_headers(self.crawler_param_config.get('site_url')),
                               proxies=settings.PROXY_SERVER,
                               timeout=20)

    def _get_headers(self, referer):
        headers = HEADERS
        headers['User-Agent'] = USER_AGENTS[random.randint(0, len(USER_AGENTS) - 1)]
        headers['Referer'] = referer
        return headers

    def validate_url(self, url):
        return validate_url(url)

    def validate_title(self, title, channel=''):
        return validate_title(title, channel)

    def validate_item(self):
        if not self.item.get('title') or not self.item.get('content'):
            return False
        return True

    def transfor(self, content):
        return content


"""
通用解析
"""


class GeneralParse(BaseParse):

    def process(self):
        logger.info('start process ')
        self.parse_list(self.load_url_params())

    def load_url_params(self):
        return self.config.get('site_url').format(page0=self.page_index - 1,
                                                  page1=self.page_index)

    def parse_list_item(self, content):
        content = self.transfor(content)
        if self.config.get('list_type') == 'json':
            _json_obj = json.loads(content)
            _title_list = jsonpath.jsonpath(_json_obj, expr=self.xpath_list_title)
            _href_list = jsonpath.jsonpath(_json_obj, expr=self.xpath_list_link)
            logger.info('json list size %s', len(_href_list))
            _next_url = self.load_url_params()
        else:
            _charset = get_encodings_from_content(content.decode('utf-8', 'ignore'))
            dom = etree.HTML(content.decode(_charset, 'ignore'))
            _href_list = dom.xpath(self.xpath_list_link)
            _title_list = dom.xpath(self.xpath_list_title)
            _next_url = self.next_url(dom)
            logger.info('html list xpath size: %s', len(_href_list))

        _list_item = []
        for index in range(0, len(_href_list)):
            if self.validate_url(_href_list[index]):
                if self.validate_title(_title_list[index]):
                    _list_item.append((_title_list[index], _href_list[index]))
                else:
                    logger.warn('<%s> (%s) 标题查重 %s', self.config.get('id'), self.config['site_name'],
                                _title_list[index])
            else:
                logger.warn('<%s> (%s) 地址查重 %s', self.config.get('id'), self.config['site_name'], _href_list[index])
        return {'next_url': '', 'list_item': _list_item}

    """
    处理列表
    """

    def parse_list(self, url):
        logger.info('parse_list %s', url)
        response = self.make_request(url)
        logger.info('获取列表状态 %s', response.status_code)
        _page_info = self.parse_list_item(response.content)
        _list_item = _page_info['list_item']
        index = 0
        for _title, _href in _list_item:
            url = urljoin(response.url, _href)
            # 解析到上次的位置停止
            logger.info('%s, %s', _title, _href)
            if url == self.last_url:
                logger.info('<%s> (%s)处理到上次BGC位置停止 : %s   %s', self.config.get('id'), self.config['site_name'], url,
                            self.last_url)
                if index == 0:
                    logger.warning('<%s> (%s) 未更新新文章', self.config.get('id'), self.config['site_name'])
                self.stop = True
                break
            if index == 0 and self.page_index == 1:
                # 记录每次最新BGC的文章
                redis_client.set(settings.CRAWLER_POS_KEY.format(self.config['id']), url)

            self.parse_body(url)
            time.sleep(random.randint(1, 5) / 2)

        # # 翻页
        if not self.stop and _page_info.get('next_url'):
            self.page_index += 1
            self.parse_list(_page_info.get('next_url'))

    def parse_body(self, url):
        logger.info('parse_body  %s', url)
        response = self.make_request(url)
        self.body_text = response.text
        logger.info('html charset %s', response.encoding)
        _charset = get_encodings_from_content(self.body_text, response.encoding)
        logger.info('parse charset %s', _charset)
        dom = etree.HTML(response.content.decode(_charset, 'ignore'))
        try:
            self.load_item(dom, url)
            self.push_queue()
        except:
            logger.error(traceback.format_exc())

    # 翻页
    def next_url(self, dom):
        try:
            if self.page_index <= int(self.crawler_param_config.get('max_page', 2)):
                next_page = self.crawler_param_config.get('next_page')
                if next_page == 'url':
                    _next_page_url = self.config.get('site_url').format(page0=self.page_index,
                                                                        page1=self.page_index + 1)
                else:
                    _next_page_url = dom.xpath(self.crawler_param_config.get('next_page'))

                if _next_page_url:
                    _next_page_url = urljoin(self.config.get('site_url'), _next_page_url[0])
                    logger.info('<%s> (%s) >>turning page: %s %s 列表翻页 >> ------------- ', self.config['id'],
                                self.config['site_name'], self.page_index,
                                _next_page_url)
                    return _next_page_url
                else:
                    logger.info('<%s> (%s) 无下一页列表 %s %s %s', self.config['id'], self.config['site_name'],
                                self.config.get('site_url'),
                                _next_page_url,
                                self.crawler_param_config.get('next_page'))
                    return None
        except Exception as ex:
            logger.error(traceback.format_exc())
            return None

    def push_queue(self):
        if self.validate_item():
            redis_client.lpush(settings.ARTICLE_QUEUE_KEY, json.dumps(self.item))
        else:
            logger.error('<%s> (%s) 获取失败 %s ', self.config['id'], self.config['site_name'],
                         self.config.get('site_url'))

    def load_item(self, response, url):

        self.item = self.create_item()

        logger.info('<%s> load_item %s', self.config['id'], url)
        # try:
        _title = ''.join(response.xpath(self.xpath_title))
        logger.info('body title %s', _title)

        if _title is None or not isinstance(_title, str) or _title == '':
            logger.error('<%s> no title get %s %s', self.config['id'], url, self.xpath_title)
            _mail_body = """
                        来源{0} {1}  未解析到文章标题  xpath:{2} {3}
                        """.format(self.config['site_name'], self.config['site_url'], self.xpath_title, url)
            record_error(_mail_body)
            return self.item

        self.item['title'] = self.filter_title(_title)
        _tags = []
        for _tag_item in response.xpath(self.xpath_body):
            _tags.append(etree.tounicode(_tag_item))

        self.item['content'] = self.filter_content(''.join(_tags))

        if 'content' not in self.item.keys() or self.item['content'] == '':
            logger.error('<%s> no body get %s %s', self.config['id'], url, self.xpath_body)
            _mail_body = """
            来源{0} {1}  未解析到文章正文  xpath:{2} {3} 错误等级：【严重】
            """.format(self.config['site_name'], self.config['site_url'], self.xpath_body, url)
            record_error(_mail_body)
        else:
            self.item['content_text'] = re.sub(r'<\s*script[^>]*>[^<]*<\s*/\s*script\s*>', '', self.item['content'],
                                               count=0, flags=re.I)
            self.item['content_text'] = re.sub(r'<.*?>', '', self.item['content_text'])

        self.item['source_url'] = url
        self.item['get_time'] = get_now()
        # 提取文章的发布时间
        logger.info('提取文章的发布时间 %s %s', self.item['title'], self.crawler_param_config.get('publish_date'))
        if 'publish_date' in self.crawler_param_config.keys():
            _publish_date = response.xpath(self.crawler_param_config.get('publish_date'))
            if _publish_date:
                logger.info('日期匹配内容')
                _publish_date = extract_date(
                    _publish_date[0] if isinstance(_publish_date[0], str) else etree.tounicode(_publish_date[0]))
                self.item['createdate'] = _publish_date
            else:
                logger.error('<%s> 没有提取到文章发布时间: %s %s', self.config['id'], url, self.config.get('site_url'))
                logger.error('<%s> %s', self.config['id'], self.crawler_param_config.get('publish_date'))
                logger.error('<%s> %s', self.config['id'], response.xpath('//body')[0])
                _mail_body = """
                            来源{0} {1}  没有提取到文章发布时间  xpath:{2} {3} 错误等级：【严重】
                            """.format(self.config['site_name'], self.config['site_url'],
                                       self.crawler_param_config.get('publish_date'), response.url)
                record_error(_mail_body)
                self.item['createdate'] = get_now()  # 解析文章的发布时间
        else:
            _publish_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.item['createdate'] = _publish_date  # 解析文章的发布时间
        self.item['get_time'] = self.item['createdate']
        logger.info('文章发布时间 %s', self.item['get_time'])
        return self.item

    # 过滤正文
    def filter_content(self, content):
        return content

    # 过滤标题
    def filter_title(self, title):
        return title
