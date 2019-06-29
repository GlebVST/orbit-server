"""Common utility functions"""
import hashlib
import uuid
from urllib.parse import urlparse


def getUrlLastPart(url):
    output = urlparse(url.strip('/')) # strip any trailing slash
    last_part = output.path.rpartition('/')[-1]
    #print(last_part)
    return last_part


def md5_uploaded_file(f):
#    print('begin md5calc on file:{0}/{1}'.format(f.name, f.content_type))
    md5 = hashlib.md5()
    for chunk in f.chunks():
        md5.update(chunk)
    return md5.hexdigest()

def newUuid():
    return uuid.uuid4()
