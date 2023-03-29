# -*- coding: utf-8 -*-

import logging
from logging import StreamHandler
from logging.handlers import TimedRotatingFileHandler

from flask import Flask

import settings

app = Flask(__name__)


def handle_logger(app):
    formatter = logging.Formatter('%(asctime)s %(filename)s [l:%(lineno)d] %(levelname)s %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    file_handler = TimedRotatingFileHandler(filename='{0}/center.log'.format(settings.LOG_PATH),
                                            when="D", interval=1)
    file_handler.setFormatter(formatter)
    # file_handler.setLevel(logging.DEBUG)
    stream_handler = StreamHandler()
    # stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(formatter)
    app.logger.setLevel(logging.DEBUG)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(stream_handler)


handle_logger(app)

logger = app.logger



