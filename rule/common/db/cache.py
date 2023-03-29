import redis
import settings

pool = redis.ConnectionPool(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0)
redis_client = redis.Redis(connection_pool=pool)


pool2 = redis.ConnectionPool(host='172.16.1.1', port=settings.REDIS_PORT, db=3)
redis_client2 = redis.Redis(connection_pool=pool2)
