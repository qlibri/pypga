"""
PYthon Programmable Gate Array
"""
from . import boards, core, modules
from .core import interface

import logging
from logging.handlers import RotatingFileHandler

# Basic configuration for logging
logging.basicConfig(
    handlers=[RotatingFileHandler('./pypga_warning.log', maxBytes=100000, backupCount=5)],
    level=logging.WARNING,  # Set the logging level to WARNING
    format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s() - %(message)s'  # Custom format
)
print([k for k in logging.Logger.manager.loggerDict])