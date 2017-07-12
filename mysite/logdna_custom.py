from logdna.logdna import LogDNAHandler
from logdna.configs import defaults
import logging
import requests

logger = logging.getLogger('logdna')

class LogDNAHandlerCustom(LogDNAHandler):
    def flush(self):
        if not self.buf or len(self.buf) < 0:
            return
        data = {'e': 'ls', 'ls': self.buf}
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
