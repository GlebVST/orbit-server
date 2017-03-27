"""logging function wrapper to pass request.user to the LogRecord"""
import logging

def logDebug(logger, request, message):
    logger.debug(message, extra={'requser': request.user})

def logInfo(logger, request, message):
    logger.info(message, extra={'requser': request.user})

def logWarning(logger, request, message):
    logger.warning(message, extra={'requser': request.user})

def logError(logger, request, message):
    logger.error(message, extra={'requser': request.user})

def logException(logger, request, message):
    logger.exception(message, extra={'requser': request.user})
