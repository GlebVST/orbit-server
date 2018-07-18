"""Tufts report - meant to be run on prod db"""
import csv
from users.models import *

outputFields = (
    'LastName',
    'FirstName',
    'Degree',
    'NPINumber',
    'Search Date',
    'Credit Earned',
    'Attendee Type',
    'TopicSearched',
    'Article/Website Consulted',
    'Change in Diagnosis?',
    'Change in Treatment?',
    'Change in clinical plan?',
    'How?',
    'Commercial bias?',
    'Comments'
)

IGNORE_USERS = (
    'faria@orbitcme.com',
    'gleb@codeabovelab.com',
    'glebst@codeabovelab.com',
    'mch@codeabovelab.com',
    'ram@corephysicsreview.com',
    'faria.chowdhury@gmail.com',
    'glebst@gmailcom',
    'mchwang@yahoo.com',
    'alexisarbeit@gmail.com',
    'testsand@weppa.org',
)

def makeReport(fpath):
    """Generate csv file of redeemed offers
    Args:
        fpath:str filepath to write to
    """
    profilesById = dict()
    profiles = Profile.objects.all().order_by('user_id')
    for p in profiles:
        profilesById[p.user_id] = p
    # get brcme entries
    filter_kwargs = dict(entry__valid=True)
    qset = BrowserCme.objects.select_related('entry').filter(**filter_kwargs).order_by('entry__activityDate')
    results = []
    for m in qset:
        user = m.entry.user
        if user.email in IGNORE_USERS:
            continue
        profile = profilesById[user.pk]
        d = dict()
        for k in outputFields:
            d[k] = ''
        d['NPINumber'] = profile.npiNumber
        if profile.lastName:
            d['LastName'] = profile.lastName.capitalize()
        elif profile.npiNumber:
            d['LastName'] = profile.npiLastName
        if profile.firstName:
            d['FirstName'] = profile.firstName.capitalize()
        elif profile.npiNumber:
            d['FirstName'] = profile.npiFirstName
        if d['LastName'] == '' or d['FirstName'] == '':
            print('Incomplete profile for {0.email}'.format(user))
            continue
        # --
        d['Degree'] = profile.formatDegrees()
        d['Search Date'] = m.entry.activityDate.strftime('%Y-%m-%d')
        d['Credit Earned'] = str(m.credits)
        d['TopicSearched'] = m.entry.description.encode("ascii", errors="ignore").decode()
        d['Article/Website Consulted'] = m.url
        if m.planEffect == 0:
            d['Change in Diagnosis?'] = 'N'
            d['Change in Treatment?'] = 'N'
        elif m.purpose == 0:
            d['Change in Diagnosis?'] = 'Y'
            d['Change in Treatment?'] = 'N'
        else:
            d['Change in Diagnosis?'] = 'N'
            d['Change in Treatment?'] = 'Y'
        d['Change in clinical plan?'] = 'N'
        results.append(d)
    # write results to file
    with open(fpath, 'wb') as f:
        writer = csv.DictWriter(f, delimiter=',', fieldnames=outputFields)
        writer.writeheader()
        for row in results:
            writer.writerow(row)
    print('Done')
