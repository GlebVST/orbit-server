import calendar
from datetime import datetime
from hashids import Hashids
import logging
from operator import itemgetter
import pytz
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from rest_framework import generics, exceptions, permissions, status, serializers
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope, TokenHasScope
# proj
from common.logutils import *
# app
from .models import *
from .serializers import DocumentReadSerializer
from .dashboard_serializers import CertificateReadSerializer, AuditReportReadSerializer
from .permissions import *
from .pdf_tools import SAMPLE_CERTIFICATE_NAME, MDCertificate, NurseCertificate, MDStoryCertificate, NurseStoryCertificate

logger = logging.getLogger('api.dash')

class LogValidationErrorMixin(object):
    def handle_exception(self, exc):
        response = super(LogValidationErrorMixin, self).handle_exception(exc)
        if response is not None and isinstance(exc, exceptions.ValidationError):
            #logWarning(logger, self.request, exc.get_full_details())
            message = "ValidationError: {0}".format(exc.detail)
            #logError(logger, self.request, message)
            logWarning(logger, self.request, message)
        return response


class AccessDocumentOrCert(APIView):
    """Public endpoint to access Document/Certificate.
    This view expects a reference ID to lookup a Document or Certificate
    in the db. The response returns a timed URL to access the file.
    parameters:
        - name: referenceId
          description: unique ID of document/certificate
          required: true
          type: string
          paramType: query
    """
    permission_classes = (permissions.AllowAny,)
    def get(self, request, referenceId):
        try:
            if referenceId.startswith('document'):
                document = Document.objects.get(referenceId=referenceId)
                out_serializer = DocumentReadSerializer(document)
            else:
                certificate = Certificate.objects.get(referenceId=referenceId)
                out_serializer = CertificateReadSerializer(certificate)
        except Certificate.DoesNotExist:
            context = {
                'error': 'Invalid certificate ID or not found'
            }
            message = context['error'] + ': ' + referenceId
            logWarning(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        except Document.DoesNotExist:
            context = {
                'error': 'Invalid document ID or not found'
            }
            message = context['error'] + ': ' + referenceId
            logWarning(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        return Response(out_serializer.data, status=status.HTTP_200_OK)


class CmeAggregateStats(APIView):
    """
    This view expects a start date and end date in UNIX epoch format
    (number of seconds since 1970/1/1) as URL parameters. It calculates
    the total SRCme and BrowserCme for the time period for the current
    user, and also the total by tag.

    parameters:
        - name: start
          description: seconds since epoch
          required: true
          type: string
          paramType: form
        - name: end
          description: seconds since epoch
          required: true
          type: string
          paramType: form
    """
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanViewDashboard)
    def serialize_and_render(self, stats):
        context = {
            'result': stats
        }
        return Response(context, status=status.HTTP_200_OK)

    def get(self, request, start, end):
        try:
            startdt = timezone.make_aware(datetime.utcfromtimestamp(int(start)), pytz.utc)
            enddt = timezone.make_aware(datetime.utcfromtimestamp(int(end)), pytz.utc)
        except ValueError:
            context = {
                'error': 'Invalid date parameters'
            }
            message = context['error'] + ': ' + start + ' - ' + end
            logWarning(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        user_tags = user.profile.getActiveCmetags()
        satag = CmeTag.objects.get(name=CMETAG_SACME)
        stats = {
            ENTRYTYPE_BRCME: {
                'total': Entry.objects.sumBrowserCme(user, startdt, enddt),
                'Untagged': Entry.objects.sumBrowserCme(user, startdt, enddt, untaggedOnly=True),
                satag.name: Entry.objects.sumBrowserCme(user, startdt, enddt, satag)
            },
            ENTRYTYPE_SRCME: {
                'total': Entry.objects.sumSRCme(user, startdt, enddt),
                'Untagged': Entry.objects.sumSRCme(user, startdt, enddt, untaggedOnly=True),
                satag.name: Entry.objects.sumSRCme(user, startdt, enddt, satag)
            },
            # not used/obsolete
            ENTRYTYPE_STORY_CME: {
                'total': 0,
                satag.name: 0
            }
        }
        for pct in user_tags: # ProfileCmetag queryset
            tag = pct.tag
            if tag.srcme_only:
                stats[ENTRYTYPE_SRCME][tag.name] = Entry.objects.sumSRCme(user, startdt, enddt, tag)
                stats[ENTRYTYPE_BRCME][tag.name] = 0
            else:
                stats[ENTRYTYPE_BRCME][tag.name] = Entry.objects.sumBrowserCme(user, startdt, enddt, tag)
                stats[ENTRYTYPE_SRCME][tag.name] = Entry.objects.sumSRCme(user, startdt, enddt, tag)
            stats[ENTRYTYPE_STORY_CME][tag.name] = 0
        return self.serialize_and_render(stats)

#
# PDF
#
class CertificateMixin(object):
    """Mixin to create Browser-Cme certificate PDF file, upload
    to S3 and save model instance.
    Returns: Certificate instance
    """
    def makeCertificate(self, certClass, profile, startdt, enddt, cmeTotal, tag=None, state_license=None):
        """
        certClass: Certificate class to instantiate (MDCertificate/NurseCertificate/MDStoryCertificate/etc)
        profile: Profile instance for user
        startdt: datetime - startDate
        enddt: datetime - endDate
        cmeTotal: float - total credits in date range
        tag: CmeTag/None - if given, this is a specialty Cert
        state_license: StateLicense/None - if given this is a Cert for a specific user statelicense
        """
        user = profile.user
        degrees = profile.degrees.all()
        can_print_cert = hasUserSubscriptionPerm(user, PERM_PRINT_BRCME_CERT)
        if can_print_cert:
            user_subs = UserSubscription.objects.getLatestSubscription(user)
            if user_subs.display_status != UserSubscription.UI_TRIAL:
                certificateName = profile.getFullNameAndDegree()
            else:
                certificateName = SAMPLE_CERTIFICATE_NAME
        else:
            certificateName = SAMPLE_CERTIFICATE_NAME
        certificate = Certificate(
            name = certificateName,
            startDate = startdt,
            endDate = enddt,
            credits = cmeTotal,
            user=user,
            tag=tag,
            state_license=state_license
        )
        certificate.save()
        hashgen = Hashids(salt=settings.HASHIDS_SALT, min_length=10)
        certificate.referenceId = hashgen.encode(certificate.pk)
        if profile.isNurse() and certificate.state_license is not None:
            certGenerator = certClass(certificate)
        else:
            isVerified = any(d.isVerifiedForCme() for d in degrees)
            certGenerator = certClass(certificate, isVerified)
        certGenerator.makeCmeCertOverlay()
        output = certGenerator.makeCmeCertificate() # str
        cf = ContentFile(output) # Create a ContentFile from the output
        # Save file (upload to S3) and re-save model instance
        certificate.document.save("{0}.pdf".format(certificate.referenceId), cf, save=True)
        certGenerator.cleanup()
        return certificate


class CreateCmeCertificatePdf(CertificateMixin, APIView):
    """
    This view expects a start date and end date in UNIX epoch format
    (number of seconds since 1970/1/1) as URL parameters. It calculates
    the total Browser-Cme credits for the time period for the user,
    generates certificate PDF file, and uploads it to S3.

    parameters:
        - name: start
          description: seconds since epoch
          required: true
          type: string
          paramType: form
        - name: end
          description: seconds since epoch
          required: true
          type: string
          paramType: form
    """
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanViewDashboard)
    def post(self, request, start, end):
        try:
            startdt = timezone.make_aware(datetime.utcfromtimestamp(int(start)), pytz.utc)
            enddt = timezone.make_aware(datetime.utcfromtimestamp(int(end)), pytz.utc)
            if startdt >= enddt:
                context = {
                    'error': 'Start date must be prior to End Date.'
                }
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            context = {
                'error': 'Invalid date parameters'
            }
            message = context['error'] + ': ' + start + ' - ' + end
            logWarning(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        profile = user.profile
        # get total cme credits earned by user in date range
        browserCmeTotal = Entry.objects.sumBrowserCme(user, startdt, enddt)
        cmeTotal = browserCmeTotal
        if cmeTotal == 0:
            context = {
                'error': 'No Orbit CME credits earned in this date range.'
            }
            logInfo(logger, request, context['error'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # 2017-11-14: if user is Nurse, get state license
        state_license = None
        certClass = MDCertificate
        if profile.isNurse() and user.statelicenses.exists():
            state_license = user.statelicenses.all()[0]
            certClass = NurseCertificate
        certificate = self.makeCertificate(certClass, profile, startdt, enddt, cmeTotal, state_license=state_license)
        out_serializer = CertificateReadSerializer(certificate)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)


class CreateSpecialtyCmeCertificatePdf(CertificateMixin, APIView):
    """
    This view expects a start date and end date in UNIX epoch format
    (number of seconds since 1970/1/1), and a tag ID as URL parameters. It calculates
    the total Browser-Cme credits for the selected tag and date range for the user,
    generates certificate PDF file, and uploads it to S3.

    parameters:
        - name: start
          description: seconds since epoch
          required: true
          type: string
          paramType: form
        - name: end
          description: seconds since epoch
          required: true
          type: string
          paramType: form
        - name: tag
          description: tag id
          required: true
          type: string
          paramType: form
    """
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanViewDashboard)
    def post(self, request, start, end, tag_id):
        try:
            startdt = timezone.make_aware(datetime.utcfromtimestamp(int(start)), pytz.utc)
            enddt = timezone.make_aware(datetime.utcfromtimestamp(int(end)), pytz.utc)
            if startdt >= enddt:
                context = {
                    'error': 'Start date must be prior to End Date.'
                }
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            context = {
                'error': 'Invalid date parameters'
            }
            message = context['error'] + ': ' + start + ' - ' + end
            logWarning(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        try:
            tag = CmeTag.objects.get(pk=tag_id)
        except CmeTag.DoesNotExist:
            context = {
                'error': 'Invalid tag id'
            }
            logWarning(logger, request, context['error'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        profile = user.profile
        # get cme credits earned by user in date range for selected tag
        browserCmeTotal = Entry.objects.sumBrowserCme(user, startdt, enddt, tag)
        cmeTotal = browserCmeTotal
        if cmeTotal == 0:
            context = {
                'error': 'No Orbit CME credits earned for the selected tag in this date range.',
            }
            logInfo(logger, request, context['error'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # 2017-11-14: if user is Nurse, get state license
        state_license = None
        certClass = MDCertificate
        if profile.isNurse() and user.statelicenses.exists():
            state_license = user.statelicenses.all()[0]
            certClass = NurseCertificate
        certificate = self.makeCertificate(certClass, profile, startdt, enddt, cmeTotal, tag, state_license=state_license)
        out_serializer = CertificateReadSerializer(certificate)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)


class CreateStoryCmeCertificatePdf(CertificateMixin, APIView):
    """
    This view expects a start date and end date in UNIX epoch format
    (number of seconds since 1970/1/1).
    It calculates the total Story-Cme credits for the given date range and request.user.
    It generates certificate PDF file, and uploads it to S3.

    parameters:
        - name: start
          description: seconds since epoch
          required: true
          type: string
          paramType: form
        - name: end
          description: seconds since epoch
          required: true
          type: string
          paramType: form
    """
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanViewDashboard)
    def post(self, request, start, end):
        try:
            startdt = timezone.make_aware(datetime.utcfromtimestamp(int(start)), pytz.utc)
            enddt = timezone.make_aware(datetime.utcfromtimestamp(int(end)), pytz.utc)
            if startdt >= enddt:
                context = {
                    'error': 'Start date must be prior to End Date.'
                }
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            context = {
                'error': 'Invalid date parameters'
            }
            message = context['error'] + ': ' + start + ' - ' + end
            logWarning(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        profile = user.profile
        satag = CmeTag.objects.get(name=CMETAG_SACME)
        # get cme credits earned by user in date range for selected tag
        cmeTotal = Entry.objects.sumStoryCme(user, startdt, enddt)
        if cmeTotal == 0:
            context = {
                'error': 'No Orbit Story CME credits earned in this date range.',
            }
            logInfo(logger, request, context['error'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # if user is Nurse, get state license
        state_license = None
        certClass = MDStoryCertificate
        if profile.isNurse() and user.statelicenses.exists():
            state_license = user.statelicenses.all()[0]
            certClass = NurseStoryCertificate
        certificate = self.makeCertificate(certClass, profile, startdt, enddt, cmeTotal, satag, state_license=state_license)
        out_serializer = CertificateReadSerializer(certificate)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)


class AccessCmeCertificate(APIView):
    """
    This view expects a certificate reference ID to lookup a Certificate
    in the db. The response returns a timed URL to access the file.
    parameters:
        - name: referenceId
          description: unique certificate ID
          required: true
          type: string
          paramType: query
    """
    permission_classes = (permissions.AllowAny,)
    def get(self, request, referenceId):
        try:
            certificate = Certificate.objects.get(referenceId=referenceId)
        except Certificate.DoesNotExist:
            context = {
                'error': 'Invalid certificate ID or not found'
            }
            logWarning(logger, request, context['error'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        out_serializer = CertificateReadSerializer(certificate)
        return Response(out_serializer.data, status=status.HTTP_200_OK)

class AuditReportMixin(CertificateMixin):

    def generateUserReport(self, user, startdt, enddt, request):
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
            logInfo(logger, request, "Failed to generate audit report for user {0}: {1}".format(user.id, context['error']))
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        if profile.shouldReqNPINumber() and not profile.npiNumber:
            context = {
                'error': 'Please update your profile with your NPI Number.'
            }
            logInfo(logger, request, "Failed to generate audit report for user {0}: {1}".format(user.id, context['error']))
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        elif profile.isNurse() and not user.statelicenses.exists():
            context = {
                'error': 'Please update your profile with your State License.'
            }
            logInfo(logger, request, "Failed to generate audit report for user {0}: {1}".format(user.id, context['error']))
            return Response(context, status=status.HTTP_400_BAD_REQUEST)

        # check which cert class to use (MD or Nurse)
        state_license = None
        certClass = MDCertificate
        if profile.isNurse():
            state_license = user.statelicenses.all()[0]
            certClass = NurseCertificate
        # list of dicts: one for each tag having non-zero credits in date range
        auditData = Entry.objects.newPrepareDataForAuditReport(user, startdt, enddt)
        certificatesByTag = {} # tag.pk => Certificate instance
        satag = CmeTag.objects.get(name=CMETAG_SACME)
        saCmeTotal = 0  # credit sum for SA-CME tag
        otherCmeTotal = 0 # credit sum for all other tags
        for d in auditData:
            tag = CmeTag.objects.get(pk=d['id'])
            brcme_sum = d['brcme_sum']
            srcme_sum = d['srcme_sum']
            d['brcmeCertReferenceId'] = None
            if brcme_sum:
                # tag has non-zero brcme credits, so make cert
                logInfo(logger, request, "Making certificate for user {0} and tag {1.name}".format(user.id, tag))
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
            logWarning(logger, request, "Failed to generate audit report for user {0}: {1}".format(user.id, context['error']))
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
        can_print_report = hasUserSubscriptionPerm(user, PERM_PRINT_AUDIT_REPORT)
        if can_print_report:
            user_subs = UserSubscription.objects.getLatestSubscription(user)
            if user_subs.display_status != UserSubscription.UI_TRIAL:
                reportName = profile.getFullNameAndDegree()
            else:
                reportName = SAMPLE_CERTIFICATE_NAME
        else:
            reportName = SAMPLE_CERTIFICATE_NAME

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
            data=JSONRenderer().render(report_data)
        )
        report.save()
        hashgen = Hashids(salt=settings.REPORT_HASHIDS_SALT, min_length=10)
        report.referenceId = hashgen.encode(report.pk)
        report.save(update_fields=('referenceId',))
        # set report.certificates ManyToManyField
        report.certificates.set([certificatesByTag[tagid] for tagid in certificatesByTag])
        return report
#
# Audit Report
#
class CreateAuditReport(AuditReportMixin, APIView):
    """
    This view expects a start date and end date in UNIX epoch format
    (number of seconds since 1970/1/1) as URL parameters.
    It generates an Audit Report for the date range, and uploads to S3.
    If user has earned browserCme credits in the date range, it also
    generates a Certificate that is associated with the report.

    parameters:
        - name: start
          description: seconds since epoch
          required: true
          type: string
          paramType: form
        - name: end
          description: seconds since epoch
          required: true
          type: string
          paramType: form
    """
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanViewDashboard)
    def post(self, request, start, end):
        try:
            startdt = timezone.make_aware(datetime.utcfromtimestamp(int(start)), pytz.utc)
            enddt = timezone.make_aware(datetime.utcfromtimestamp(int(end)), pytz.utc)
            if startdt >= enddt:
                context = {
                    'error': 'Start date must be prior to End Date.'
                }
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            context = {
                'error': 'Invalid date parameters'
            }
            message = context['error'] + ': ' + start + ' - ' + end
            logWarning(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)

        return self.generateUserReport(request.user, startdt, enddt, request)

class AccessAuditReport(APIView):
    """
    This view expects a report reference ID to lookup an AuditReport
    in the db. The response returns a timed URL to access the file.
    parameters:
        - name: referenceId
          description: unique report ID
          required: true
          type: string
          paramType: query
    """
    permission_classes = (permissions.AllowAny,)
    def get(self, request, referenceId):
        try:
            report = AuditReport.objects.get(referenceId=referenceId)
        except AuditReport.DoesNotExist:
            context = {
                'error': 'Invalid report ID or not found'
            }
            logWarning(logger, request, context['error'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        out_serializer = AuditReportReadSerializer(report)
        return Response(out_serializer.data, status=status.HTTP_200_OK)
