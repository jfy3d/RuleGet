# -*- coding: UTF-8 -*-

from rule.common.db.database import conn_pool, get_data_list
from rule.common.db.cache import redis_client
import re
import threading
import time

FILTER_WORD = {}


class Node(object):
    def __init__(self):
        self.children = None


class DFA(object):
    root = Node()
    channel = None

    def __init__(self, channel=None):
        logger.info('dfa --- load %s', self.__str__())
        self.channel = channel
        self.load_word()

    def load_word(self):
        pass

    def contain_word(self, message, returnlist=True):
        _list = []
        if message is None:
            return True
        for i in range(len(message)):
            p = self.root
            j = i
            while j < len(message) and p.children is not None and message[j] in p.children:
                p = p.children[message[j]]

                j += 1
                if p.children is not None and '' in p.children:
                    _list.append(message[i:j])

            if p.children is None:
                _list.append(message[i:j])
                if not returnlist:
                    return True
                # return True
        return _list

    def has_word(self, word):
        return self.contain_word(word)


class GossipDFA(DFA):
    second = Node()

    def load_word(self):
        self.read_from_db()
        t = threading.Thread(target=GossipDFA.read_gossip, args=(self,))
        t.setDaemon(True)
        t.start()

    def read_gossip(self):
        while True:
            time.sleep(600)
            self.read_from_db()

    def read_from_db(self):
        root = Node()

        _w_channel = ''
        if self.channel:
            _w_channel = """ and channel = '{0}' """.format(self.channel)
        _sql = """
                SELECT DISTINCT word_a FROM gossip_word WHERE  flag_delete=0 
                AND ( flag_valid=5
                    OR (flag_valid=1 AND datediff(update_date,now())>=-7 )
                    ) and word_a <> ''  {0}
                """.format(_w_channel)
        _word_a = get_data_list(_sql)
        print('---> 加载八卦词库 {0} {1}'.format(len(_word_a), _w_channel))
        for row in _word_a:
            add_word(root, row['word_a'])
        self.root = root

    def is_gossip(self, content, channel=None):
        _has_words = self.has_word(content)
        if len(_has_words) > 0:
            _b = self.contain_next(_has_words, content)
            if _b is not False:
                return _b
        return False

    def contain_next(self, a_words, message):
        for word_a in a_words:
            _word_b = self.get_word_b(word_a)
            if _word_b is None:
                continue
            if _word_b == '':
                return [word_a, ['']]
            _m = re.findall(_word_b, message)

            if len(_m) > 0:
                return [word_a, list(set(_m))]
        return False

    def get_word_b(self, word_a):
        _ch = '' if self.channel is None else '--{0}'.format(self.channel)

        _ch_w = '' if self.channel is None else " and channel = '{0}'".format(self.channel)

        # logger.info('八卦副词 %s ->>', _ch_w)
        _word_b = redis_client.get('subword:{0}{1}'.format(word_a, _ch))
        if _word_b:
            return _word_b.decode('utf-8')
        _sql = """
        SELECT word_b FROM gossip_word WHERE flag_delete=0  AND word_a=%s

        and ( flag_valid=5
                    OR (flag_valid=1 AND datediff(update_date,now())>=-7 )
                    )  {0}
        """.format(_ch_w)
        _word_b_list = []
        _word_b_set = get_data_list(_sql, (word_a,))
        if len(_word_b_set) == 0:
            return None
        for row in _word_b_set:
            if row['word_b'] is not None and row['word_b'] != '':
                _word_b_list.append(row['word_b'])
        _word_b = '|'.join(_word_b_list)
        redis_client.setex('subword:{0}{1}'.format(word_a, _ch), _word_b, 7200)
        return _word_b

class MultGossipDFA(object):
    dfa_list = {}

    def __init__(self):
        _sql = """select distinct channel from haowai.gossip_word"""
        _channels = get_data_list(_sql)
        for _channel in _channels:
            self.dfa_list[_channel['channel']] = GossipDFA(_channel['channel'])

    def is_gossip(self, word, channel):
        for item in channel.split('|'):

            gossip = self.dfa_list.get(item)
            if gossip:
                print('八卦频道 %s has ->>', item)
                return gossip.is_gossip(word)

        return False


def add_word(root, word):
    node = root
    _w_length = len(word)
    for i in range(_w_length):
        if node.children is None:
            node.children = {word[i]: Node()}

        elif word[i] not in node.children:
            node.children[word[i]] = Node()

        node = node.children[word[i]]
        if i == _w_length - 1:
            node.children = {'': True}


def load_word_type():
    _type_list = []

    _list = get_data_list("SELECT DISTINCT type FROM site_filter_words WHERE flag_valid=1")
    for row in _list:
        FILTER_WORD[row['type']] = Node()
        _type_list.append(row['type'])
    return _type_list


def load_words(word_type):
    print('load site_filter_words type: {0}'.format(word_type))
    _list = get_data_list("SELECT word FROM site_filter_words WHERE type=%s AND flag_valid=1", (word_type,))
    for row in _list:
        add_word(FILTER_WORD[word_type], row['word'])


def dfa_init():
    print('load site_filter_words .......')
    _type_list = load_word_type()
    for _type in _type_list:
        load_words(_type)


def contain_badword(message, word_type):
    _list = []
    if message is None:
        return True
    for i in range(len(message)):
        p = FILTER_WORD[word_type]
        j = i
        while j < len(message) and p.children is not None and message[j] in p.children:
            p = p.children[message[j]]
            j += 1

        if p.children is None:
            _list.append(message[i:j])
            # return True
    return _list


GOSSIP_DFA = {} #MultGossipDFA()

if __name__ == "__main__":
    wl = GOSSIP_DFA.is_gossip(
        '四处乱咬乱吠黄羊角，吓得家中六四事件11岁的女儿军转安置躲在屋里不敢出来，直到辖冯素英区派出所民警赶到后，才将孩子从屋中救出。最后在征得主人同意后，民警和村民合力将这只发疯的狗打死')
    print(wl)
