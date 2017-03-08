"""Common utility functions"""
import logging
import datetime
import decimal
import hashlib
import json
import uuid
from urlparse import urlparse
from django.http import HttpResponse
from rest_framework.renderers import JSONRenderer

class JSONResponse(HttpResponse):
    def __init__(self, context, **kwargs):
        content=JSONRenderer().render(context)
        kwargs['content_type'] ='application/json'
        super(JSONResponse, self).__init__(content, **kwargs)

# used by function views
def render_to_json_response(context, status_code=200, **response_kwargs):
    response_kwargs['status'] = status_code
    resp = JSONResponse(context, **response_kwargs)
    return resp

# used by non-DRF cb views
class JsonResponseMixin(object):
    def render_to_json_response(self, context, status_code=200, **response_kwargs):
        response_kwargs['status'] = status_code
        resp = JSONResponse(context, **response_kwargs)
        return resp

def parseUriDomain(url):
    parsed_uri = urlparse(url)
    domain = '{uri.scheme}://{uri.netloc}/'.format(uri=parsed_uri)
    print(domain)
    return domain

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

# http://stackoverflow.com/questions/4581789/how-do-i-get-user-ip-address-in-django
def getClientIp(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


