from dateutil.relativedelta import *
import pytz
from operator import itemgetter
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import get_template
from django.utils import timezone
from .models import *
from pprint import pprint

ROCKET_ICON = u'\U0001F680'
REPLY_TO = settings.SUPPORT_EMAIL

def sendNewUserReportEmail(profiles, email_to):
    """Send report of new user signups. Info included:
    email, getFullNameAndDegree, npiNumber, plan_name, subscriptionId,referral
    Can raise SMTPException
    """
    from .models import UserSubscription
    from_email = settings.EMAIL_FROM
    tz = pytz.timezone(settings.LOCAL_TIME_ZONE)
    now = timezone.now()
    subject = 'New User Accounts Report - {0:%b %d %Y}'.format(now.astimezone(tz))
    if settings.ENV_TYPE != settings.ENV_PROD:
        subject = u'[test-only] ' + subject
    data = []
    for p in profiles:
        user = p.user
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        d = dict(
            user_id=user.id,
            email=user.email,
            nameAndRole=p.getFullNameAndDegree(),
            specialties=p.formatSpecialties(),
            country='',
            nbcrnaId=p.nbcrnaId,
            npiNumber=p.npiNumber,
            npiType=p.npiType,
            plan_name='',
            subscriptionId='',
            referral=''
        )
        if user_subs:
            d['plan_name'] = user_subs.plan.name
            d['subscriptionId'] = user_subs.subscriptionId
        if p.inviter:
            if p.affiliateId:
                aff = Affiliate.objects.get(user=p.inviter)
                referralName = aff.displayLabel
            else:
                referralName = p.inviter.profile.getFullName()
            d['referral'] = referralName
        if p.country:
            d['country'] = p.country.name
        data.append(d)
    ctx = {
        'data': data
    }
    message = get_template('email/new_user_report.html').render(ctx)
    msg = EmailMessage(subject, message, to=[email_to], from_email=from_email)
    msg.content_subtype = 'html'
    msg.send()

def sendReceiptEmail(user, user_subs, subs_trans):
    """Send EmailMessage receipt to user using receipt template
    Can raise SMTPException
    """
    from_email = settings.SUPPORT_EMAIL
    plan_name = u'Orbit ' + user_subs.plan.name
    subject = u'Your receipt for annual subscription to {0}'.format(plan_name)
    if settings.ENV_TYPE != settings.ENV_PROD:
        subject = u'[test-only] ' + subject
    ctx = {
        'profile': user.profile,
        'subscription': user_subs,
        'transaction': subs_trans,
        'plan_name': plan_name,
        'plan_monthly_price': user_subs.plan.monthlyPrice(),
        'support_email': settings.SUPPORT_EMAIL
    }
    message = get_template('email/receipt.html').render(ctx)
    msg = EmailMessage(subject, message, to=[user.email], from_email=from_email)
    msg.content_subtype = 'html'
    msg.send()

def sendPaymentFailureEmail(user, subs_trans):
    """Send EmailMessage receipt to user using payment_failed template
    Can raise SMTPException
    """
    from_email = settings.SUPPORT_EMAIL
    subject = u'Your Orbit Invoice Payment Failed [#{0.transactionId}]'.format(subs_trans)
    if settings.ENV_TYPE != settings.ENV_PROD:
        subject = u'[test-only] ' + subject
    username = None
    if user.profile.firstName:
        username = user.profile.firstName
    elif user.profile.npiFirstName:
        username = user.profile.npiFirstName
    else:
        username = user.email
    ctx = {
        'username': username,
        'transaction': subs_trans,
        'server_hostname': settings.SERVER_HOSTNAME,
        'support_email': settings.SUPPORT_EMAIL
    }
    message = get_template('email/payment_failed.html').render(ctx)
    msg = EmailMessage(subject, message, to=[user.email], from_email=from_email, bcc=[from_email,])
    msg.content_subtype = 'html'
    msg.send()


def sendAfflConsolationEmail(affl, start_monyear):
    """This is intended to be called once a month for the case of
    Affiliate did not earn any payout for the past month
    Args:
        affl: Affiliate instance
        start_monyear:str e.g. October 2017
    """
    from_email = settings.EMAIL_FROM
    email_to = affl.paymentEmail
    addressee = affl.user.profile.firstName
    if not addressee:
        addressee = 'Greetings'
    subject = u"{0}, here's your Orbit Associate Program statement for {1}".format(addressee, start_monyear)
    if settings.ENV_TYPE != settings.ENV_PROD:
        subject = u'[test-only] ' + subject
    subject_with_icon = u"{0} {1}".format(ROCKET_ICON, subject)
    encoded_subject = subject_with_icon.encode('utf-8')
    #print(encoded_subject)
    # get affiliateId(s) for this Affiliate
    data = AffiliateDetail.objects.filter(affiliate=affl).values('affiliateId').order_by('affiliateId')
    ctx = {
        'addressee': addressee,
        'monyear': start_monyear,
        'data': data,
        'support_email': settings.SUPPORT_EMAIL
    }
    message = get_template('email/affl_consolation.html').render(ctx)
    msg = EmailMessage(encoded_subject,
            message,
            from_email=from_email,
            to=[email_to],
            bcc=[REPLY_TO,],
            reply_to=[REPLY_TO,]
        )
    msg.content_subtype = 'html'
    msg.send()

def sendAfflEarningsStatementEmail(batchPayout, affl, afp_data):
    """This is intended to be called once a month using the batchPayout created
    for a particular month's payout.
    It sends an earnings statement email for the past month to the given affiliate
    with a tabular summary of the conversions.
    Args:
        batchPayout: BatchPayout instance - used to determine the month interval
        affl: Affiliate instance
        afp_data: list of dicts [{convertee:User, amount:Decimal, created:datetime}]
    """
    from_email = settings.EMAIL_FROM
    email_to = affl.paymentEmail
    start = batchPayout.created - relativedelta(months=1)
    start_monyear = start.strftime('%B %Y')
    addressee = affl.user.profile.firstName
    if not addressee:
        addressee = 'Greetings'
    subject = u"{0}, here's your Orbit Associate Program statement for {1}".format(addressee, start_monyear)
    if settings.ENV_TYPE != settings.ENV_PROD:
        subject = u'[test-only] ' + subject
    subject_with_icon = u"{0} {1}".format(ROCKET_ICON, subject)
    encoded_subject = subject_with_icon.encode('utf-8')
    print(encoded_subject)
    # get affiliateId(s) for this Affiliate
    affIds = AffiliateDetail.objects.filter(affiliate=affl).values_list('affiliateId', flat=True).order_by('affiliateId')
    data_by_affid = dict() # affiliateId => {num_convertees:int, total:Decimal}
    for affId in affIds:
        data_by_affid[affId] = dict(num_convertees=0, total=0)
    # group afp_data by affiliateId(s)
    for d in afp_data:
        p = d['convertee'].profile
        affId = p.affiliateId
        dd = data_by_affid[affId]
        dd['num_convertees'] += 1
        dd['total'] += d['amount']
    display_data = []
    grandTotal = 0
    totalConvertees = 0
    for affId in sorted(data_by_affid):
        dd = data_by_affid[affId]
        grandTotal += dd['total']
        totalConvertees += dd['num_convertees']
        display_data.append({
            'affiliateId': affId,
            'num_convertees': dd['num_convertees'],
            'total': dd['total']
        })
    #pprint(display_data)
    ctx = {
        'addressee': addressee,
        'monyear': start_monyear,
        'grandTotal': grandTotal,
        'totalConvertees': totalConvertees,
        'data': display_data,
        'showGrandTotal': len(display_data) > 1,
        'support_email': settings.SUPPORT_EMAIL
    }
    message = get_template('email/affl_earnings_statement.html').render(ctx)
    msg = EmailMessage(encoded_subject,
            message,
            from_email=from_email,
            to=[email_to],
            bcc=[REPLY_TO,],
            reply_to=[REPLY_TO,]
        )
    msg.content_subtype = 'html'
    msg.send()


def sendAffiliateReportEmail(total_by_affl, email_to):
    """Send report of payout that needs to be submitted to Affiliates.
    Info included: fullname, paymentEmail, num_convertees, payout, grandTotal for payout
    """
    from_email = settings.EMAIL_FROM
    tz = pytz.timezone(settings.LOCAL_TIME_ZONE)
    now = timezone.now()
    subject = 'Associate Payout Report - {0:%b %d %Y}'.format(now.astimezone(tz))
    if settings.ENV_TYPE != settings.ENV_PROD:
        subject = u'[test-only] ' + subject
    data = []
    grandTotal = 0
    totalUsers = 0
    for aff_pk in sorted(total_by_affl):
        affl = Affiliate.objects.get(pk=aff_pk)
        profile = affl.user.profile
        total = total_by_affl[aff_pk]['total']
        num_convertees = len(total_by_affl[aff_pk]['pks'])
        grandTotal += total
        totalUsers += num_convertees
        data.append({
            'name': affl.displayLabel,
            'paymentEmail': affl.paymentEmail,
            'numConvertees': num_convertees,
            'payout': str(total)
        })
    lastBatchPayout = None
    bps = BatchPayout.objects.all().order_by('-created')
    if bps.exists():
        lastBatchPayout = bps[0]
    ctx = {
        'data': data,
        'grandTotal': grandTotal,
        'totalUsers': totalUsers,
        'lastBatchPayout': lastBatchPayout
    }
    message = get_template('email/affl_payout_report.html').render(ctx)
    msg = EmailMessage(subject, message, to=[email_to], from_email=from_email)
    msg.content_subtype = 'html'
    msg.send()


def sendCardExpiredAlertEmail(user_subs, payment_method):
    """Send email alert about expired card to user
    Args:
        user_subs: UserSubscription instance
        payment_method:dict from Customer vault (getPaymentMethods)
    """
    from_email = settings.EMAIL_FROM
    email_to = user_subs.user.email
    subject = u'Heads up! Your Orbit payment method has expired'
    if settings.ENV_TYPE != settings.ENV_PROD:
        subject = u'[test-only] ' + subject
    ctx = {
        'profile': user.profile,
        'subscription': user_subs,
        'card_type': payment_method['type'],
        'card_last4': payment_method['number'][-4:]
        'expiry': payment_method['expiry'],
        'support_email': settings.SUPPORT_EMAIL
    }
    message = get_template('email/card_expired_alert.html').render(ctx)
    msg = EmailMessage(subject,
            message,
            from_email=from_email,
            to=[email_to],
            bcc=[REPLY_TO,],
            reply_to=[REPLY_TO,]
        )
    msg.content_subtype = 'html'
    msg.send()
