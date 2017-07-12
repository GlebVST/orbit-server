"""logging function wrapper to pass request.user to the LogRecord"""
from django.forms.models import model_to_dict

# logdna meta object
def getMeta(request):
    if not request:
        return {}
    return {
        'meta': {
            'remote_user': model_to_dict(request.user) if request.user.is_authenticated else 'Anonymous',
            'remote_addr': request.META.get('REMOTE_ADDR'),
            'proxies': request.META.get('HTTP_X_FORWARDED_FOR')
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

