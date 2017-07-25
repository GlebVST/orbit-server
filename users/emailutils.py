from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import get_template

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
