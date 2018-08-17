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
        user_tags = user.profile.cmeTags.all()
        satag = CmeTag.objects.get(name=CMETAG_SACME)
        story_total = Entry.objects.sumStoryCme(user, startdt, enddt)
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
            ENTRYTYPE_STORY_CME: {
                'total': story_total,
                satag.name: story_total
            }
        }
        for tag in user_tags:
            stats[ENTRYTYPE_BRCME][tag.name] = Entry.objects.sumBrowserCme(user, startdt, enddt, tag)
            stats[ENTRYTYPE_SRCME][tag.name] = Entry.objects.sumSRCme(user, startdt, enddt, tag)
            stats[ENTRYTYPE_STORY_CME][tag.name] = 0 # for mvp storycme are only tagged with SA-CME
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

#
# Audit Report
#
class CreateAuditReport(CertificateMixin, APIView):
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
            brcme_startdt = startdt
        except ValueError:
            context = {
                'error': 'Invalid date parameters'
            }
            message = context['error'] + ': ' + start + ' - ' + end
            logWarning(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        profile = user.profile
        # get total self-reported cme credits earned by user in date range
        srCmeTotal = Entry.objects.sumSRCme(user, startdt, enddt)
        # get total Browser-cme credits earned by user in date range
        if brcme_startdt:
            browserCmeTotal = Entry.objects.sumBrowserCme(user, brcme_startdt, enddt)
        else:
            browserCmeTotal = 0
        cmeTotal = srCmeTotal + browserCmeTotal
        if cmeTotal == 0:
            context = {
                'error': 'No CME credits earned in this date range.'
            }
            logInfo(logger, request, context['error'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        if profile.isPhysician() and not profile.isNPIComplete():
            context = {
                'error': 'Please update your profile with your NPI Number.'
            }
            logInfo(logger, request, context['error'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        elif profile.isNurse() and not user.statelicenses.exists():
            context = {
                'error': 'Please update your profile with your State License.'
            }
            logInfo(logger, request, context['error'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)

        certificate = None
        state_license = None
        certClass = MDCertificate
        if browserCmeTotal > 0:
            if profile.isNurse():
                state_license = user.statelicenses.all()[0]
                certClass = NurseCertificate
            certificate = self.makeCertificate(certClass, profile, brcme_startdt, enddt, cmeTotal, state_license=state_license)
        report = self.makeReport(profile, startdt, enddt, certificate)
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

    def makeReport(self, profile, startdt, enddt, certificate):
        """
        The brcmeEvents.tags value contains the AMA PRA Category 1 label
        as the first tag.
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
        brcmeCertReferenceId = certificate.referenceId if certificate else None
        # get AuditReportResult
        res = Entry.objects.prepareDataForAuditReport(user, startdt, enddt)
        if not res:
            return None
        saEvents = [{
            'id': m.pk,
            'entryType': m.entryType.name,
            'date': calendar.timegm(m.activityDate.timetuple()),
            'credit': float(m.getCredits()),
            'creditType': m.formatCreditType(),
            'tags': m.formatNonSATags(),
            'authority': m.getCertifyingAuthority(),
            'activity': m.description,
            'referenceId': m.getCertDocReferenceId()
        } for m in res.saEntries]
        brcmeEvents = [{
            'id': m.pk,
            'entryType': m.entryType.name,
            'date': calendar.timegm(m.activityDate.timetuple()),
            'credit': float(m.brcme.credits),
            'creditType': m.formatCreditType(),
            'tags': m.formatTags(),
            'authority': m.getCertifyingAuthority(),
            'activity': m.brcme.formatActivity(),
            'referenceId': brcmeCertReferenceId
        } for m in res.brcmeEntries]
        srcmeEvents = [{
            'id': m.pk,
            'entryType': m.entryType.name,
            'date': calendar.timegm(m.activityDate.timetuple()),
            'credit': float(m.srcme.credits),
            'creditType': m.formatCreditType(),
            'tags': m.formatTags(),
            'authority': m.getCertifyingAuthority(),
            'activity': m.description,
            'referenceId': m.getCertDocReferenceId()
        } for m in res.otherSrCmeEntries]
        creditSumByTagList = sorted(
            [{'name': k, 'total': float(v)} for k,v in res.creditSumByTag.items()],
            key=itemgetter('name')
        )
        report_data = {
            'saEvents': saEvents,
            'otherEvents': brcmeEvents+srcmeEvents,
            'saCmeTotal': res.saCmeTotal,
            'otherCmeTotal': res.otherCmeTotal,
            'creditSumByTag': creditSumByTagList
        }
        ##pprint(report_data)
        # create AuditReport instance
        report = AuditReport(
            user=user,
            name = reportName,
            startDate = startdt,
            endDate = enddt,
            saCredits = res.saCmeTotal,
            otherCredits = res.otherCmeTotal,
            certificate=certificate,
            data=JSONRenderer().render(report_data)
        )
        report.save()
        hashgen = Hashids(salt=settings.REPORT_HASHIDS_SALT, min_length=10)
        report.referenceId = hashgen.encode(report.pk)
        report.save(update_fields=('referenceId',))
        return report


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