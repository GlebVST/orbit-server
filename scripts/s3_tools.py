"""S3 tools
Reference: http://boto3.readthedocs.io/en/latest/reference/services/s3.html
This code was written for boto3 v1.4.4
"""
import boto3
import os
from django.conf import settings

CERT_DIR = settings.CERTIFICATE_MEDIA_BASEDIR

def getResourceFromSettings():
    """Create s3 resource from AWS settings in settings.py"""
    s3r = boto3.resource('s3', aws_access_key_id=settings.AWS_ACCESS_KEY_ID, aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY)
    return s3r

def getResourceFromSession(profileName='orbit'):
    """This expects a .aws credentials file in the home dir with the requested profile"""
    session = boto3.Session(profile_name=profileName)
    s3r = session.resource('s3') # s3.ServiceResource object
    for b in s3r.buckets.all():
        print(b)
    return s3r


def getClientFromResource(s3r):
    """Args:
        s3r: S3 resource from session
    """
    client = s3r.meta.client
    return client

def getBucket(s3r, name):
    bucket = s3r.Bucket(name=name)
    return bucket

def setUserDir(user):
    return 'uid_{0}'.format(user.pk)

def getCertificatesForUser(bucket, user):
    """Returns list of objects in bucket for user certificates"""
    userDir = setUserDir(user)
    prefix = os.path.join(CERT_DIR, userDir)
    objs = list(bucket.objects.filter(Prefix=prefix))
    return objs

def getObject(s3r, bucket, mediaDir, user, fileName):
    userDir = setUserDir(user)
    key = os.path.join(mediaDir, userDir, fileName)
    obj = s3r.Object(bucket.name, key)
    print(obj.content_type) # this will force a GET on the obj
    return obj

def isSuccessResponse(response):
    status_code = response.get('ResponseMetadata', {}).get('HTTPStatusCode', None)
    return status_code == 200

def copyObjectAsAttachment(client, sourceObj, new_key):
    """Make copy of the sourceObj in the same bucket with key=new_key
    and set ContentDisposition to: attachment
    Returns: response
    """
    response = client.copy_object(
        ACL='private',
        Bucket=sourceObj.bucket_name,
        ContentDisposition='attachment',
        ContentType=sourceObj.content_type,
        CopySource=os.path.join(sourceObj.bucket_name, sourceObj.key),
        Key=new_key,
        MetadataDirective='REPLACE' # the Metadata will be set from ContentType/ContentDisposition specified
    )
    print(response)
    return response

def copyCertificateAsAttachment(s3r, bucket, user, certName):
    """Args:
        s3r: s3 resource
        certName: str certificate name
    Returns: destObject is newly created, else None
    """
    try:
        sourceObj = getObject(s3r, bucket, CERT_DIR, user, certName)
    except:
        print('sourceObj does not exist: {0}'.format(certName))
    else:
        client = getClientFromResource(s3r)
        # make key name for the new object
        fname, ext = os.path.splitext(certName)
        newCertName = fname + '_dl' + ext
        userDir = setUserDir(user)
        new_key = os.path.join(CERT_DIR, userDir, newCertName)
        # does new_key exist already
        try:
            response = client.head_object(Bucket=bucket.name, Key=new_key)
        except:
            # destObj does not exist, proceed
            response = copyObjectAsAttachment(client, sourceObj, new_key)
            is_success = isSuccessResponse(response)
            if is_success:
                destObj = getObject(s3r, bucket, CERT_DIR, user, newCertName)
                print('ContentDisposition: {0}'.format(destObj.content_disposition))
                # nope: does not work
                ##destObj.metadata.update({'Content-Disposition': 'attachment'})
                return destObj
            else:
                print('Copy failed')
        else:
            print('destObj already exists: {0}'.format(new_key))
            return
