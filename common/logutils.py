"""logging function wrapper to pass request.user to the LogRecord"""

# logdna meta object
def getMeta(request):
    if not request:
        return {}
    return {
        'meta': {
            'remote_user': request.user.username if request.user.is_authenticated else 'Anonymous',
            'remote_addr': request.META.get('REMOTE_ADDR'),
            'proxies': request.META.get('X_FORWARDED_FOR')
        }
    }

def logDebug(logger, request, message):
    logger.debug(message, getMeta(request), extra={'requser': request.user})

def logInfo(logger, request, message):
    logger.info(message, getMeta(request), extra={'requser': request.user})

def logWarning(logger, request, message):
    logger.warning(message, getMeta(request), extra={'requser': request.user})

def logError(logger, request, message):
    logger.error(message, getMeta(request), extra={'requser': request.user})

def logException(logger, request, message):
    logger.exception(message, getMeta(request), extra={'requser': request.user})

