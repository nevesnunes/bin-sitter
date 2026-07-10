#!/usr/bin/env python3

import logging


class Formatter(logging.Formatter):
    def format(self, record):
        self._style._fmt = "%(message)s"
        return super().format(record)


logger = logging.getLogger()
_handler = logging.StreamHandler()
_handler.setFormatter(Formatter())
logger.setLevel(logging.INFO)
logger.addHandler(_handler)
