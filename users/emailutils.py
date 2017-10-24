from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import get_template
from django.utils import timezone
import pytz

def sendAffiliateReportEmail(total_by_affl, email_to):
    """Send report of payout that needs to be submitted to Affiliates.
    Info included: fullname, paymentEmail, num_convertees, payout, grandTotal for payout
    """
    from .models import Affiliate
    from_email = settings.EMAIL_FROM
    tz = pytz.timezone(settings.LOCAL_TIME_ZONE)
    now = timezone.now()
    subject = 'Affiliate Payout Report - {0:%b %d %Y}'.format(now.astimezone(tz))
    if settings.ENV_TYPE != settings.ENV_PROD:
        subject = u'[test-only] ' + subject
    data = []
    grandTotal = 0
    for aff_pk in total_by_affl:
        affl = Affiliate.objects.get(pk=aff_pk)
        profile = affl.user.profile
        total = total_by_affl[aff_pk]['total']
        num_convertees = len(total_by_affl[aff_pk]['pks'])
        grandTotal += total
        data.append({
            'fullName': profile.getFullName(),
            'paymentEmail': affl.paymentEmail,
            'numConvertees': num_convertees,
            'payout': str(total)
        })
    ctx = {
        'data': data,
        'grandTotal': grandTotal
    }
    message = get_template('email/affl_payout_report.html').render(ctx)
    msg = EmailMessage(subject, message, to=[email_to], from_email=from_email)
    msg.content_subtype = 'html'
    msg.send()

def sendNewUserReportEmail(profiles, email_to):
    """Send report of new user signups. Info included:
    email, getFullNameAndDegree, npiNumber, plan_name, subscriptionId
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
            npiNumber=p.npiNumber,
            npiType=p.npiType,
            plan_name='',
            subscriptionId=''
        )
        if user_subs:
            d['plan_name'] = user_subs.plan.name
            d['subscriptionId'] = user_subs.subscriptionId
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
    msg = EmailMessage(subject, message, to=[user.email], from_email=from_email)
    msg.content_subtype = 'html'
    msg.send()
