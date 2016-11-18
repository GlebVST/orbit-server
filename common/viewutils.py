"""Common utility functions"""
import datetime
import decimal
import hashlib
import json
import uuid
from django.http import HttpResponse, JsonResponse
from urlparse import urlparse

def jsonSerialize(obj):
    if isinstance(obj, datetime.datetime):
        # for consistency, and to save space, don't return microseconds
        date = obj.replace(microsecond=0)
        return date.isoformat()
    elif isinstance(obj, uuid.UUID):
        return str(obj)
    elif isinstance(obj, decimal.Decimal):
        return str(obj)
    else:
        raise TypeError ("Type not serializable")

class MyJsonResponse(HttpResponse):
    def __init__(self, context, status_code, **response_kwargs):
        super(MyJsonResponse, self).__init__(
            content=json.dumps(context, default=jsonSerialize),
            content_type='application/json',
            status=status_code,
            **response_kwargs
        )

# used by function views
def render_to_json_response(context, status_code=200, **response_kwargs):
    resp = MyJsonResponse(
        context,
        status_code,
        **response_kwargs
    )
    resp['X-Frame-Options'] = 'ALLOWALL'
    return resp

# used by cb views
class JsonResponseMixin(object):
    def render_to_json_response(self, context, status_code=200, **response_kwargs):
        resp = MyJsonResponse(
            context,
            status_code,
            **response_kwargs
        )
        resp['X-Frame-Options'] = 'ALLOWALL'
        return resp

def parseUriDomain(url):
    parsed_uri = urlparse(url)
    domain = '{uri.scheme}://{uri.netloc}/'.format(uri=parsed_uri)
    print(domain)
    return domain

def md5_uploaded_file(f):
#    print('begin md5calc on file:{0}/{1}'.format(f.name, f.content_type))
    md5 = hashlib.md5()
    for chunk in f.chunks():
        md5.update(chunk)
    return md5.hexdigest()

def newUuid():
    return uuid.uuid4()
