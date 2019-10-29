"""Common utility functions"""
import hashlib
import uuid
from urllib.parse import urlparse
#from rest_framework import mixins
from rest_framework.generics import UpdateAPIView, RetrieveUpdateAPIView

class ExtUpdateAPIView(UpdateAPIView):
    """Extended view that allow POST method to be
    equivalent to PATCH method. This is because some users' firewalls
    do not allow PATCH method. Added 2019-10-28.
    """
    def post(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

class ExtRetrieveUpdateAPIView(RetrieveUpdateAPIView):
    """Extended class that allows POST to be equivalent to PATCH"""
    def post(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

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
