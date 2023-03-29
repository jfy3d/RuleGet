# -*- coding: utf-8 -*-
# 通用处理
import logging
import re

from rule.common.DFA import contain_badword, FILTER_WORD, GOSSIP_DFA
from rule.common.db.database import exec_sql
from rule.common.func import filter_emoji
from rule.store.loader import store_logger as logger


class BaseFilter:
    def __init__(self):
        pass

    def summary(self, content):
        """获取摘要，self为文章解析类实例"""
        if content is None:
            return True
        srt = re.sub(r'[\s\u3000]', '', content)  # 去除换行和空白
        srr = ''
        while len(srr) < 100:  # 当字数大于100的时候停止
            try:
                ss = re.search(r'.+?[。！？]', srt, re.S).group()  # 寻找整句
            except:
                return srr
            srt = srt.replace(ss, '')
            srr = srr + ss
        return srr




DROP_SOURCE = [
    'VISTA看天下', '每日经济新闻', '每经网', '海外网', '澎湃新闻', '澎湃', '新京报', '新京报网', '财新', '财新网', '中新社', '中国新闻网', '号外',
    '中国网', '数据宝', '小基快跑', '财看见', 'Dreamwriter', '申万宏源研究', '界面新闻', '界面', '电鳗快报', '21世纪经济报道', 'AI财经社'
]


class SourceFilter(BaseFilter):
    def filter_item(self, entity):
        logger.info("内容来源 <{0}> [{1}] {2} ".format(entity['_config']['id'], entity['id'], entity.get('source')))
        if entity.get('source') in DROP_SOURCE:
            logger.warn("内容来源 <{0}> [{1}] {2} 丢弃".format(entity['_config']['id'], entity['id'], entity.get('source')))
            return False
        return True


"""
违禁词敏感词等过滤
"""


class WordFilter(BaseFilter):
    # todo new ver
    def filter_item(self, entity):
        self.ignore_verify(entity)
        return True

    def ignore_verify(self, entity):
        _interception = int(entity['_config']['interception'])
        logger.info("判断八卦推荐 <{0}> [{1}] {2}".format(entity['_config']['id'], entity['id'], _interception))
        if _interception == 10:
            # 不过滤敏感词，直接进推荐库。
            entity['recmd'] = 2
            logger.info('<{0}> [{1}] {2} {3} 10分来源直接推荐'.format(entity['_config']['id'], entity['id'], entity['title'],
                                                               entity.get('source_url')))
            return True
        elif _interception in (8, 9):
            # 不过滤敏感词，判断内容是否名人八卦、奇闻逸事。若不符合，进ES文章库；若符合，进推荐库
            _match_word = GOSSIP_DFA.is_gossip('{0} {1}'.format(entity['title'], entity['content_text']),
                                               entity['_config']['channel'])
            if _match_word:
                # todo new ver
                logger.info(
                    '<{0}> [{1}] {2} {3} 匹配为八卦'.format(entity['_config']['id'], entity['id'], entity['title'],
                                                       entity.get('source_url')))
                self.notify(entity, _match_word)
                entity['recmd'] = 2
            else:
                entity['recmd'] = 0
            return True
        elif _interception in (6, 7):
            # 过滤敏感词，不通过的，进审查库；通过的，判断内容是否名人八卦、奇闻逸事。若不符合，进ES文章库；若符合，进推荐库。
            if not self.has_bad_word(entity):
                _match_word = GOSSIP_DFA.is_gossip('{0} {1}'.format(entity['title'], entity['content_text']),
                                                   entity['_config']['channel'])
                if _match_word:
                    logger.info(
                        '<{0}> [{1}] {2} {3} 匹配为八卦'.format(entity['_config']['id'], entity['id'], entity['title'],
                                                           entity.get('source_url')))
                    self.notify(entity, _match_word)
                    entity['recmd'] = 2
                else:
                    entity['recmd'] = 0
                return True
        elif _interception in (4, 5):
            # 过滤敏感词，不通过，进审查库；通过的，进入到ES文章库。
            if not self.has_bad_word(entity):
                entity['recmd'] = 0
            return True
        elif _interception in (1, 3):
            # 过滤敏感词，通过或不通过都进审查库。
            if not self.has_bad_word(entity):
                return True

        return True

    def has_bad_word(self, entity):
        for _type in FILTER_WORD.keys():
            _badwords = contain_badword('{0} {1}'.format(entity.get('title'),
                                                         entity.get('content_text', entity['content'])), _type)
            if len(_badwords) > 0:
                exec_sql('INSERT INTO content_store.sensi(id,word,type) VALUES(%s,%s,%s)',
                         (entity['id'], _badwords[0], _type))
                return True
        return False

    def notify(self, entity, match):
        entity['gossip'] = '{0}-{1}'.format(match[0], '|'.join(match[1]))
        msg = '首词：{0}  配词：{1}'.format(match[0], '|'.join(match[1]))
        logger.info('{0} - [{1}] {2}'.format(msg, entity['id'], entity['title']))
        notify = """#推荐#
标题：{0}
网址：{1}
匹配：{2}""".format(entity['title'], entity['source_url'], msg)


"""
符号替换
"""


class WordReplaceFilter(BaseFilter):
    def filter_item(self, entity):
        if entity.get('keep_format') == 1 or entity['_config'].get('skip_filter') == 1:
            return True

        title = entity['title']
        title = filter_emoji(title)
        # title = re.sub(r'(?<=[\?？：\:\!！。\.\,，\"“\'”\da-zA-Z])\s|\s(?=[\?？：\:\!！。\.\,，\"“\'”\da-zA-Z])', '',
        #                title)  # 清除部分符号，字母和数字前后的空格
        title = re.sub(r'——', '', title)
        title = re.sub(r'</?[a-zA-Z\d]+?>', '', title)
        title = re.sub(r'&#?[a-zA-Z\d]{2,7};', '', title)  # 清除实体符
        title = re.sub(r'【.+?】|\||\.{2,6}', '', title)  # 清除【】，|，.数字
        title = re.sub(r'[\(\[「（].*?[\)）\]」]', '', title)  # 清除符号中间的字符
        title = re.sub(r'\"', '“', title, 1)  # 英文引号替换成中文引号
        title = re.sub(r'\"', '”', title, 1)  # 英文引号替换成中文引号
        title = re.sub(r'[\(（\[]组?图[\)）\]]', '', title)  # 删除组图
        title = re.sub(r'\s{2,}', ' ', title)  # 将多个空格符变为一个
        title = title.strip()  # 去除开头和结尾的空格
        # title = re.sub(r' +', '，', title)  # 把title中的空格变成逗号
        # title = re.sub('(?<![ -~]) (?![ -~])', '，', title)  # 把title中的空格变成逗号,不替换中文英文数字间的空格
        title = re.sub(r'[\(\[「（].*?[\)）\]」]', '', title)
        title = title.replace('「', '').replace('」', '')
        title = title.replace('……', '')
        title = title.replace('『', '').replace('』', title)
        title = re.sub(r'[)(]', '', title)

        for i in ['~', '。', '。。。', '…', '？！', '！！', '！！！', '？？', '？？？', ' 。。。。。。', '。。', '＃']:
            title = re.sub(r'%s' % i, '', title)
        entity['title'] = title

        content = entity['content']

        content = re.sub(r'（.+?）+$', '', content)
        content = re.sub(r'\(.+?\)+$', '', content)
        content = content.replace('（完）', '')
        content = content.replace('▲', '')
        entity['content'] = content
        return True


"""
文章内容标签替换
"""


class ContentTagFilter(BaseFilter):
    def filter_item(self, entity):
        if entity['_config'].get('skip_filter') == 1 or entity['_config'].get('channel') == '视频' or entity.get(
                'keep_format') == 1:
            # if entity['_config'].get('skip_filter') == 1 or entity['_config'].get('channel') == '视频':
            return True
        """
        得到带有标签的文本内容
        """
        content = entity['content']
        content = re.sub(r'<script.+?</script>', '', content, flags=re.S)  # 删除文章中的js代码
        content = re.sub(r'<style.+?</style>', '', content, flags=re.S)  # 删除文章中的css代码
        content = re.sub(r'(?<=<)[iI][Mm][Gg]', 'img', content)  # 把img标签统一
        content = re.sub(r'P(?=>)', 'p', content)
        # print(2,self.content)
        content = re.sub(r'<div.*?>', '<div>', content)  # 把div前标签的属性统统删除
        content = re.sub(r'<(?!/?(p|img|br|div|hr|spilt|strong|h1|h2|h3|h4|h5|h6)).*?>', '', content)  # 删除除了这些标签外的所有标签
        content = re.sub(r'<p.*?>', '<p>', content)  # 同上
        # content = re.sub(r'✎ ', '', content)  # 删除不需要的字符
        content = re.sub(r'&[a-zA-Z]{3,7};|(?<=<p>)\s+?(?!\s)', '', content)  # 删除不需要的标签
        content = re.sub(r'[□▲▽■▌●▶▼△⊙★◤ω↓↑✎👇◎←→①②③④⑤⑥⑦⑧⑨⑩]', '', content)  # 删除不需要的符号
        content = re.sub(r'\u3000+?', '', content)  # 删除不需要的标签
        content = re.sub(r'\xa0+?', '', content)  # 删除不需要的标签
        content = re.sub(r'<p><br></p>', '', content)  # 删除不需要的标签
        content = re.sub(r'<p><br/></p>', '', content)  # 删除不需要的标签
        content = re.sub(r'<p>\r\n<br>\r\n</p>', '', content)  # 删除不需要的标签
        content = re.sub(r'&nbsp;&nbsp;|﻿', '', content)  # 删除不需要的标签
        content = re.sub(r'<strong></strong>﻿', '', content)  # 删除不需要的标签
        content = re.sub(r'<p> </p>', '', content)  # 删除不需要的标签
        content = re.sub(r'<p>﻿ </p>', '', content)  # 删除不需要的标签
        content = re.sub(r'<p></p>', '', content)  # 删除不需要的标签
        entity['content'] = content
        return True
        # self.plain_text = re.sub(r'<.+?>', '', self.get_tag_content())
        # return self.plain_text


class SummaryFilter(BaseFilter):
    def filter_item(self, entity):
        if not entity.get('content_text'):
            p = re.compile('<[^>]+>')
            entity['content_text'] = p.sub("", entity['content'])
        entity['summary'] = self.summary(entity['content_text'])
        # logger.info('生成摘要：%s', entity['summary'])
        return True
