import os
import boto3
import mimetypes

PROFILE_NAME = 'orbit'
BUCKET_DEV = 'orbitcme-dev'
BUCKET_PROD = 'orbitcme-prod'
LOGOS_FOLDER = 'logos/'

def get_s3(profileName=PROFILE_NAME):
    """
    profileName:str from .aws/credentials
    Returns s3.ServiceResource object
    """
    session = boto3.Session(profile_name=profileName)
    s3 = session.resource('s3')
    return s3

def upload_file(s3, bucketName, fpath):
    """Upload file object
    s3: s3.ServiceResource object
    bucketName: str
    fp: opened file object
    fileName:str for key in bucket
    """
    fileName = os.path.basename(fpath)
    mime = mimetypes.guess_type(fileName)
    content_type = mime[0]
    try:
        fp = open(fpath, 'rb')
        response = s3.Object(bucketName, LOGOS_FOLDER+fileName).put(
            ACL='public-read',
            Body=fp,
            ContentType=content_type
        )
        print('Status: {0}'.format(response['ResponseMetadata']['HTTPStatusCode']))
        print('ETag: {0}'.format(response['ETag']))
    except IOError, e:
        print(str(e))
    else:
        obj = s3.Object(bucketName, LOGOS_FOLDER+fileName)
        for g in obj.Acl().grants:
            print(g)
        return obj

