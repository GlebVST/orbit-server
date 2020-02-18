import pandas as pd
import logging
from datetime import datetime
import pytz
from users.models import *

logger = logging.getLogger('mgmt.rpenr')

def parseDataFrame(df):
    """Parse DataFrame
    df = pd.read_csv(some_file.csv)
    """
    data = []
    teams = set([])
    for index, row in df.iterrows():
        if not row['Last Name']:
            continue
        middleName = row['Middle Name'] or ''
        if type(middleName) == type(3.33):
            middleName = ''
        d = dict(
            lastName=row['Last Name'].strip(),
            firstName=row['First Name'].strip(),
            middleName=middleName.strip(),
            npiNumber=str(row['Individual NPI']).strip(),
            team=row['RP Team'].strip()
        )
        teams.add(d['team'])
        d['lcFullName'] = OrgEnrollee.objects.makeSearchName(d['firstName'], d['lastName'])
        data.append(d)
        print("{lastName} {firstName} {npiNumber} {team}".format(**d))
    return (data, teams)

def insertGroups(org, teams):
    groups = dict() # team name => OrgGroup
    for team in teams:
        og, created = OrgGroup.objects.get_or_create(organization=org, name=team)
        groups[team] = og
    return groups

def insertEnrollees(org, groups, data):
    enrollees = dict() # npi => OrgEnrollee
    for d in data:
        npi = d['npiNumber']
        qs = OrgEnrollee.objects.filter(organization=org, npiNumber=npi)
        if qs.exists():
            enrollees[npi] = qs[0]
        else:
            og = groups[d['team']]
            oe = OrgEnrollee.objects.create(
                organization=org,
                group=og,
                npiNumber=npi,
                firstName=d['firstName'],
                lastName=d['lastName'],
                middleName=d['middleName'],
                lcFullName=d['lcFullName']
            )
            enrollees[npi] = oe
        # does npi/lastName match any existing profile?
        qs = Profile.objects.filter(npiNumber=npi, lastName__iexact=d['lastName']).order_by('-pk')
        if not qs.exists():
            continue
        num_profiles = qs.count()
        if num_profiles == 1:
            oe.user = qs[0].user
            oe.save()
            print('Assign {0.npiNumber} {0.lastName} to User {0.user}'.format(oe))
        else:
            print('! Found {0} profile matches for {npiNumber} {lastName}'.format(**d)) 
    return enrollees

def endEnterpriseSubscription(org):
    """End enterprise subscription for all providers in org"""
    newEndDate = datetime(2020,4,1, tzinfo=pytz.utc)
    profiles = Profile.objects.filter(organization=org).order_by('pk')
    for profile in profiles:
        user = profile.user
        qs = OrgMember.objects.filter(organization=org, user=user).order_by('-pk')
        if not qs.exists():
            print('! No OrgMember found for {0}'.format(profile))
            continue
        # handle admin users separately because they need to still see the admin reports for enrollment
        if orgm.is_admin:
            print('Adjust admin {0}'.format(orgm))
            user_subs = UserSubscription.objects.getLatestSubscription(user)
            user_subs.billingEndDate = newEndDate
            user_subs.save()
            continue
        # regular provider
        UserSubscription.objects.endEnterpriseSubscription(user)
    return profiles
