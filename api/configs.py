# Read configuration with fall back defaults

from os import environ

CONFIGS = {
    # Simulate work between 5 - 30 seconds
    'TASK_MIN_TIME': int(environ.get('TASK_MIN_TIME', 5)),
    'TASK_MAX_TIME': int(environ.get('TASK_MAX_TIME', 30)),

    # Rate limit to 10 requests/minute/IP
    'MAX_REQUESTS_PER_TIME_PER_IP': int(environ.get('MAX_REQUESTS_PER_TIME_PER_IP', 10)),
    'RATE_LIMIT_PERIOD': int(environ.get('RATE_LIMIT_PERIOD', 60)),

    # Concurrent tasks
    'CONCURRENCY': int(environ.get('CONCURRENCY', 5)),
    'MAX_TASKS_QUEUE': int(environ.get('MAX_TASKS_QUEUE', 100)),

    # Cleanup
    'CLEANUP_INTERVAL': int(environ.get('CLEANUP_INTERVAL', 600)),
}
