import logging
from logging import config


def setup_loggers(app):
    """Setup loggers for a production environment"""
    logging_conf = app.config.get("LOGGING", {})
    if not logging_conf:
        return

    logging_conf["version"] = 1
    # inject app, dirty but only way
    for filter_conf in logging_conf.get("filters", {}).values():
        filter_conf["app"] = app

    # setup logging
    config.dictConfig(logging_conf)

    # mute werkzeug (sends duplicates)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
