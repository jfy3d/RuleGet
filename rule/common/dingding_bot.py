# -*- coding: utf-8 -*-
import requests
import os


def system_bot_send(message, msgtype='text', title=''):
    if os.getenv('RUN_MODE') == 'dev':
        return
    url = 'https://oapi.dingtalk.com/robot/send?access_token='

    json = package_msg(msgtype, message, title)
    return requests.post(url, json=json)


def package_msg(msgtype, text, title=''):
    _env = ''
    if os.getenv('RUN_MODE') == 'dev':
        _env = '[测试环境]\n'
    if msgtype == "markdown":
        return markdown_msg('{0}{1}'.format(title, _env), text)
    return {'msgtype': msgtype, 'text': {'content': '{0}{1}'.format(_env, text)}}


def markdown_msg(title, text):
    return {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": text
        }
    }
