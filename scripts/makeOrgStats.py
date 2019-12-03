"""Report used for RP pricing"""
import csv
from datetime import timedelta
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone
from users.models import *
from users.emailutils import makeCsvForAttachment

fieldNamesMap = {
    'providers': ('status','email','lastName','firstName','group','birthDate','age','creditsRedeemed'),
    'groups': ('group','totalCredits','avgCreditsPerProvider','numActiveProviders','totalProviders'),
    'age': ('age','totalCredits','avgCreditsPerProvider','numActiveProviders','totalProviders'),
    'tags': ('tag','totalCredits'),
    'oagg': ('year','month','activeUsers','invitedUsers','totalUsers','addedUsers','expiredLicenses','expiredCMEGap')
}

def makeCsvAttachment(tabName, data):
    fieldNames = fieldNamesMap[tabName]
    cf = makeCsvForAttachment(fieldNames, data)
    return cf

def sendEmail(attachments):
    to_emails = ['faria.chowdhury@gmail.com',]
    subject='RP Stats Oct 2019'
    message = 'See attached files'
    msg = EmailMessage(
            subject,
            message,
            to=to_emails,
            cc=[],
            bcc=[],
            from_email=settings.EMAIL_FROM)
    msg.content_subtype = 'html'
    for d in attachments:
        msg.attach(d['fileName'], d['contentFile'], 'application/octet-stream')
    msg.send()
    print('Email sent')

def makeProviderData(providers):
    """Provider (status, group, first name, last name, email, birthDate), creditsRedeemed
    Exclude group Orbit
    Returns: list of dicts
    """
    now = timezone.now()
    today = now.date()
    data = []
    for orgm in providers:
        user = orgm.user
        profile = user.profile
        uc = UserCmeCredit.objects.get(user=user)
        if profile.birthDate:
            td = today - profile.birthDate
            age = round(td.days/365.0)
        else:
            age = 0
        groupName = orgm.group.name if orgm.group else ''
        if groupName.lower() == 'orbit':
            continue
        d = dict(
            user=user,
            group=groupName,
            email=user.email,
            status=orgm.enterpriseStatus,
            firstName= profile.firstName,
            lastName= profile.lastName,
            npiNumber=profile.npiNumber,
            age=age,
            birthDate=profile.birthDate or '',
            creditsRedeemed=uc.total_credits_earned,
            creditsRedeemedStr=str(uc.total_credits_earned),
        )
        data.append(d)
    return data

def makeTagData(providerData):
    """Each row:
        tagName|totalCredits
    Returns: list of dicts sorted by tag
    """
    tagDict = {}
    eType = EntryType.objects.get(name=ENTRYTYPE_BRCME)
    for d in providerData:
        user = d['user']
        entries = Entry.objects.filter(user=user, entryType=eType, valid=True).prefetch_related('tags').order_by('id')
        for entry in entries:
            tags = entry.tags.all()
            for tag in tags:
                tagName = tag.name
                if tagName not in tagDict:
                    tagDict[tagName] = 0
                tagDict[tagName] += ARTICLE_CREDIT
        print("{0} numEntries: {1}".format(user, len(entries)))
    # make list of dicts
    data = []
    for tagName in sorted(tagDict):
        data.append({'tag': tagName, 'totalCredits': tagDict[tagName]})
    return data

def makeAgeData(providerData):
    """Each row:
        age|totalCredits|avgCreditsPerProvider|numActiveProviders|totalProviders
    Returns: list of dicts sorted by age asc
    """
    groupAgg = dict()
    for d in providerData:
        group = d['age']
        if not group in groupAgg:
            groupAgg[group] = {'totalCredits': 0, 'numActiveProviders': 0, 'totalProviders': 0}
        groupAgg[group]['totalCredits'] += d['creditsRedeemed']
        groupAgg[group]['totalProviders'] += 1
        if d['status'] == OrgMember.STATUS_ACTIVE:
            groupAgg[group]['numActiveProviders'] += 1
    # calc avgCredits per group: totalCredits/totalProviders
    for group in groupAgg:
        totalProviders = groupAgg[group]['totalProviders']
        totalCredits = groupAgg[group]['totalCredits']
        groupAgg[group]['avgCreditsPerProvider'] = "{:0.2f}".format(totalCredits/totalProviders)
    # final data
    data = []
    for group in sorted(groupAgg):
        d = groupAgg[group]
        d['age'] = group
        data.append(d)
    return data

def makeGroupData(providerData):
    """Each row is:
        group|totalCredits|avgCreditsPerProvider|numActiveProviders|totalProviders
    Returns: list of dicts sorted by groupname asc
    """
    groupAgg = dict()
    for d in providerData:
        group = d['group']
        if not group in groupAgg:
            groupAgg[group] = {'totalCredits': 0, 'numActiveProviders': 0, 'totalProviders': 0}
        groupAgg[group]['totalCredits'] += d['creditsRedeemed']
        groupAgg[group]['totalProviders'] += 1
        if d['status'] == OrgMember.STATUS_ACTIVE:
            groupAgg[group]['numActiveProviders'] += 1
    # calc avgCredits per group: totalCredits/totalProviders
    for group in groupAgg:
        totalProviders = groupAgg[group]['totalProviders']
        totalCredits = groupAgg[group]['totalCredits']
        groupAgg[group]['avgCreditsPerProvider'] = "{:0.2f}".format(totalCredits/totalProviders)
    # final data
    data = []
    for group in sorted(groupAgg):
        d = groupAgg[group]
        d['group'] = group
        data.append(d)
    return data

def makeOrgAggData(org, startMY, endMY):
    """Get OrgAgg data for the last day of each month from startMY to endMY inclusive
    Returns: list of dicts ordered by day
    """
    startMonth = startMY[0]; startYear = startMY[1]
    endMonth = endMY[0]; endYear = endMY[1]
    data = []
    KEYS = ('activeUsers','invitedUsers','totalUsers','addedUsers','expiredLicenses','expiredCMEGap')
    for year in range(startYear, endYear+1):
        for month in range(startMonth, endMonth+1):
            d = {'year': year, 'month': month}
            for key in KEYS:
                d[key] = 0
            qs = org.orgaggs.filter(day__month=month, day__year=year).order_by('-day')
            if not qs.exists():
                data.append(d)
                continue
            m = qs[0] # latest day in db for (month,yr)
            d['activeUsers'] = m.users_active
            d['invitedUsers'] = m.users_invited
            d['totalUsers'] = m.users_active + m.users_invited
            d['expiredLicenses'] = m.licenses_expired
            d['expiredCMEGap'] = m.cme_gap_expired
            data.append(d)
    # calc addedUsers
    zipped = zip(data, data[1:])
    for d1,d2 in zipped:
        diff = d2['totalUsers'] - d1['totalUsers']
        d2['addedUsers'] = diff
    for d in data:
        print("{month}|{activeUsers}|{invitedUsers}|{totalUsers}|{addedUsers}".format(**d))
    return data

def main(org):
    providers = org.orgmembers \
        .filter(is_admin=False) \
        .select_related('group', 'user__profile') \
        .order_by('user__profile__lastName','user__profile__firstName','id')
    #providerData = makeProviderData(providers)
    #tagData = makeTagData(providerData)
    #groupData = makeGroupData(providerData)
    #ageData = makeAgeData(providerData)
    oaggData = makeOrgAggData(org, startMY=(2, 2019), endMY=(10,2019))
    attachments = [
        #dict(fileName='providers.csv', contentFile=makeCsvAttachment('providers', providerData)),
        #dict(fileName='groups.csv', contentFile=makeCsvAttachment('groups', groupData)),
        #dict(fileName='age.csv', contentFile=makeCsvAttachment('age', ageData))
        #dict(fileName='tags.csv', contentFile=makeCsvAttachment('tags', tagData))
        dict(fileName='oagg.csv', contentFile=makeCsvAttachment('oagg', oaggData))
    ]
    sendEmail(attachments)
    return oaggData
