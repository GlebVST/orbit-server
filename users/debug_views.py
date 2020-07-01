import logging
import coreapi
import premailer
from io import StringIO
import simplejson as json
from smtplib import SMTPException
from django.contrib.auth.models import User
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import get_template
from django.utils import timezone
from rest_framework.filters import BaseFilterBackend
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope, TokenHasScope
# app
from .auth0_tools import Auth0Api
from .emailutils import sendCancelReminderEmail, sendRenewalReminderEmail, sendCardExpiredAlertEmail
from .models import *
from .permissions import *
from .serializers import *
from .enterprise_serializers import *
from .dashboard_views import CertificateMixin
from .pdf_tools import SAMPLE_CERTIFICATE_NAME, MDCertificate, NurseCertificate
from .emailutils import setCommonContext, sendJoinTeamEmail, sendWelcomeEmail
from .license_tools import LicenseUpdater

class ValidateLicenseFile(generics.UpdateAPIView):
    """Validate an existing uploaded license file
    """
    serializer_class = LicenseFileTypeUpdateSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]
    def get_queryset(self):
        org = self.request.user.profile.organization
        return OrgFile.objects.filter(organization=org)

    def perform_update(self, serializer, format=None):
        instance = serializer.save(licenseUpdater=self.licenseUpdater)
        return instance

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        form_data = request.data.copy()
        orgfile = self.get_object()
        self.licenseUpdater = LicenseUpdater(orgfile.organization, orgfile.user, dry_run=True)
        in_serializer = self.get_serializer(orgfile, data=form_data, partial=partial)
        in_serializer.is_valid(raise_exception=True)
        instance = self.perform_update(in_serializer)
        print('file_type: {0.file_type}'.format(instance))
        parseErrors = []
        res = dict(num_new=0, num_upd=0, num_error=0, num_no_action=0)
        if instance.isValidFileTypeForUpdate():
            parseErrors = self.licenseUpdater.extractData()
            if self.licenseUpdater.data and not parseErrors:
                self.licenseUpdater.validateUsers()
                res = self.licenseUpdater.preprocessData() # dict(num_new, num_upd, num_no_action, num_error)
                instance.validated = True # num_error can be non-zero (these rows will be skipped if file is processed)
            else:
                instance.validated = False
            instance.save(update_fields=('validated',))
        context = {
            'file_type': instance.file_type,
            'file_providers': {
                'active': len(self.licenseUpdater.profileDict),
                'unrecognized': len(self.licenseUpdater.userValidationDict['unrecognized']),
                'inactive': len(self.licenseUpdater.userValidationDict['inactive']),
                'nonmember': len(self.licenseUpdater.userValidationDict['nonmember']),
            },
            'file_licenses': {
                'num_existing': res['num_no_action'],
                'num_new': res['num_new'],
                'num_update': res['num_upd'],
                'num_error': res['num_error'],
                'errors': self.licenseUpdater.preprocessErrors,
                'parseErrors': parseErrors
            }
        }
        return Response(context)

class MakeOrbitCmeOffer(APIView):
    """
    Create a test OrbitCmeOffer for the authenticated user.
    Pick a random AllowedUrl for the url for the offer.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        user = request.user
        now = timezone.now()
        esiteids = EligibleSite.objects.getSiteIdsForProfile(user.profile)
        # exclude urls for which user already has un-redeemed un-expired offers waiting to be redeemed
        exclude_urls = OrbitCmeOffer.objects.filter(
            user=user,
            redeemed=False,
            eligible_site__in=esiteids,
            expireDate__gte=now
        ).values_list('url', flat=True).distinct()
        #print('Num exclude_urls: {0}'.format(len(exclude_urls)))
        aurl = AllowedUrl.objects.filter(eligible_site__in=esiteids).exclude(pk__in=exclude_urls).order_by('?')[0]
        offer = OrbitCmeOffer.objects.makeDebugOffer(aurl, user)
        if offer:
            context = {'success': True, 'id': offer.pk}
            return Response(context, status=status.HTTP_201_CREATED)
        else:
            context = {'success': False, 'message': 'No offer created'}
            return Response(context, status=status.HTTP_200_OK)



class EmailSubscriptionReceipt(APIView):
    """
    Find the latest subscription transaction of the user
    and email a receipt for it, and return success:True and the transactionId.
    If no transaction exists: return success:False
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        user = request.user
        #print('User: {0.pk} {0.email}'.format(user))
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        if not user_subs:
            context = {'success': False, 'message': 'User does not have a subscription.'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # does user_subs have associated payment transaction
        qset = user_subs.transactions.all().order_by('-created')
        if not qset.exists():
            context = {
                'success': False,
                'message': 'The UserSubscription {0.pk} does not have a payment transaction in the database yet.'.format(user_subs)
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # else prepare context for email
        subs_trans = qset[0]
        plan_name = 'Orbit ' + user_subs.plan.name
        subject = 'Your receipt for annual subscription to {0}'.format(plan_name)
        from_email = settings.SUPPORT_EMAIL
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
        try:
            msg.send()
        except SMTPException as e:
            logException(logger, request, 'EmailSubscriptionReceipt send email failed.')
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            context = {
                'success': True,
                'message': 'A receipt was emailed to {0.email}'.format(user),
                'transactionId': subs_trans.transactionId
            }
            return Response(context, status=status.HTTP_200_OK)

class EmailSubscriptionPaymentFailure(APIView):
    """
    Find the latest subscription transaction of the user
    and send a payment failure email for it, and return success:True and the transactionId.
    If no transaction exists: return success:False
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        user = request.user
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        if not user_subs:
            context = {'success': False, 'message': 'User does not have a subscription.'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # does user_subs have associated payment transaction
        qset = user_subs.transactions.all().order_by('-created')
        if not qset.exists():
            context = {
                'success': False,
                'message': 'The UserSubscription {0.pk} does not have a payment transaction in the database yet.'.format(user_subs)
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # else prepare context for email
        subs_trans = qset[0]
        subject = 'Your Orbit Invoice Payment Failed [#{0.transactionId}]'.format(subs_trans)
        from_email = settings.SUPPORT_EMAIL
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
        msg = EmailMessage(subject, message, to=[user.email], from_email=from_email)
        msg.content_subtype = 'html'
        try:
            msg.send()
        except SMTPException as e:
            logException(logger, request, 'EmailSubscriptionPaymentFailure send email failed.')
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            context = {
                'success': True,
                'message': 'A payment failure notice was emailed to {0.email}'.format(user),
                'transactionId': subs_trans.transactionId
            }
            return Response(context, status=status.HTTP_200_OK)


class InvitationDiscountList(generics.ListAPIView):
    """List of InvitationDiscounts for the current authenticated user as inviter"""
    serializer_class = InvitationDiscountReadSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        user = self.request.user
        return InvitationDiscount.objects.filter(inviter=user).select_related().order_by('-created')

class PreEmail(APIView):
    """send test email using premailer
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        user = request.user
        etype = EntryType.objects.get(name=ENTRYTYPE_BRCME)
        now = timezone.now()
        cutoff = now - timedelta(days=90)
        entries = Entry.objects.select_related('user','entryType').filter(
                valid=True,
                created__gte=cutoff).order_by('-created')
        from_email = settings.SUPPORT_EMAIL
        subject = 'Orbit user activity'
        ctx = {
            'profile': user.profile,
            'entries': entries,
            'num_entries': entries.count(),
            'reportDate': now,
            'cutoff': cutoff
        }
        setCommonContext(ctx)
        # setup premailer
        plog = StringIO()
        phandler = logging.StreamHandler(plog)
        orig_message = get_template('email/test_inline.html').render(ctx)
        p = premailer.Premailer(orig_message,
                cssutils_logging_handler=phandler,
                cssutils_logging_level=logging.INFO)
        # transformed message
        message = p.transform()
        print(plog.getvalue())
        msg = EmailMessage(subject, message, to=[user.email], from_email=from_email)
        msg.content_subtype = 'html'
        try:
            msg.send()
        except SMTPException as e:
            logException(logger, request, 'SendTestPreEmail failed.')
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            context = {
                'success': True,
                'message': 'A message was emailed to {0.email}'.format(user),
            }
            return Response(context, status=status.HTTP_200_OK)



class EmailCardExpired(APIView):
    """Call emailutils.SendCardExpiredAlertEmail for request.user
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        user = request.user
        paymentMethods = Customer.objects.getPaymentMethods(user.customer)
        pm = paymentMethods[0]
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        try:
            sendCardExpiredAlertEmail(user_subs, pm)
        except SMTPException as e:
            logException(logger, request, 'EmailCardExpired failed.')
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            context = {
                'success': True,
                'message': 'A message was emailed to {0.email}'.format(user),
                'paymentMethod': pm
            }
            return Response(context, status=status.HTTP_200_OK)

class EmailSubscriptionRenewalReminder(APIView):
    """Call emailutils.SendRenewalReminderEmail for request.user
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        user = request.user
        paymentMethods = Customer.objects.getPaymentMethods(user.customer)
        pm = paymentMethods[0]
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        extra_data = {
            'totalCredits': int(BrowserCme.objects.totalCredits())
        }
        try:
            sendRenewalReminderEmail(user_subs, pm, extra_data)
        except SMTPException as e:
            logException(logger, request, 'EmailSubscriptionRenewalReminder failed.')
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            context = {
                'success': True,
                'message': 'A message was emailed to {0.email}'.format(user),
                'paymentMethod': pm
            }
            return Response(context, status=status.HTTP_200_OK)


class EmailSubscriptionCancelReminder(APIView):
    """Call emailutils.SendCancelReminderEmail for request.user
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        user = request.user
        paymentMethods = Customer.objects.getPaymentMethods(user.customer)
        pm = paymentMethods[0]
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        try:
            sendCancelReminderEmail(user_subs, pm)
        except SMTPException as e:
            logException(logger, request, 'EmailSubscriptionCancelReminder failed.')
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            context = {
                'success': True,
                'message': 'A message was emailed to {0.email}'.format(user),
            }
            return Response(context, status=status.HTTP_200_OK)


class DocumentList(generics.ListAPIView):
    serializer_class = DocumentReadSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)

class OrgMemberFilterBackend(BaseFilterBackend):
    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name='q',
                location='query',
                required=False,
                type='string',
                description='Search by firstName, lastName or email'
                ),
            coreapi.Field(
                name='compliance',
                location='query',
                required=False,
                type='string',
                description='Filter by compliance: [0-4]'
                ),
            coreapi.Field(
                name='verified',
                location='query',
                required=False,
                type='string',
                description='Filter by verified: 0 or 1'
                ),
            coreapi.Field(
                name='o',
                location='query',
                required=False,
                type='string',
                description='Order By one of: lastname/created/compliance/verified'
                ),
            coreapi.Field(
                name='otype',
                location='query',
                required=False,
                type='string',
                description='a for ASC. d for DESC'
                ),
            ]

    def filter_queryset(self, request, queryset, view):
        """This requires the model Manager to have a search_filter manager method"""
        org = request.user.profile.organization
        search_term = request.query_params.get('q', '').strip()
        compliance = None
        verified = None
        q_compliance = request.query_params.get('compliance', '').strip()
        try:
            compliance = int(q_compliance)
        except ValueError:
            compliance = None
        q_verified = request.query_params.get('verified', '').strip()
        try:
            verified = bool(int(q_verified))
        except ValueError:
            verified = None
        # basic filter kwargs
        filter_kwargs = {'organization': org, 'removeDate__isnull': True, 'pending': False}
        if compliance is not None:
            filter_kwargs['compliance'] = compliance
        if verified is not None:
            filter_kwargs['user__profile__verified'] = verified
        o = request.query_params.get('o', 'lastname').strip()
        otype = request.query_params.get('otype', 'a').strip() # sort primary field by ASC/DESC
        # set orderByFields from o
        if o == 'lastname':
            orderByFields = ['user__profile__lastName', 'user__profile__firstName', 'created']
        elif o == 'created':
            orderByFields = ['created', 'fullname']
        elif o == 'compliance':
            orderByFields = ['compliance', 'fullname']
        elif o == 'verified':
            orderByFields = ['user__profile__verified', 'fullname']
        if otype == 'd':
            orderByFields[0] = '-' + orderByFields[0]
        if search_term:
            return OrgMember.objects.search_filter(search_term, filter_kwargs, orderByFields)
        return queryset.filter(**filter_kwargs).order_by(*orderByFields)


class OrgMemberList(generics.ListAPIView):
    queryset = OrgMember.objects.filter(removeDate__isnull=True)
    serializer_class = OrgMemberReadSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]
    filter_backends = (OrgMemberFilterBackend,)


class CreateOrgMember(generics.CreateAPIView):
    serializer_class = OrgMemberFormSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]

    def perform_create(self, serializer, format=None):
        """If email is given, check that it does not trample on an existing user account
        Save auth0 token info to request.session
        """
        org = self.request.user.profile.organization
        # check email
        email = self.request.data.get('email', '')
        if email:
            qset = User.objects.filter(email__iexact=email)
            if qset.exists():
                error_msg = 'This email already belongs to another user account.'
                raise serializers.ValidationError({'email': error_msg}, code='invalid')
        apiConn = Auth0Api.getConnection(self.request)
        with transaction.atomic():
            instance = serializer.save(apiConn=apiConn, organization=org)
        return instance

    def create(self, request, *args, **kwargs):
        form_data = request.data.copy()
        serializer = self.get_serializer(data=form_data)
        serializer.is_valid(raise_exception=True)
        instance = self.perform_create(serializer)
        out_serializer = OrgMemberReadSerializer(instance)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)

class OrgMemberDetail(generics.RetrieveAPIView):
    serializer_class = OrgMemberReadSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]


    def get_queryset(self):
        """This ensures that an OrgMember instance can only be retrieved by
        an admin belonging to the same org as the member
        """
        org = self.request.user.profile.organization
        return OrgMember.objects.filter(organization=org)


class UpdateOrgMember(generics.UpdateAPIView):
    serializer_class = OrgMemberFormSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]


    def get_queryset(self):
        """This ensures that an OrgMember instance can only be updated by
        an admin belonging to the same org as the member
        """
        org = self.request.user.profile.organization
        return OrgMember.objects.filter(organization=org)

    def perform_update(self, serializer, format=None):
        """If email is given, check that it does not trample on an existing user account"""
        # check email
        m = self.get_object()
        email = self.request.data.get('email', '')
        if email and m.user.email != email:
            qset = User.objects.filter(email__iexact=email).exclude(pk=m.user.pk)
            if qset.exists():
                error_msg = 'The email {0} belongs to another user account.'.format(email)
                raise serializers.ValidationError({'email': error_msg}, code='invalid')
        apiConn = Auth0Api.getConnection(self.request)
        with transaction.atomic():
            instance = serializer.save(apiConn=apiConn)
        return instance

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        form_data = request.data.copy()
        in_serializer = self.get_serializer(instance, data=form_data, partial=partial)
        in_serializer.is_valid(raise_exception=True)
        self.perform_update(in_serializer)
        m = OrgMember.objects.get(pk=instance.pk)
        out_serializer = OrgMemberReadSerializer(m)
        return Response(out_serializer.data)


class EmailSetPassword(APIView):
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

    def post(self, request, *args, **kwargs):
        apiConn = Auth0Api.getConnection(self.request)
        memberid = self.kwargs.get('pk')
        if memberid:
            qset = OrgMember.objects.filter(pk=memberid)
            if not qset.exists():
                return Response({'success': False}, status=status.HTTP_404_NOT_FOUND)
            orgmember = qset[0]
            profile = orgmember.user.profile
            if orgmember.pending:
                # member get into a pending state only when existing Orbit user get invited to organisation
                # for such users we send a join-team email again
                try:
                    sendJoinTeamEmail(orgmember.user, orgmember.organization, send_message=True)
                    sleep(0.2)
                except SMTPException as e:
                    logger.warn('sendJoinTeamEmail failed to pending OrgMember {0.fullname}.'.format(orgmember))
                else:
                    member.inviteDate = timezone.now()
                    member.setPasswordEmailSent = True # need to set this flag otherwise member appears in Launchpad in UI
                    member.save(update_fields=('setPasswordEmailSent','inviteDate'))
            elif not orgmember.user.profile.verified:
                # unverified users with with non-pending state are those invited but not yet verified their email
                # so for such users we send a set-password email
                OrgMember.objects.sendPasswordTicket(orgmember.user.profile.socialId, orgmember, apiConn)
                if not member.is_admin:
                    sendWelcomeEmail(member)
            context = {'success': True}
            return Response(context, status=status.HTTP_200_OK)
        return Response({'success': False}, status=status.HTTP_404_NOT_FOUND)

class CreateAuditReport(CertificateMixin, APIView):
    """
    This view expects a start date and end date in UNIX epoch format
    (number of seconds since 1970/1/1) as URL parameters.
    It generates an Audit Report for the date range, and uploads to S3.
    For each tag with non-zero brcme credits, it also generates a Specialty Certificate that is associated with the report.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

    def post(self, request, userid, start, end):
        try:
            startdt = timezone.make_aware(datetime.utcfromtimestamp(int(start)), pytz.utc)
            enddt = timezone.make_aware(datetime.utcfromtimestamp(int(end)), pytz.utc)
            if startdt >= enddt:
                context = {
                    'error': 'Start date must be prior to End Date.'
                }
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
            brcme_startdt = startdt
        except ValueError:
            context = {
                'error': 'Invalid date parameters'
            }
            message = context['error'] + ': ' + start + ' - ' + end
            logWarning(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.get(pk=userid)
        profile = user.profile
        # get total self-reported cme credits earned by user in date range
        srCmeTotal = Entry.objects.sumSRCme(user, startdt, enddt)
        # get total Browser-cme credits earned by user in date range
        browserCmeTotal = Entry.objects.sumBrowserCme(user, startdt, enddt)
        cmeTotal = srCmeTotal + browserCmeTotal
        if cmeTotal == 0:
            context = {
                'error': 'No CME credits earned in this date range.'
            }
            logInfo(logger, request, context['error'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # check which cert class to use (MD or Nurse)
        state_license = None
        certClass = MDCertificate
        if profile.isNurse():
            state_license = user.statelicenses.all()[0]
            certClass = NurseCertificate
        # list of dicts: one for each tag having non-zero credits in date range
        auditData = Entry.objects.prepareDataForAuditReport(user, startdt, enddt)
        certificatesByTag = {} # tag.pk => Certificate instance
        satag = CmeTag.objects.get(name=CmeTag.SACME)
        saCmeTotal = 0  # credit sum for SA-CME tag
        otherCmeTotal = 0 # credit sum for all other tags
        for d in auditData:
            tag = CmeTag.objects.get(pk=d['id'])
            brcme_sum = d['brcme_sum']
            srcme_sum = d['srcme_sum']
            d['brcmeCertReferenceId'] = None
            if brcme_sum:
                # tag has non-zero brcme credits, so make cert
                print('Making certificate for {0.name}'.format(tag))
                certificate = self.makeCertificate(
                    certClass,
                    profile,
                    startdt,
                    enddt,
                    brcme_sum,
                    tag, # this makes it a Specialty certificate
                    state_license=state_license
                )
                certificatesByTag[tag.pk] = certificate
                # set referenceId for the brcme entries
                # Check w. Gleb if we can set single key brcmeCertReferenceId for all brcme entries under this tag to avoid for-loop
                d['brcmeCertReferenceId'] = certificate.referenceId # preferred!
                for ed in d['entries']:
                    if ed['entryType'] == ENTRYTYPE_BRCME:
                        ed['referenceId'] = certificate.referenceId
            tag_sum = brcme_sum + srcme_sum
            if tag.pk == satag.pk:
                saCmeTotal += tag_sum
            else:
                otherCmeTotal += tag_sum

        # make AuditReport instance and associate with the above certs
        report = self.makeReport(profile, startdt, enddt, auditData, certificatesByTag, saCmeTotal, otherCmeTotal)
        if report is None:
            context = {
                'error': 'There was an error in creating this Audit Report.'
            }
            logWarning(logger, request, context['error'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            context = {
                'success': True,
                'referenceId': report.referenceId
            }
            return Response(context, status=status.HTTP_201_CREATED)

    def makeReport(self, profile, startdt, enddt, auditData, certificatesByTag, saCmeTotal, otherCmeTotal):
        """Create AuditReport model instance, associate it with the certificates and return model instance
        """
        user = profile.user
        reportName = profile.getFullNameAndDegree()
        profile_specs = [ps.name for ps in profile.specialties.all()]
        # report_data: JSON used by the UI to generate the HTML report
        report_data = {
            'saCredits': saCmeTotal,
            'otherCredits': otherCmeTotal,
            'dataByTag': auditData,
            'profileSpecialties': profile_specs
        }
        # create AuditReport instance
        report = AuditReport(
            user=user,
            name = reportName,
            startDate = startdt,
            endDate = enddt,
            saCredits = saCmeTotal,
            otherCredits = otherCmeTotal,
            data=json.dumps(report_data)
        )
        report.save()
        hashgen = Hashids(salt=settings.REPORT_HASHIDS_SALT, min_length=10)
        report.referenceId = hashgen.encode(report.pk)
        report.save(update_fields=('referenceId',))
        # set report.certificates ManyToManyField
        report.certificates.set([certificatesByTag[tagid] for tagid in certificatesByTag])
        return report

class RecAllowedUrlListForUser(APIView):
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get(self, request, userid, *args, **kwargs):
        from .feed_serializers import RecAllowedUrlReadSerializer
        user = User.objects.get(pk=userid)
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        plan = user_subs.plan
        results = []
        plantags = Plantag.objects.filter(plan=plan, num_recs__gt=0).order_by('num_recs', 'id')
        for pt in plantags:
            tag = pt.tag
            qset = user.recaurls \
                .select_related('offer', 'url__eligible_site') \
                .filter(cmeTag=tag) \
                .order_by('-url__numOffers', 'id')
            s = RecAllowedUrlReadSerializer(qset, many=True)
            results.append({
                'tag': tag.pk,
                'recs': s.data
            })
        context = {
            'results': results
        }
        return Response(context, status=status.HTTP_200_OK)
