from __future__ import unicode_literals
import logging
from dateutil.relativedelta import *
from datetime import timedelta
import csv
import premailer
import io
from io import StringIO
from operator import itemgetter
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import get_template
from django.utils import timezone
from common.dateutils import LOCAL_TZ, fmtLocalDatetime
from .models import *
from pprint import pprint

ROCKET_ICON = '\U0001F680'
REPLY_TO = settings.SUPPORT_EMAIL

TEST_ONLY_PREFIX = '[test-only] '

def makeSubject(subject):
    if settings.ENV_TYPE != settings.ENV_PROD:
        subject = TEST_ONLY_PREFIX + subject
    return subject

def getHostname():
    """Handle mapping admin to either prod or test server"""
    hostname = settings.SERVER_HOSTNAME
    if hostname.startswith('admin.'): # admin.orbitcme.com becomes orbitcme.com for links in emails
        hostname = hostname.replace('admin.', '')
    elif hostname.startswith('testadmin.'): # testadmin.orbitcme.com becomes test1.orbitcme.com for links in emails
        hostname = hostname.replace('testadmin', 'test1')
    return hostname

def setCommonContext(ctx):
    hostname = getHostname()
    ctx.update({
        'server_hostname': hostname,
        'login_link': settings.UI_LINK_LOGIN,
        'feedback_link': settings.UI_LINK_FEEDBACK,
        'subscription_link': settings.UI_LINK_SUBSCRIPTION,
        'support_email': settings.SUPPORT_EMAIL,
    })

def sendNewUserReportEmail(profiles, email_to):
    """Send report of new user signups. Info included:
    email, getFullNameAndDegree, npiNumber, plan_name, subscriptionId,referral
    Can raise SMTPException
    """
    from_email = settings.EMAIL_FROM
    now = timezone.now()
    subject = makeSubject('New User Accounts Report - {0:%b %d %Y}'.format(now.astimezone(LOCAL_TZ)))
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

def sendFirstSubsInvoiceEmail(user, user_subs, payment_method, subs_trans=None):
    """Send invoice email to user for first subscription (if payment succeeds, user will receive a separate receipt email).
    Args:
        user: User instance
        user_subs: UserSubscription instance
        payment_method:dict from Customer vault (getPaymentMethods)
        subs_trans: SubscriptionTransaction instance or None (if user is in BT Trial period)
    Can raise SMTPException
    """
    from_email = settings.SUPPORT_EMAIL
    plan = user_subs.plan
    plan_name = 'Orbit ' + plan.display_name
    subject = makeSubject('Your invoice for subscription to {0}'.format(plan_name))
    card = Customer.objects.formatCard(payment_method)
    if subs_trans:
        billingAmount = subs_trans.amount
        nextBillingDate = user_subs.billingEndDate + timedelta(days=1)
    else:
        # user is in BT Trial period; calculate charge amount
        billingAmount = UserSubscription.objects.calcInitialChargeAmountForUserInTrial(user_subs)
        nextBillingDate = None
    ctx = {
        'profile': user.profile,
        'subscription': user_subs,
        'card': card,
        'plan': plan,
        'nextBillingDate': nextBillingDate,
        'billingAmount': billingAmount,
    }
    setCommonContext(ctx)
    orig_message = get_template('email/btsubs_invoice.html').render(ctx)
    # setup premailer
    plog = StringIO()
    phandler = logging.StreamHandler(plog)
    p = premailer.Premailer(orig_message,
            cssutils_logging_handler=phandler,
            cssutils_logging_level=logging.INFO)
    # transformed message
    message = p.transform()
    msg = EmailMessage(subject,
            message,
            from_email=from_email,
            to=[user.email],
            bcc=['faria@orbitcme.com',]
        )
    msg.content_subtype = 'html'
    msg.send()

def sendUpgradePlanInvoiceEmail(user, user_subs, payment_method, subs_trans):
    """Send invoice email to user for UpgradePlan action completed.
    Note: uses same email template as sendFirstSubsInvoiceEmail: btsubs_invoice.html
    Args:
        user: User instance
        user_subs: UserSubscription instance
        payment_method:dict from Customer vault (getPaymentMethods)
        subs_trans: SubscriptionTransaction instance
    Can raise SMTPException
    """
    from_email = settings.SUPPORT_EMAIL
    plan = user_subs.plan
    plan_name = 'Orbit ' + plan.display_name
    subject = makeSubject('Your invoice for subscription to {0}'.format(plan_name))
    card = Customer.objects.formatCard(payment_method)
    billingAmount = subs_trans.amount
    nextBillingDate = user_subs.billingEndDate + timedelta(days=1)
    ctx = {
        'profile': user.profile,
        'subscription': user_subs,
        'card': card,
        'plan': plan,
        'nextBillingDate': nextBillingDate,
        'billingAmount': billingAmount,
    }
    setCommonContext(ctx)
    orig_message = get_template('email/btsubs_invoice.html').render(ctx)
    # setup premailer
    plog = StringIO()
    phandler = logging.StreamHandler(plog)
    p = premailer.Premailer(orig_message,
            cssutils_logging_handler=phandler,
            cssutils_logging_level=logging.INFO)
    # transformed message
    message = p.transform()
    msg = EmailMessage(subject,
            message,
            from_email=from_email,
            to=[user.email],
            bcc=['faria@orbitcme.com',]
        )
    msg.content_subtype = 'html'
    msg.send()


def sendReceiptEmail(user, user_subs, subs_trans):
    """Send EmailMessage receipt to user using receipt template
    Can raise SMTPException
    """
    from_email = settings.SUPPORT_EMAIL
    plan_name = 'Orbit ' + user_subs.plan.display_name
    subject = makeSubject('Your receipt for subscription to {0}'.format(plan_name))
    ctx = {
        'profile': user.profile,
        'subscription': user_subs,
        'transaction': subs_trans,
        'plan_name': plan_name,
        'plan_monthly_price': user_subs.plan.monthlyPrice(),
    }
    setCommonContext(ctx)
    message = get_template('email/receipt.html').render(ctx)
    msg = EmailMessage(subject, message, to=[user.email], from_email=from_email)
    msg.content_subtype = 'html'
    msg.send()

def sendPaymentFailureEmail(user, subs_trans):
    """Send EmailMessage receipt to user using payment_failed template
    Can raise SMTPException
    """
    from_email = settings.SUPPORT_EMAIL
    subject = makeSubject('Your Orbit Invoice Payment Failed [#{0.transactionId}]'.format(subs_trans))
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
    }
    setCommonContext(ctx)
    message = get_template('email/payment_failed.html').render(ctx)
    msg = EmailMessage(subject, message, to=[user.email], from_email=from_email, bcc=[from_email,])
    msg.content_subtype = 'html'
    msg.send()

def sendBoostPurchaseEmail(user, boost_purchase):
    """Send email confirming purchase of CmeBoost by user
    Args:
        user: User instance
        boost_purchase: CmeBoostPurchase instance
    Can raise SMTPException
    """
    from_email = settings.SUPPORT_EMAIL
    subject = makeSubject('Your Orbit Boost purchase')
    ctx = {
        'profile': user.profile,
        'boost_purchase': boost_purchase,
    }
    setCommonContext(ctx)
    orig_message = get_template('email/boost_invoice.html').render(ctx)
    # setup premailer
    plog = StringIO()
    phandler = logging.StreamHandler(plog)
    p = premailer.Premailer(orig_message,
            cssutils_logging_handler=phandler,
            cssutils_logging_level=logging.INFO)
    # transformed message
    message = p.transform()
    msg = EmailMessage(subject,
            message,
            from_email=from_email,
            to=[user.email],
            bcc=['faria@orbitcme.com',]
        )
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
    subject = makeSubject("{0}, here's your Orbit Associate Program statement for {1}".format(addressee, start_monyear))
    encoded_subject = subject
    #subject_with_icon = "{0} {1}".format(ROCKET_ICON, subject)
    #encoded_subject = subject_with_icon.encode('utf-8') # do we need this in py3?
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
    subject = makeSubject("{0}, here's your Orbit Associate Program statement for {1}".format(addressee, start_monyear))
    subject_with_icon = "{0} {1}".format(ROCKET_ICON, subject)
    encoded_subject = subject_with_icon.encode('utf-8') # TODO: may not need this in py3
    #print(encoded_subject)
    # get affiliateId(s) for this Affiliate
    affIds = AffiliateDetail.objects.filter(affiliate=affl).values_list('affiliateId', flat=True).order_by('affiliateId')
    data_by_affid = {'Other': dict(num_convertees=0, total=0)} # affiliateId => {num_convertees:int, total:Decimal}
    for affId in affIds:
        data_by_affid[affId] = dict(num_convertees=0, total=0)
    # group afp_data by affiliateId(s)
    for d in afp_data:
        p = d['convertee'].profile
        affId = p.affiliateId
        if not affId or affId not in data_by_affid:
            # if convertee's profile has stale (or blank) affiliateId, then fallback to Other
            print('Invalid profile.affiliateId for convertee: {0}'.format(p))
            affId = 'Other'
        dd = data_by_affid.get[affId]
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
    now = timezone.now()
    subject = makeSubject('Associate Payout Report - {0:%b %d %Y}'.format(now.astimezone(LOCAL_TZ)))
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
    user = user_subs.user
    email_to = user.email
    subject = makeSubject('Heads up! Your Orbit payment method has expired')
    nextBillingDate = user_subs.billingEndDate + timedelta(days=1)
    ctx = {
        'profile': user.profile,
        'nextBillingDate': nextBillingDate,
        'card_type': payment_method['type'],
        'card_last4': payment_method['number'][-4:],
        'expiry': payment_method['expiry'],
        'support_email': settings.SUPPORT_EMAIL,
        'server_hostname': settings.SERVER_HOSTNAME
    }
    orig_message = get_template('email/card_expired_alert.html').render(ctx)
    # setup premailer
    plog = StringIO()
    phandler = logging.StreamHandler(plog)
    p = premailer.Premailer(orig_message,
            cssutils_logging_handler=phandler,
            cssutils_logging_level=logging.INFO)
    # transformed message
    message = p.transform()
    msg = EmailMessage(subject,
            message,
            from_email=from_email,
            to=[email_to],
            bcc=[REPLY_TO,],
            reply_to=[REPLY_TO,]
        )
    msg.content_subtype = 'html'
    msg.send()


def sendRenewalReminderEmail(user_subs, payment_method, extra_data):
    """Send reminder email about subscription renewal.
    If payment_method has expired, then inform user.
    Args:
        user_subs: UserSubscription instance
        payment_method:dict from Customer vault (getPaymentMethods)
        extra_data:dict {totalCredits:Decimal}
    """
    from_email = settings.EMAIL_FROM
    user = user_subs.user
    email_to = user.email
    subject = makeSubject('Your Orbit subscription renewal')
    nextBillingDate = user_subs.billingEndDate + timedelta(days=1)
    card = Customer.objects.formatCard(payment_method)
    card['needs_update'] = card['expiration_date'] <= nextBillingDate
    ctx = {
        'profile': user.profile,
        'card': card,
        'plan': user_subs.plan,
        'nextBillingDate': nextBillingDate,
        'nextBillingAmount': user_subs.nextBillingAmount,
        'totalCredits': extra_data['totalCredits']
    }
    setCommonContext(ctx)
    orig_message = get_template('email/renewal_reminder.html').render(ctx)
    # setup premailer
    plog = StringIO()
    phandler = logging.StreamHandler(plog)
    p = premailer.Premailer(orig_message,
            cssutils_logging_handler=phandler,
            cssutils_logging_level=logging.INFO)
    # transformed message
    message = p.transform()
    msg = EmailMessage(subject,
            message,
            from_email=from_email,
            to=[user.email],
            reply_to=[REPLY_TO,]
        )
    msg.content_subtype = 'html'
    msg.send()

def sendCancelReminderEmail(user_subs, payment_method, extra_data):
    """Send reminder email to user that their subscription is set to expire at billingEndDate and will not renew.
    This is called when user_subs status is ACTIVE_CANCELED.
    Args:
        user_subs: UserSubscription instance
        payment_method:dict from Customer vault (getPaymentMethods)
        extra_data:dict {totalCredits:Decimal}
    """
    from_email = settings.EMAIL_FROM
    user = user_subs.user
    email_to = user.email
    subject = makeSubject('Your Orbit subscription cancellation')
    ctx = {
        'profile': user.profile,
        'subscription': user_subs,
        'plan': user_subs.plan,
        'totalCredits': extra_data['totalCredits']
    }
    setCommonContext(ctx)
    orig_message = get_template('email/cancel_reminder.html').render(ctx)
    # setup premailer
    plog = StringIO()
    phandler = logging.StreamHandler(plog)
    p = premailer.Premailer(orig_message,
            cssutils_logging_handler=phandler,
            cssutils_logging_level=logging.INFO)
    # transformed message
    message = p.transform()
    msg = EmailMessage(subject,
            message,
            from_email=from_email,
            to=[user.email],
            reply_to=[REPLY_TO,]
        )
    msg.content_subtype = 'html'
    msg.send()

def sendWelcomeEmail(orgmember, send_message=True):
    """Send EmailMessage to user using the welcome_auth0 template.
    Note: If the Auth0 welcome email template is modified, it should be copied into
    the welcome_auth0.html template, and replace any hardcoded links to the website
    with server_hostname.
    Args:
        orgmember: OrgMember instance
        send_message: bool defaults to True. If False, msg will be returned instead
    Returns:
        If send_message is True: int (0 = failed. 1 = delivered)
        If send_message is False: EmailMessage object
    Can raise SMTPException

    """
    from_email = settings.SUPPORT_EMAIL
    subject = makeSubject('Orbit - start earning credit with your new account')
    user = orgmember.user
    ctx = {
        'org': orgmember.organization,
    }
    setCommonContext(ctx)
    message = get_template('email/welcome_auth0.html').render(ctx)
    msg = EmailMessage(subject, message, to=[user.email], from_email=from_email)
    msg.content_subtype = 'html'
    if send_message:
        return msg.send() # 0 or 1
    else:
        return msg


def sendPasswordTicketEmail(orgmember, ticket_url, send_message=True):
    """Send EmailMessage to user using set_password_enterprise template
    Args:
        orgmember: OrgMember instance
        ticket_url: URL for change-password-ticket
        send_message: bool defaults to True. If False, msg will be returned instead
    Returns:
        If send_message is True: int (0 = failed. 1 = delivered)
        If send_message is False: EmailMessage object
    Can raise SMTPException

    """
    from_email = settings.SUPPORT_EMAIL
    subject = makeSubject('Welcome to Orbit! Please set your password')
    user = orgmember.user
    ctx = {
        'org': orgmember.organization,
        'ticket_url': ticket_url,
    }
    setCommonContext(ctx)
    message = get_template('email/set_password_enterprise.html').render(ctx)
    msg = EmailMessage(subject, message, to=[user.email], from_email=from_email)
    msg.content_subtype = 'html'
    if send_message:
        return msg.send() # 0 or 1
    else:
        return msg

def sendJoinTeamEmail(user, org, send_message=True):
    """Send JoinTeam invitation email to user using join_team_invite template
    Args:
        user: User instance
        org: Organization instance
        send_message: bool defaults to True. If False, msg will be returned instead
    Returns:
        If send_message is True: int (0 = failed. 1 = delivered)
        If send_message is False: EmailMessage object
    Can raise SMTPException
    """
    from_email = settings.SUPPORT_EMAIL
    subject = makeSubject('Invitation to join Orbit Enterprise')
    ctx = {
        'user': user,
        'org': org,
        'join_url': settings.UI_LINK_JOINTEAM
    }
    setCommonContext(ctx)
    message = get_template('email/join_team_invite.html').render(ctx)
    msg = EmailMessage(
            subject,
            message,
            to=[user.email],
            from_email=from_email,
            bcc=[from_email,]
            )
    msg.content_subtype = 'html'
    if send_message:
        return msg.send() # 0 or 1
    else:
        return msg

def makeCsvForAttachment(fieldnames, data):
    """"Return object to be used as attachment for EmailMessage"""
    output = StringIO()
    writer = csv.DictWriter(output, delimiter=',', fieldnames=fieldnames)
    writer.writeheader()
    for row in data:
        writer.writerow(row)
    cf = output.getvalue() # to be used as attachment for EmailMessage
    return cf

def sendEmailWithAttachment(subject, message, attachment, attachmentFileName, from_email, to_emails, cc_emails=None, bcc_emails=None):
    if not cc_emails:
        cc_emails  = []
    if not bcc_emails:
        bcc_emails = []
    msg = EmailMessage(
            subject,
            message,
            to=to_emails,
            cc=cc_emails,
            bcc=bcc_emails,
            from_email=from_email)
    msg.content_subtype = 'html'
    msg.attach(attachmentFileName, attachment, 'application/octet-stream')
    msg.send()
