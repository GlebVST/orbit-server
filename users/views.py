from datetime import datetime
from decimal import Decimal
from pprint import pprint
from smtplib import SMTPException

import pytz
from django.contrib.auth.models import User
from django.db import transaction
from django.http import QueryDict
from django.utils import timezone
from rest_framework import generics, permissions, status, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser,MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.ext.rest_framework import TokenHasReadWriteScope, TokenHasScope
# app
from .models import *
from .serializers import *
from .permissions import *
from django.core.mail import send_mail, EmailMessage
from django.template import Context
from django.template.loader import render_to_string, get_template
from django.conf import settings

import copy
import StringIO
from PyPDF2 import PdfFileWriter, PdfFileReader
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from django.http import HttpResponse
from reportlab.lib.fonts import addMapping
from glob import glob
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from hashids import Hashids
from django.utils.dateformat import DateFormat

FONT_CHARACTER_TABLES = {}
for font_file in glob('{0}/fonts/*.ttf'.format(settings.PDF_TEMPLATES_DIR)):
    font_name = os.path.basename(os.path.splitext(font_file)[0])
    ttf = TTFont(font_name, font_file)
    FONT_CHARACTER_TABLES[font_name] = ttf.face.charToGlyph.keys()
    pdfmetrics.registerFont(TTFont(font_name, font_file))
# Country
class CountryList(generics.ListCreateAPIView):
    queryset = Country.objects.all().order_by('id')
    serializer_class = CountrySerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class CountryDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# Degree
class DegreeList(generics.ListCreateAPIView):
    queryset = Degree.objects.all().order_by('id')
    serializer_class = DegreeSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class DegreeDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Degree.objects.all()
    serializer_class = DegreeSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# custom pagination for large page size
class LongPagination(PageNumberPagination):
    page_size = 10000

# PracticeSpecialty - list only
class PracticeSpecialtyList(generics.ListAPIView):
    queryset = PracticeSpecialty.objects.all().order_by('name')
    serializer_class = PracticeSpecialtyListSerializer
    pagination_class = LongPagination
    permission_classes = (IsContentAdminOrAny,)


class PracticeSpecialtyDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = PracticeSpecialty.objects.all()
    serializer_class = PracticeSpecialtySerializer
    permission_classes = (IsContentAdminOrAny,)

# CmeTag
class CmeTagList(generics.ListCreateAPIView):
    queryset = CmeTag.objects.all().order_by('-priority', 'name')
    serializer_class = CmeTagSerializer
    pagination_class = LongPagination
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class CmeTagDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = CmeTag.objects.all()
    serializer_class = CmeTagSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# EntryType
class EntryTypeList(generics.ListCreateAPIView):
    queryset = EntryType.objects.all().order_by('name')
    serializer_class = EntryTypeSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class EntryTypeDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = EntryType.objects.all()
    serializer_class = EntryTypeSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# Sponsor
class SponsorList(generics.ListCreateAPIView):
    queryset = Sponsor.objects.all().order_by('name')
    serializer_class = SponsorSerializer
    pagination_class = LongPagination
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class SponsorDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Sponsor.objects.all()
    serializer_class = SponsorSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]


# Profile
# A list of profiles is readable by any authenticated user
# A profile cannot be created from the API because it is created by the psa pipeline for each user.
class ProfileList(generics.ListAPIView):
    queryset = Profile.objects.all().order_by('lastName').select_related('country')
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

# A profile is viewable by any authenticated user.
# A profile can edited only by the owner from the API
# A profile cannot be deleted from the API
class ProfileDetail(generics.RetrieveUpdateAPIView):
    queryset = Profile.objects.all().select_related('country')
    serializer_class = ProfileSerializer
    permission_classes = [IsOwnerOrAuthenticated, TokenHasReadWriteScope]

class VerifyProfile(APIView):
    """This view expects the lookup-id in the JSON object for the POST.
    It finds the user linked to the customerId and sets their profile.verified flag to True. If user not found, return success=False.
    Example JSON:
        {"lookup-id": customerId string}
    """
    permission_classes = (permissions.AllowAny,)
    def post(self, request, *args, **kwargs):
        userdata = request.data
        lookupId = userdata.get('lookup-id', None)
        if not lookupId:
            context = {
                'success': False,
                'message': 'Lookup Id value is required'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # get customer object from database
        try:
            customer = Customer.objects.get(customerId=lookupId)
        except Customer.DoesNotExist:
            context = {
                'success': False,
                'message': 'Invalid Lookup Id.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            # set verified to True
            profile = customer.user.profile
            if not profile.verified:
                profile.verified = True
                profile.save()
            context = {'success': True}
            return Response(context, status=status.HTTP_200_OK)

class VerifyProfileEmail(APIView):
    """
    This endpoint will user the current user's profile to send gmail verification email with a special link.

    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def get(self, request, *args, **kwargs):
        user = request.user
        customer = Customer.objects.get(user=request.user)
        subject = settings.EMAIL_VERIFICATION_SUBJECT
        from_email = settings.EMAIL_FROM
        ctx = {
            'profile': user.profile,
            'customer': customer,
            'domain': settings.DOMAIN_REFERENCE
        }
        message = get_template('email/verification.html').render(Context(ctx))
        msg = EmailMessage(subject, message, to=[user.profile.contactEmail], from_email=from_email)
        msg.content_subtype = 'html'
        try:
            msg.send()
        except SMTPException as e:
            logger.debug('Failure sending email: {}'.format(e))
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)

        context = {'success': True}
        return Response(context, status=status.HTTP_200_OK)

# Customer
# A list of customers is readable by any Admin user
# A customer cannot be created from the API because it is created by the psa pipeline for each user.
class CustomerList(generics.ListAPIView):
    queryset = Customer.objects.all().order_by('-created')
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAdminUser, TokenHasReadWriteScope]

# A customer is viewable by any Admin user (or the user that is the owner of the account)
# A customer cannot be edited from the API because it only contains read-only fields
# A customer cannot be deleted from the API
class CustomerDetail(generics.RetrieveAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsOwnerOrAdmin, TokenHasReadWriteScope]

# SubscriptionPlan : new payment model
class SubscriptionPlanList(generics.ListCreateAPIView):
    queryset = SubscriptionPlan.objects.all().order_by('created')
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class SubscriptionPlanDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# SubscriptionPlanPublic : for AllowAny
class SubscriptionPlanPublic(APIView):
    """This expects a single annual plan in the db which
    must be in agreement with the Braintree Control Panel.
    """
    permission_classes = (permissions.AllowAny,)

    def serialize_and_render(self, plan):
        context = {'plan': None}
        if plan:
            s = SubscriptionPlanPublicSerializer(plan)
            context['plan'] = s.data
        return Response(context, status=status.HTTP_200_OK)

    def get(self, request, format=None):
        qset = SubscriptionPlan.objects.filter(active=True)
        plan = qset[0] if qset.exists() else None
        return self.serialize_and_render(plan)



# custom pagination for BrowserCmeOfferList
class BrowserCmeOfferPagination(PageNumberPagination):
    page_size = 5

class BrowserCmeOfferList(generics.ListAPIView):
    """
    Find the top N un-redeemed and unexpired offers order by expireDate
    (earliest first) for the authenticated user.
    """
    serializer_class = BrowserCmeOfferSerializer
    pagination_class = BrowserCmeOfferPagination
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanViewOffer)

    def get_queryset(self):
        user = self.request.user
        now = timezone.now()
        return BrowserCmeOffer.objects.filter(
            user=user,
            expireDate__gt=now,
            redeemed=False
            ).select_related('sponsor').order_by('expireDate')


#
# FEED
#
class FeedListPagination(PageNumberPagination):
    page_size = 10

class FeedList(generics.ListAPIView):
    serializer_class = EntryReadSerializer
    pagination_class = FeedListPagination
    permission_classes = (CanViewFeed, permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        user = self.request.user
        return Entry.objects.filter(user=user, valid=True).select_related('entryType','sponsor').order_by('-created')

class FeedEntryDetail(generics.RetrieveDestroyAPIView):
    serializer_class = EntryReadSerializer
    permission_classes = (CanViewFeed, IsOwnerOrAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        user = self.request.user
        return Entry.objects.filter(user=user, valid=True).select_related('entryType', 'sponsor')

    def perform_destroy(self, instance):
        """Entry must be of type srcme else raise ValidationError"""
        if instance.entryType != ENTRYTYPE_SRCME:
            raise serializers.ValidationError('Invalid entryType for deletion.')

    def delete(self, request, *args, **kwargs):
        """Delete entry and any documents associated with it.
        Currently, only SRCme entries can be deleted from the UI.
        """
        instance = self.get_object()
        if instance.documents.exists():
            for doc in instance.documents.all():
                logger.debug('Deleting document {0}'.format(doc))
                doc.delete()
        return self.destroy(request, *args, **kwargs)

class TagsMixin(object):
    """Mixin to handle the tags parameter in request.data
    for SRCme and BrowserCme entry form.
    """

    def get_tags(self, form_data):
        """Handle different format for tags in request body
        Swagger UI sends tags as a list, e.g.
            tags: ['1','2']
        UI sends tags as a comma separated string of IDs, e.g.
            tags: "1,2"
        """
        #pprint(form_data) # <type 'dict'>
        tags = form_data.get('tags', '')
        if type(tags) == type(u'') and ',' in tags:
            tag_ids = tags.split(",") # convert "1,2" to [1,2]
            form_data['tags'] = tag_ids

class CreateBrowserCme(TagsMixin, generics.CreateAPIView):
    """
    Create a BrowserCme Entry in the user's feed.
    This action redeems the BrowserCmeOffer specified in the
    request, and sets the redeemed flag on the offer.
    """
    serializer_class = BRCmeCreateSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanPostBRCme)

    def perform_create(self, serializer, format=None):
        user = self.request.user
        with transaction.atomic():
            brcme = serializer.save(user=user)
            offer = brcme.offer
            # set redeemed flag on offer
            offer.redeemed = True
            offer.save()
        return brcme

    def create(self, request, *args, **kwargs):
        """Override create to add custom keys to response"""
        form_data = request.data.copy()
        self.get_tags(form_data)
        logger.debug(form_data)
        serializer = self.get_serializer(data=form_data)
        serializer.is_valid(raise_exception=True)
        brcme = self.perform_create(serializer)
        entry = brcme.entry
        offer = brcme.offer
        context = {
            'success': True,
            'id': entry.pk,
            'logo_url': entry.sponsor.logo_url,
            'created': entry.created,
            'credits': offer.credits
        }
        return Response(context, status=status.HTTP_201_CREATED)


class UpdateBrowserCme(TagsMixin, generics.UpdateAPIView):
    """
    Update a BrowserCme Entry in the user's feed.
    This action does not change the credits earned from the original creation.
    """
    serializer_class = BRCmeUpdateSerializer
    permission_classes = (CanPostBRCme, IsEntryOwner, TokenHasReadWriteScope)

    def get_queryset(self):
        return BrowserCme.objects.select_related('entry')

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        form_data = request.data.copy()
        self.get_tags(form_data)
        logger.debug(form_data)
        serializer = self.get_serializer(instance, data=form_data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        entry = Entry.objects.get(pk=instance.pk)
        context = {
            'success': True,
            'modified': entry.modified
        }
        return Response(context)



class CreateSRCme(TagsMixin, generics.CreateAPIView):
    """
    Create SRCme Entry in the user's feed.
    """
    serializer_class = SRCmeFormSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanPostSRCme)

    def get_queryset(self):
        user = self.request.user
        return SRCme.objects.filter(user=user).select_related('entry')

    def perform_create(self, serializer, format=None):
        """If documents is specified, verify that document.user
        is request.user, else raise ValidationError.
        """
        user = self.request.user
        doc_ids = self.request.data.get('documents', [])
        num_docs = len(doc_ids)
        if num_docs:
            qset = Document.objects.filter(user=user, pk__in=doc_ids)
            if qset.count() != num_docs:
                logger.debug('CreateSRCme: Invalid documentId(s). queryset.count does not match num_docs.')
                raise serializers.ValidationError('Invalid documentId(s) specified for user.')
        with transaction.atomic():
            srcme = serializer.save(user=user)
        return srcme

    def create(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""
        form_data = request.data.copy()
        #pprint(form_data)
        self.get_tags(form_data)
        logger.debug(form_data)
        in_serializer = self.get_serializer(data=form_data)
        in_serializer.is_valid(raise_exception=True)
        srcme = self.perform_create(in_serializer)
        out_serializer = CreateSRCmeOutSerializer(srcme.entry)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)

class UpdateSRCme(TagsMixin, generics.UpdateAPIView):
    """
    Update an existing SRCme Entry in the user's feed.
    """
    serializer_class = SRCmeFormSerializer
    permission_classes = (CanPostSRCme, IsEntryOwner, TokenHasReadWriteScope)

    def get_queryset(self):
        return SRCme.objects.select_related('entry')

    def perform_update(self, serializer, format=None):
        """If documents is specified, verify that document.user
        is request.user, else raise ValidationError.
        """
        user = self.request.user
        # check documents
        doc_ids = self.request.data.get('documents', [])
        num_docs = len(doc_ids)
        if num_docs:
            qset = Document.objects.filter(user=user, pk__in=doc_ids)
            if qset.count() != num_docs:
                logger.debug('UpdateSRCme: Invalid documentId(s). queryset.count does not match num_docs.')
                raise serializers.ValidationError('Invalid documentId(s) specified for user.')
        with transaction.atomic():
            srcme = serializer.save(user=user)
        return srcme

    def update(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        form_data = request.data.copy()
        self.get_tags(form_data)
        logger.debug(form_data)
        in_serializer = self.get_serializer(instance, data=form_data, partial=partial)
        in_serializer.is_valid(raise_exception=True)
        self.perform_update(in_serializer)
        entry = Entry.objects.get(pk=instance.pk)
        out_serializer = UpdateSRCmeOutSerializer(entry)
        return Response(out_serializer.data)


class CreateDocument(generics.CreateAPIView):
    serializer_class = UploadDocumentSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    parser_classes = (MultiPartParser,FormParser,)

    def perform_create(self, serializer, format=None):
        user = self.request.user
        instance = serializer.save(user=user)
        return instance

    def create(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""
        in_serializer = self.get_serializer(data=request.data)
        in_serializer.is_valid(raise_exception=True)
        instance = self.perform_create(in_serializer)
        out_data = [instance,]
        if instance.image_w:
            # find thumb
            qset = Document.objects.filter(user=request.user, set_id=instance.set_id, is_thumb=True)
            if qset.exists():
                out_data.insert(0, qset[0])
        # serialized data contains either 1 or 2 records
        out_serializer = DocumentReadSerializer(out_data, many=True)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)

class DeleteDocument(APIView):
    """
    This view expects a list of document IDs (pk of document in db) in the JSON object for the POST.
    It finds the associated documents and deletes them.
    This also checks that request.user owns the document-id, else return 400.
    Example JSON:
        {"document-ids": [1,2,3]}
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, *args, **kwargs):
        userdata = request.data
        doc_pks = userdata.get('document-id', [])
        if not doc_pks:
            context = {
                'success': False,
                'message': 'An array of Document Id (pk) values is required.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # find Document instances in db : filter by pk AND user
        qset = Document.objects.filter(
            user=request.user,
            pk__in=doc_pks
        )
        if not qset.exists():
            context = {
                'success': False,
                'message': 'Invalid Document Id list.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            for instance in qset:
                # delete the file from storage, and the model instance
                instance.document.delete()
                instance.delete()
            context = {'success': True}
            return Response(context, status=status.HTTP_200_OK)



# User Feedback
class UserFeedbackList(generics.ListCreateAPIView):
    serializer_class = UserFeedbackSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def get_queryset(self):
        return UserFeedback.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

# Eligible Site
class EligibleSiteList(generics.ListCreateAPIView):
    queryset = EligibleSite.objects.all().order_by('domain_title','created')
    serializer_class = EligibleSiteSerializer
    pagination_class = LongPagination
    permission_classes = (IsContentAdminOrAny,)

class EligibleSiteDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = EligibleSite.objects.all()
    serializer_class = EligibleSiteSerializer
    permission_classes = (IsContentAdminOrAny,)


#
# Dashboard
#
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
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        try:
            profile = Profile.objects.get(user=request.user)
        except Profile.DoesNotExist:
            context = {
                'error': 'Invalid user. No profile found.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        user_tags = profile.cmeTags.all()
        satag = CmeTag.objects.get(name=CMETAG_SACME)
        stats = {
            ENTRYTYPE_BRCME: {
                'total': Entry.objects.sumBrowserCme(request.user, startdt, enddt),
                'untagged': Entry.objects.sumBrowserCme(request.user, startdt, enddt, untaggedOnly=True)
            },
            ENTRYTYPE_SRCME: {
                'total': Entry.objects.sumSRCme(request.user, startdt, enddt),
                'untagged': Entry.objects.sumSRCme(request.user, startdt, enddt, untaggedOnly=True),
                satag.name: Entry.objects.sumSRCme(request.user, startdt, enddt, satag)
            }
        }
        for tag in user_tags:
            stats[ENTRYTYPE_BRCME][tag.name] = Entry.objects.sumBrowserCme(request.user, startdt, enddt, tag)
            stats[ENTRYTYPE_SRCME][tag.name] = Entry.objects.sumSRCme(request.user, startdt, enddt, tag)
        return self.serialize_and_render(stats)

#
# PDF
#
class CmeCertificatePdf(APIView):
    """
    This view expects a start date and end date in UNIX epoch format
    (number of seconds since 1970/1/1) as URL parameters. It calculates
    the total CME credit for the time period for the current
    user, generates certificate record with PDF printout and stores that on S3

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
    # permission_classes = (permissions.AllowAny,)
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanViewDashboard)
    def post(self, request, start, end):
        try:
            startdt = timezone.make_aware(datetime.utcfromtimestamp(int(start)), pytz.utc)
            enddt = timezone.make_aware(datetime.utcfromtimestamp(int(end)), pytz.utc)
        except ValueError:
            context = {
                'error': 'Invalid date parameters'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        try:
            profile = Profile.objects.get(user=request.user)
        except Profile.DoesNotExist:
            context = {
                'error': 'Invalid user. No profile found.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        degrees = profile.degrees.all()
        certificateName = "{0} {1}, {2}".format(profile.firstName, profile.lastName, ", ".join(str(degree.abbrev) for degree in degrees))

        browserCmeTotal = Entry.objects.sumBrowserCme(request.user, startdt, enddt)
        srCmeTotal = Entry.objects.sumSRCme(request.user, startdt, enddt)
        cmeTotal = browserCmeTotal+ srCmeTotal
        hashids = Hashids(salt=settings.HASHIDS_SALT, min_length = 10)
        certificate = Certificate(
            name = certificateName,
            startDate = startdt,
            endDate = enddt,
            credits = cmeTotal,
            user=request.user
        )
        certificate.save()
        certificate.referenceId = hashids.encode(certificate.id)
        isVerified = any(d.abbrev.lower() == "DO" or d.abbrev.lower() == "md" for d in degrees)
        pdf_blob = self.generateCertificate(isVerified, certificate.referenceId, certificateName, cmeTotal, startdt, enddt, certificate.created)
        cf = ContentFile(pdf_blob) # Create a ContentFile from the output
        certificate.document.save("{0}.pdf".format(certificate.referenceId), cf, save=True)

        out_serializer = CertificateSerializer(certificate)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)

    def generateCertificate(self, verified, reference, certificateName, credit, startDate, endDate, issued):
        template_pdf = PdfFileReader(
            file("{0}/cme-certificate-participation.pdf".format(settings.PDF_TEMPLATES_DIR), "rb"), strict=False
        )
        if verified:
            template_pdf = PdfFileReader(
                file("{0}/cme-certificate-verified.pdf".format(settings.PDF_TEMPLATES_DIR), "rb"), strict=False
            )
        # This file is overlaid on the template certificate
        overlay_pdf_buffer = StringIO.StringIO()
        pdfCanvas = canvas.Canvas(overlay_pdf_buffer, pagesize=landscape(A4))
        addMapping('OpenSans-Light', 0, 0, 'OpenSans-Light')
        addMapping('OpenSans-Light', 0, 1, 'OpenSans-LightItalic')
        addMapping('OpenSans-Light', 1, 0, 'OpenSans-Bold')
        addMapping('OpenSans-Regular', 0, 0, 'OpenSans-Regular')
        addMapping('OpenSans-Regular', 0, 1, 'OpenSans-Italic')
        addMapping('OpenSans-Regular', 1, 0, 'OpenSans-Bold')
        addMapping('OpenSans-Regular', 1, 1, 'OpenSans-BoldItalic')
        styleOpenSans = ParagraphStyle(name="opensans-regular", leading=10, fontName='OpenSans-Bold')
        styleOpenSansLight = ParagraphStyle(name="opensans-light", leading=10, fontName='OpenSans-Regular')

        WIDTH = 297  # width in mm (A4)
        HEIGHT = 210  # hight in mm (A4)
        LEFT_INDENT = 49  # mm from the left side to write the text
        RIGHT_INDENT = 49  # mm from the right side for the CERTIFICATE
        # CLIENT NAME
        styleOpenSans.fontSize = 20
        styleOpenSans.leading = 10
        styleOpenSans.textColor = colors.Color(0, 0, 0)
        styleOpenSans.alignment = TA_LEFT

        styleOpenSansLight.fontSize = 12
        styleOpenSansLight.leading = 10
        styleOpenSansLight.textColor = colors.Color(
            0.1, 0.1, 0.1)
        styleOpenSansLight.alignment = TA_LEFT

        paragraph = Paragraph(certificateName, styleOpenSans)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12 * mm, 120 * mm)

        paragraph = Paragraph("{0} - {1}".format(DateFormat(startDate).format('d F Y'), DateFormat(endDate).format('d F Y')), styleOpenSansLight)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12.2 * mm, 65 * mm)

        styleOpenSans.fontSize = 14
        text = "<i>AMA PRA Category 1 Credits<sup>TM</sup></i> Awarded"
        if not verified:
            text = "Hours of Participation Awarded"
        paragraph = Paragraph("{0} {1}".format(credit, text), styleOpenSans)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12.2 * mm, 53.83 * mm)

        styleOpenSans.fontSize = 9
        paragraph = Paragraph("Issued: {0}".format(DateFormat(issued).format('d F Y')), styleOpenSans)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12.2 * mm, 12 * mm)

        paragraph = Paragraph("https://{0}/certificate/{1}".format(settings.DOMAIN_REFERENCE, reference), styleOpenSans)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 127.5 * mm, 12 * mm)

        if not verified:
            styleOpenSansLight.fontSize = 7
            styleOpenSansLight.textColor = colors.Color(
                0.3, 0.3, 0.3)
            text = "This activity was designated for {0} <i>AMA PRA Category 1 Credit<sup>TM</sup></i>. This activity has been planned and implemented in accordance with the Essential Areas <br/>and policies of the Accreditation Council for Continuing Medical Education through the joint providership Tufts University School of Medicine (TUSM) and <br/>Transcend Review, Inc. TUSM is accredited by the ACCME to provide continuing education for physicians."
            paragraph = Paragraph(text.format(credit), styleOpenSansLight)
            paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
            paragraph.drawOn(pdfCanvas, 12.2 * mm, 24 * mm)


        pdfCanvas.showPage()
        pdfCanvas.save()
        # Merge the overlay with the template, then write it to file
        writer = PdfFileWriter()
        overlay = PdfFileReader(overlay_pdf_buffer, strict=False)
        mergedPage = copy.copy(
            PdfFileReader(file("{0}/blank.pdf".format(settings.PDF_TEMPLATES_DIR), "rb"), strict=False)).getPage(0)
        mergedPage.mergePage(template_pdf.getPage(0))
        mergedPage.mergePage(overlay.getPage(0))
        writer.addPage(mergedPage)
        output = StringIO.StringIO()
        writer.write(output)
        return output.getvalue()


class CmeCertificate(APIView):
    """
    This view expects a certificate reference ID and allows a public acccess

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
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        out_serializer = CertificateSerializer(certificate)
        return Response(out_serializer.data, status=status.HTTP_200_OK)