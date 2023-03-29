import settings
from rule.common.db.cache import redis_client


def record_error(content):
    redis_client.lpush(settings.CRAWLER_ERROR_LIST_KEY, content)