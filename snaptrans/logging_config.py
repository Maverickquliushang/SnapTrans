import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(data: Path):
    logger = logging.getLogger('snaptrans')
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(data / 'logs' / 'app.log', maxBytes=1024 * 1024,
                                  backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    logger.propagate = False
    # Third-party debug output must not persist text, HTTP headers or bodies.
    for name in ('httpx', 'httpcore', 'RapidOCR'):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    return logger
