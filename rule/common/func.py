from datetime import datetime
import hashlib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from email.header import Header
import smtplib
import logging
from logging.handlers import TimedRotatingFileHandler, HTTPHandler
import settings
import os
import re
import json
from datetime import date
import six
import zbarlight
import os

base_str = [str(x) for x in range(10)] + [chr(x) for x in range(ord('A'), ord('A') + 26)]


def get_rnd_id():
    ms = datetime.now().microsecond

    string_num = str(time.time())

    idx = string_num.find('.')
    string_num = '%s%s' % (string_num[0:idx], ms)
    num = int(string_num)

    mid = []
    while True:
        if num == 0:
            break
        num, rem = divmod(num, 36)
        mid.append(base_str[rem])
    return ''.join([str(xx) for xx in mid[::-1]])


def get_now(format='%Y-%m-%d %H:%M:%S'):
    return time.strftime(format, time.localtime(time.time()))


def get_yesterday(fmt='%Y-%m-%d'):
    return get_before_day(fmt)


def get_before_day(fmt='%Y-%m-%d', days=-1):
    _today = datetime.datetime.now()
    _before_day = _today + datetime.timedelta(days=days)
    return _before_day.strftime(fmt)


def md5(string):
    m = hashlib.md5()
    m.update(string)
    return m.hexdigest()


# 初始化日志
def setup_logger(logger_name, log_file, level=logging.INFO, format='%(lineno)d %(asctime)s %(message)s'):
    log_setup = logging.getLogger(logger_name)
    formatter = logging.Formatter(format, datefmt='%Y-%m-%d %H:%M:%S')
    file_handler = TimedRotatingFileHandler(filename='%s/%s' % (settings.LOG_PATH, log_file),
                                            when="D", interval=1, backupCount=20)

    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    http_handle = HTTPHandler(host='', url='', method='POST')
    http_handle.setFormatter(formatter)

    log_setup.setLevel(level)
    log_setup.addHandler(file_handler)
    log_setup.addHandler(stream_handler)


def mkdir(path):
    if not os.path.exists(path):
        os.makedirs(path)
        os.system('chmod -R 777 {0}'.format(path))


def filter_pun(string):
    r = r"[\s+\.\!\n\t\r\/_,$%^*(+\"\')]+|[+——()?【】《》“”‘’;；！，。？、:：~@#￥%……&*（）]+"
    return re.sub(r, '', string)


# 对日期时间序列化
class CJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        else:
            return json.JSONEncoder.default(self, obj)


def filter_emoji(desstr, restr=''):
    '''''
    过滤表情
    '''
    try:
        co = re.compile(u'[\U00010000-\U0010ffff]')
    except re.error:
        co = re.compile(u'[\uD800-\uDBFF][\uDC00-\uDFFF]')
    return co.sub(restr, desstr)


# 判断文章正文编码
def get_encodings_from_content(content, encode='-'):

    ch = re.search(r'<meta.*?charset=["\']*(.+?)["\'>]', content)
    if ch:
        return ch.group(1)

    ch = re.search(r'<meta.*?content=["\']*;?charset=(.+?)["\'>]', content)
    if ch:
        return ch.group(1)

    ch = re.search(r'^<\?xml.*?encoding=["\']*(.+?)["\'>]', content)
    if ch:
        return ch.group(1)

    ch = re.search(r'<meta.*?content=["].*?charset=(.+?)[">]', content, flags=re.I)
    if ch:
        return ch.group(1)
    print(encode, '-----')
    if encode is not None and encode != 'ISO-8859-1' and encode != '-':
        return encode
    return 'utf-8'


# 提取各种格式的日期时间
def extract_date(string):
    string = string.strip()
    pattern = r'(\d{4})-(\d{1,2})-(\d{1,2} \d{1,2}:\d{1,2}:\d{1,2})'
    r = re.search(pattern, string)
    if r is not None:
        return r.group()
    pattern = r'(\d{4})-(\d{1,2})-(\d{1,2} \d{1,2}:\d{1,2})'
    r = re.search(pattern, string)
    if r is not None:
        return '{0}{1}'.format(r.group(), ':00')
    pattern = r'(\d{4})-(\d{1,2})-(\d{1,2})'
    r = re.search(pattern, string)
    if r is not None:
        return '{0} {1}'.format(r.group(), '09:00:00')

    pattern = r'(\d{4})/(\d{1,2})/(\d{1,2} \d{1,2}:\d{1,2}:\d{1,2})'
    r = re.search(pattern, string)
    if r is not None:
        return r.group().replace('/', '-')
    pattern = r'(\d{4})/(\d{1,2})/(\d{1,2} \d{1,2}:\d{1,2})'
    r = re.search(pattern, string)
    if r is not None:
        return '{0}{1}'.format(r.group().replace('/', '-'), ':00')
    pattern = r'(\d{4})/(\d{1,2})/(\d{1,2})'
    r = re.search(pattern, string)
    if r is not None:
        return '{0} {1}'.format(r.group().replace('/', '-'), '09:00:00')

    pattern = r'(\d{4})\.(\d{1,2})\.(\d{1,2} \d{1,2}:\d{1,2}:\d{1,2})'
    r = re.search(pattern, string)
    if r is not None:
        return r.group().replace('.', '-')
    pattern = r'(\d{4})\.(\d{1,2})\.(\d{1,2} \d{1,2}:\d{1,2})'
    r = re.search(pattern, string)
    if r is not None:
        return '{0}{1}'.format(r.group().replace('.', '-'), ':00')
    pattern = r'(\d{4})\.(\d{1,2})\.(\d{1,2})'
    r = re.search(pattern, string)
    if r is not None:
        return '{0} {1}'.format(r.group().replace('.', '-'), '09:00:00')

    pattern = r'(\d{4})年(\d{1,2})月(\d{1,2})日 \d{1,2}:\d{1,2}:\d{1,2}'
    r = re.search(pattern, string)
    if r is not None:
        return '{0} {1}'.format(r.group().replace('年', '-').replace('月', '-').replace('日', ''), '')


    pattern = r'(\d{4})年(\d{1,2})月(\d{1,2})日\d{1,2}:\d{1,2}'
    r = re.search(pattern, string)
    if r is not None:
        return '{0}{1}'.format(r.group().replace('年', '-').replace('月', '-').replace('日', ' '), ':00')

    pattern = r'(\d{4})年(\d{1,2})月(\d{1,2})日 \d{1,2}:\d{1,2}'
    r = re.search(pattern, string)
    if r is not None:
        return '{0}{1}'.format(r.group().replace('年', '-').replace('月', '-').replace('日', ' '), ':00')

    pattern = r'(\d{4})年(\d{1,2})月(\d{1,2})日'
    r = re.search(pattern, string)
    if r is not None:
        return '{0} {1}'.format(r.group().replace('年', '-').replace('月', '-').replace('日', ''), '09:00:00')

    pattern = r'(\d{1,2})分钟前'
    r = re.search(pattern, string)
    if r is not None:
        m = r.group(1)
        now = datetime.datetime.now()
        dt = datetime.timedelta(minutes=int(m))
        it_date = now - dt
        return it_date.strftime('%Y-%m-%d %H:%M:%S')
    pattern = r'(\d{1,2})小时前'
    r = re.search(pattern, string)
    if r is not None:
        m = r.group(1)
        now = datetime.datetime.now()
        dt = datetime.timedelta(hours=int(m))
        it_date = now - dt
        return it_date.strftime('%Y-%m-%d %H:%M:%S')
    pattern = r'(\d{1,2})天前'
    r = re.search(pattern, string)
    if r is not None:
        m = r.group(1)
        now = datetime.datetime.now()
        dt = datetime.timedelta(days=int(m))
        it_date = now - dt
        return it_date.strftime('%Y-%m-%d %H:%M:%S')

    pattern = r'(\d{1,2})-(\d{1,2} \d{1,2}:\d{1,2}:\d{1,2})'
    r = re.search(pattern, string)
    if r is not None:
        return '{0}-{1}'.format(datetime.datetime.now().strftime('%Y'), r.group())

def bytes_to_str(s, encoding='utf-8'):
    """Returns a str if a bytes object is given."""
    if six.PY3 and isinstance(s, bytes):
        return s.decode(encoding)
    return s


# 检查二维码
def count_qrcode(img):
    code = zbarlight.scan_codes('qrcode', img)
    if code is None:
        return 0
    else:
        return len(code)


def is_valid_jpg(jpg_file):
    """判断JPG文件下载是否完整
    """
    result = False
    logger.info('is_valid_jpg ----------|-|')
    if isinstance(jpg_file, str):
        if jpg_file.lower().endswith('jpg') or jpg_file.lower().endswith('jpeg'):
            with open(jpg_file, 'rb') as f:
                f.seek(-2, 2)
                p = f.read()
                result = (p == b'\xff\xd9')  # 判定jpg是否包含结束字段
        else:
            result = True
    else:
        result = (jpg_file[-2:] == b'\xff\xd9')
    logger.info('is_valid_jpg ----------|-| unvalid_picture {0}'.format(result))
    return result


# 生成摘要
def get_html_summary(str, min, length):
    dr = re.compile(r'<[^>]+>', re.S)
    s = dr.sub('', str)
    if len(s) < min:
        return ''
    return s[0:length].strip()


def get_filename_ext(path, default_ext='image/jpg'):
    path = path.split('?')[0]
    ext = os.path.splitext(path)[1]
    if ext == '':
        _file_type = default_ext.split('/')
        ext = 'jpg' if len(_file_type) == 1 else _file_type[1]
    if ext.lower() not in ('.jpg', '.png', '.gif', '.jpeg'):
        ext = 'jpg'
    return ext.replace('.', '')


def get_dominant_color(image):

    image = image.convert('RGBA')
    image.thumbnail((200, 200))
    index = 0
    _w_count = 0

    for count, (r, g, b, a) in image.getcolors(image.size[0] * image.size[1]):

        dominant_color = (r, g, b)

        index += 1
        if sum(dominant_color) > 560:
            _w_count += 1

    return _w_count / index
