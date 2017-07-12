import sys
from logdna.logdna import LogDNAHandler
from logdna.configs import defaults
import logging
import requests
from threading import Timer

logger = logging.getLogger('logdna')

class LogDNAHandlerCustom(LogDNAHandler):
    def bufferLog(self, message):
        if message and message['line']:
            if self.max_length and len(message['line']) > defaults['MAX_LINE_LENGTH']:
                message['line'] = message['line'][:defaults['MAX_LINE_LENGTH']] + ' (cut off, too long...)'
                logger.debug('Line was longer than ' + str(defaults['MAX_LINE_LENGTH']) + ' chars and was truncated.')

            self.bufByteLength += sys.getsizeof(message)
            logger.info('Buffer LogDNA message: {}'.format(message))
            self.buf.append(message)

            if self.bufByteLength >= self.flushLimit:
                self.flush()
                return

            if not self.flusher:
                self.flusher = Timer(defaults['FLUSH_INTERVAL'], self.flush)
                self.flusher.start()

    def flush(self):
        if not self.buf or len(self.buf) < 0:
            return
        data = {'e': 'ls', 'ls': self.buf}
        logger.info('Sending LogDNA API write request: {}'.format(data))
        try:
            resp = requests.post(url=defaults['LOGDNA_URL'], json=data, auth=('user', self.token), params={ 'hostname': self.hostname }, stream=True, timeout=defaults['MAX_REQUEST_TIMEOUT'])
            if resp.status_code != 200:
                logger.warn('Error logging to LogDNA: HTTP {} - {}'.format(resp.status_code, resp.content))
            else:
                logger.info('Sent LogDNA API request: HTTP {} - {}'.format(resp.status_code, resp.content))
            self.buf = []
            self.bufByteLength = 0
            if self.flusher:
                self.flusher.cancel()
                self.flusher = None
        except requests.exceptions.RequestException as e:
            logger.error('Error in request to LogDNA: ' + str(e))
