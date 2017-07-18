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

        # Attempt to acquire lock to write to buf, otherwise write to secondary as flush occurs
        if not self.lock.acquire(blocking=False):
            logger.info('Primary buffer locked, log to secondary: {}'.format(message))
            self.secondary.append(message)
        else:
            logger.info('Buffer LogDNA message: {}'.format(message))
            self.buf.append(message)
            self.lock.release()
            if self.bufByteLength >= self.flushLimit:
                self.flush()
                return

        if not self.flusher:
            logger.debug('Starting a flusher/timer thread as none found: {}'.format(self.flusher))
            self.flusher = Timer(defaults['FLUSH_INTERVAL'], self.flush)
            self.flusher.start()

    def flush(self):
        if not self.buf or len(self.buf) < 0:
            logger.debug('Nothing to flush in a primary buffer - no log entries yet (secondary: {})'.format(len(self.secondary)))
            return
        data = {'e': 'ls', 'ls': self.buf}
        try:
            # Ensure we have the lock when flushing
            if not self.lock.acquire(blocking=False):
                if not self.flusher:
                    self.flusher = Timer(defaults['FLUSH_NOW'], self.flush)
                    self.flusher.start()
            else:
                logger.info('Sending {} log entries to LogDNA API'.format(len(self.buf)))
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
                self.lock.release()
                # Ensure messages that could've dropped are appended back onto buf
                self.buf = self.buf + self.secondary
                self.secondary = []
        except requests.exceptions.RequestException as e:
            self.lock.release()
            logger.exception('Error in request to LogDNA: ' + str(e))
