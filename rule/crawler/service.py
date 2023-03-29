from rule.common.db.cache import redis_client
from rule.common.func import bytes_to_str
import settings
import time
import json
import multiprocessing
import traceback
from multiprocessing import cpu_count
from rule.crawler.loader import crawler_logger as logger

CLASS_MAP = []
PACKAGE_MAP = {}


def get_spider(classname):
    _class = classname.replace('#', '').split('?')[0]
    _path = _class.split('.')
    _module = '.'.join(_path[:-1])
    _module = '%s' % _module
    _name = _path[-1]
    if not CLASS_MAP.__contains__(_class):
        PACKAGE_MAP[_module] = __import__(_module, {}, {}, _name)
        CLASS_MAP.append(_class)
    return getattr(PACKAGE_MAP[_module], _name)


class Crawler:
    def start(self):
        pool = multiprocessing.Pool(processes=1)
        for _ in range(1):
            pool.apply_async(Crawler.runner, (self,))
        pool.close()
        # pool.join()

        logger.info('Crawler create ')

    def runner(self):
        while True:
            _config = redis_client.rpop(settings.CONFIG_KEY)
            logger.info('get crawler config %s', _config)
            if not _config:
                time.sleep(10)
                continue

            _crawler_config = json.loads(bytes_to_str(_config))
            logger.info('load config !')
            try:
                _crawler_class = get_spider(_crawler_config['crawler'])
                _crawler = _crawler_class(_crawler_config)
                logger.info('crawler process !')
                _crawler.process()
            except KeyboardInterrupt as e:
                logger.warning("KeyboardInterrupt 中断进程 ")
                break
            except:
                logger.error(traceback.print_exc())


def start_crawler():
    crawler = Crawler()
    crawler.start()