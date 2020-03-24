"""2020-03-23
Usage: 
    % python manage.py shell
    >> from scripts import processCprCerts as s
    >> data, users, entries = s.main(path_to_csv_file)
    >> # check and verify data/users/entries as needed
Pre-requisites:
    1. Local CSV file exists with fields: Last Name, First Name, Email
    2. It expects that for each user in the csv file, there is a corresponding
        certificate PDF file in the CERT_DIR directory (specified below).

This script creates sr-cme entries for the CPR users listed in the csv file
that is input to the main function. Starting from j=1, it matches the
j-th user in the csv file with the cert_j.pdf file where j is 0-padded
(009, 099, 999) upto 3 digits. It creates a Document for each PDF file
and associates the sr-cme entry with the Document.

Notes:
1. If the csv file contains a user that does not exist, it creates a User
  instance, and OrgMember instance using the cpr organization. You must
  invite the user using the Admin dashboard, and assign the user to the
  correct group because this script does not do it. All users *should*
  have already been created by a different import script.
2. Ensure that CERT_DATE below is set to the date of the course completion,
 this date is used as the activityDate of the entry.
"""
import os
import csv
import logging
from datetime import datetime
import hashlib
from hashids import Hashids
import pytz
from time import sleep
# django
from django.core.files import File
from django.conf import settings
from django.db import transaction
from django.utils import timezone
# proj
from common.signals import profile_saved
# users
from users.models import *
from users.auth0_tools import Auth0Api
from users.enterprise_serializers import OrgMemberFormSerializer

logger = logging.getLogger('mgmt.cprct')
hashgen = Hashids(salt=settings.DOCUMENT_HASHIDS_SALT, min_length=10)

CONTENT_TYPE = 'application/pdf'
CERT_DIR = '/home/ubuntu/orbit_server/import/certs'
CERT_DATE = datetime(2020,3,13, tzinfo=pytz.utc) # last day of the course
CERT_DESCR = 'Core Physics Review'
CERT_CREDIT_TYPE = CreditType.objects.get(abbrev='Class')
ETYPE = EntryType.objects.get(name=ENTRYTYPE_SRCME)

fieldnames = ('Last Name', 'First Name', 'Email')

deg_md = Degree.objects.get(abbrev='MD')
ps_rad = PracticeSpecialty.objects.get(name='Radiology')
country_usa = Country.objects.get(code=Country.USA)
org = Organization.objects.get(joinCode='cpr')
plan = SubscriptionPlan.objects.getEnterprisePlanForOrg(org)
defaultGroup = OrgGroup.objects.get(organization=org, name='2020-west')

def readCsv(fpath):
    data = []
    try:
        f = open(fpath, 'r')
        reader = csv.DictReader(f, fieldnames=fieldnames, restkey='extra')
        all_data = [row for row in reader]
        data = all_data[1:]
        f.close()
    except csv.Error as e:
        error_msg = "CsvError: {0}".format(e)
        logger.warning(error_msg)
        print(error_msg)
    return data

def createUser(api, d):
    """Create new User (MD/Radiology specialty)
    Args:
        api: Auth0Api instance
        d: dict with keys: First Name, Last Name, Email
    Returns: User instance
    Ideally, this should not be called as all users should have already been
    created by a separate import script. But in order to map the correct
    certificate pdf to the correct user, we create any users that do not
    already exist.
    Admin must assign the new users to the correct group.
    """
    form_data = {
        'is_admin': False,
        'firstName': d['First Name'],
        'lastName': d['Last Name'],
        'email': d['Email'].lower(),
        'password_ticket': False,
        'group': defaultGroup.pk,
        'country': country_usa.pk,
        'degrees': [deg_md.pk,],
        'specialties': [],
        'subspecialties': [],
        'states': [],
        'deaStates': [],
        'fluoroscopyStates': [],
        'hospitals': [],
        'residency_program': None,
        'npiNumber': ''
    }
    ser = OrgMemberFormSerializer(data=form_data)
    ser.is_valid(raise_exception=True)
    user = None
    with transaction.atomic():
        orgmember = ser.save(organization=org, plan=plan, apiConn=api)
        # Update profile
        user = orgmember.user
        profile = user.profile
        # this is NOT done by OrgMemberFormSerializer! - it takes in the args but does not use them
        profile.degrees.add(deg_md)
        profile.specialties.add(ps_rad)
        # ProfileCmetags
        add_tags = profile.addOrActivateCmeTags()
        # emit profile_saved signal
        ret = profile_saved.send(sender=profile.__class__, user_id=user.pk)
    msg = u"Created OrgMember: {0.pk}|{0}. Please assign to correct group, and invite the user.".format(orgmember)
    logger.info(msg)
    print(msg)
    sleep(1)
    return user

def getUsers(data):
    users = []
    api = Auth0Api()
    for d in data:
        try:
            u = User.objects.get(email__iexact=d['Email'])
        except User.DoesNotExist:
            print(d)
            print('! No user found for {Email}'.format(**d))
            u = createUser(api, d)
            users.append(d)
        else:
            users.append(u)
    return users

def createCertDocument(user, certfpath):
    """Create Document instance for the given user and pdf file"""
    certName = "CorePhysicsReview_{0}".format(os.path.basename(certfpath))
    # check if exists already
    qs = Document.objects.filter(user=user, name=certName, is_certificate=True)
    if qs.exists():
        instance = qs[0]
        print('Existing document {0.pk}/{0}'.format(instance))
        return instance
    # create Document
    f = open(certfpath, 'rb')
    md5sum = hashlib.md5(f.read()).hexdigest()
    docName = '{0}.pdf'.format(md5sum)
    #print('Filename: {0}'.format(docName))
    f.close()
    instance = Document(
        md5sum=md5sum,
        name=certName,
        content_type=CONTENT_TYPE,
        image_h=None,
        image_w=None,
        set_id='',
        user=user,
        is_certificate=True
    )
    f = open(certfpath, 'rb')
    df = File(f) # Django File object
    # upload the file to user's folder in AWS, and save the instance
    instance.document.save(docName, df, save=True)
    instance.referenceId = 'document' + hashgen.encode(instance.pk)
    instance.save(update_fields=('referenceId',))
    df.close()
    #print('New docId: {0.pk} for: {0.user}'.format(instance))
    logger.info('New docId: {0.pk} for: {0.user}'.format(instance))
    return instance

def createSrEntry(j, user):
    """Create sr-cme entry for the given user.
    Assign j-th local certificate filepath to a certificate Document
    Associate document with entry
    Note: if entry for user/activityDate/creditType already exists, it returns
        the existing entry immediately
    Returns: Entry instance
    """
    cert_idx = str(j).zfill(3)
    certname = 'cert_{0}.pdf'.format(cert_idx)
    certfpath = os.path.join(CERT_DIR, certname)
    if not os.path.isfile(certfpath):
        raise ValueError('Invalid local filepath: {0}'.format(certfpath))
        return
    # check if entry already exists (if so, ignore certfpath and return immediately)
    qs = user.entries.filter(entryType=ETYPE, activityDate=CERT_DATE, creditType=CERT_CREDIT_TYPE)
    if qs.exists():
        entry = qs[0]
        print('Return existing entry {0}'.format(entry))
        return entry
    #print("Assign User {0} to {1}".format(user, certfpath))
    # create document
    document = createCertDocument(user, certfpath)
    entry = Entry(
        entryType=ETYPE,
        activityDate=CERT_DATE,
        description=CERT_DESCR,
        creditType=CERT_CREDIT_TYPE,
        user=user
    )
    entry.save()
    # Using parent entry, create SRCme instance
    srcme = SRCme.objects.create(entry=entry, credits=0)
    # set entry.documents
    entry.documents.add(document)
    #print(entry.documents.all()[0])
    return entry

def processUsers(users):
    """Call createSREntry for each user start from index=1
    Returns: list of sr-cme entries
    """
    entries = []
    for j, user in enumerate(users):
        entry = createSrEntry(j+1, user)
        entries.append(entry)
    return entries

def main(fpath, createEntries=True):
    """Read and process the users in the given csv file
    Args:
        fpath: path to CSV file
        createEntries: bool (if True: will create sr-cme entries)
            pass False, if you want to debug/only see the users.
    Returns: (3-tuple) (data:list of dicts from csv file, users, entries)
    """
    data = readCsv(fpath)
    users = getUsers(data)
    entries = []
    if createEntries:
        entries = processUsers(users)
    return (data, users, entries)
