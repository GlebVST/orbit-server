import coreapi
from datetime import datetime
import logging
from urlparse import urlparse
from smtplib import SMTPException
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.forms.models import model_to_dict
from django.template.loader import get_template
from django.utils import timezone

from rest_framework import generics, exceptions, permissions, status, serializers
from rest_framework.filters import BaseFilterBackend
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope, TokenHasScope
# proj
from common.logutils import *
# app
from .models import *
from .serializers import *
from .upload_serializers import *
from .permissions import *

logger = logging.getLogger('api.users')

class LogValidationErrorMixin(object):
    def handle_exception(self, exc):
        response = super(LogValidationErrorMixin, self).handle_exception(exc)
        if response is not None and isinstance(exc, exceptions.ValidationError):
            #logWarning(logger, self.request, exc.get_full_details())
            message = "ValidationError: {0}".format(exc.detail)
            #logError(logger, self.request, message)
            logWarning(logger, self.request, message)
        return response

# custom pagination for large page size
class LongPagination(PageNumberPagination):
    page_size = 1000

class PingTest(APIView):
    """ping test response"""
    permission_classes = (permissions.AllowAny,)

    def get(self, request, format=None):
        context = {'success': True}
        return Response(context, status=status.HTTP_200_OK)

# Country - list only
class CountryList(generics.ListAPIView):
    queryset = Country.objects.all().order_by('id')
    serializer_class = CountrySerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]


# Degree - list only
class DegreeList(generics.ListAPIView):
    queryset = Degree.objects.all().order_by('sort_order')
    serializer_class = DegreeSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]


class HospitalFilterBackend(BaseFilterBackend):
    def get_schema_fields(self, view):
        return [coreapi.Field(
            name='q',
            location='query',
            required=False,
            type='string',
            description='Search by name, city or state'
        )]

    def filter_queryset(self, request, queryset, view):
        """This requires the model Manager to have a search_filter manager method"""
        search_term = request.query_params.get('q', '').strip()
        if search_term:
            logInfo(logger, request, search_term)
            return Hospital.objects.search_filter(search_term)
        return queryset.order_by('display_name')

# Hospital - list only
class HospitalList(generics.ListAPIView):
    queryset = Hospital.objects.all()
    serializer_class = HospitalSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]
    filter_backends = (HospitalFilterBackend,)


# ResidencyProgram - list only
class ResidencyProgramList(generics.ListAPIView):
    serializer_class = HospitalSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

    def get_queryset(self):
        """Filter by GET parameter: q"""
        search_term = self.request.query_params.get('q', '').strip()
        if search_term:
            return Hospital.residency_objects.search_filter(search_term)
        return Hospital.residency_objects.all().order_by('display_name')


# PracticeSpecialty - list only
class PracticeSpecialtyList(generics.ListAPIView):
    queryset = PracticeSpecialty.objects.all().order_by('name')
    serializer_class = PracticeSpecialtyListSerializer
    pagination_class = LongPagination
    permission_classes = (IsContentAdminOrAny,)


# CmeTag - list only
class CmeTagList(generics.ListAPIView):
    #queryset = CmeTag.objects.all().order_by('-priority', 'name')
    serializer_class = CmeTagWithSpecSerializer
    pagination_class = LongPagination
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

    def get_queryset(self):
        return CmeTag.objects.all().prefetch_related('specialties').order_by('-priority','name')

# Update profile
class ProfileUpdate(generics.UpdateAPIView):
    """Note: This used to be a RetrieveUpdateAPIView but we need to use
    different serializers for Retrieve vs. Update. Normally, this can be
    done using get_serializer_class. But, it does not work when using
    Swagger because Swagger calls get_serializer_class before a request
    exists in order to determine the class.
    Current fix is to just make this an Update-only view.
    """
    queryset = Profile.objects.all().select_related('country')
    serializer_class = UpdateProfileSerializer
    permission_classes = [IsOwnerOrAuthenticated, TokenHasReadWriteScope]

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        form_data = request.data.copy()
        serializer = self.get_serializer(instance, data=form_data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        profile = self.get_object()
        out_serializer = ReadProfileSerializer(profile)
        return Response(out_serializer.data)



class AffiliateIdLookup(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, *args, **kwargs):
        lookupId = self.kwargs.get('affid')
        if lookupId:
            qset = AffiliateDetail.objects.filter(affiliateId=lookupId)
            if qset.exists():
                m = qset[0]
                affl = m.affiliate
                inv_discount = Discount.objects.get(discountType=INVITEE_DISCOUNT_TYPE, activeForType=True)
                context = {
                    'username': affl.displayLabel,
                    'personalText': m.personalText,
                    'photoUrl': m.photoUrl,
                    'jobDescription': m.jobDescription,
                    'og_title': m.og_title,
                    'og_description': m.og_description,
                    'og_image': m.og_image,
                    'redirect_page': m.redirect_page,
                    'invitee_discount': inv_discount.amount
                }
                return Response(context, status=status.HTTP_200_OK)
        return Response({'success': False}, status=status.HTTP_404_NOT_FOUND)

class InviteIdLookup(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, *args, **kwargs):
        lookupId = self.kwargs.get('inviteid')
        if lookupId:
            qset = Profile.objects.filter(inviteId=lookupId)
            if qset.exists():
                profile = qset[0]
                if profile.firstName:
                    username = profile.firstName
                elif profile.lastName:
                    username = profile.lastName
                elif profile.npiFirstName:
                    username = profile.npiFirstName
                elif profile.npiLastName:
                    username = profile.npiLastName
                else:
                    username = 'Your friend'
                inv_discount = Discount.objects.get(discountType=INVITEE_DISCOUNT_TYPE, activeForType=True)
                context = {
                    'username': username,
                    'invitee_discount': inv_discount.amount
                }
                return Response(context, status=status.HTTP_200_OK)
        return Response({'success': False}, status=status.HTTP_404_NOT_FOUND)


class SetProfileAccessedTour(APIView):
    """This view sets/clears the accessedTour flag on the user's profile.
    Example JSON in the POST data:
        {"value": 0 or 1}
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, *args, **kwargs):
        value = request.data.get('value', None)
        if value not in (0, 1):
            context = {
                'success': False,
                'message': 'value must be either 0 or 1'
            }
            logError(logger, request, context['message'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        profile = request.user.profile
        bool_value = bool(value)
        if profile.accessedTour != bool_value:
            profile.accessedTour = bool_value
            profile.save(update_fields=('accessedTour',))
        context = {'success': True}
        return Response(context, status=status.HTTP_200_OK)


class ManageProfileCmetags(APIView):
    """This view allows the user to set the value of the is_active flag on the
    existing cmeTags assigned to them. It does not create or delete any tags,
    it only updates the is_active flag.
    Example JSON:
        {
            "tags": [
                {"tag":1, "is_active": true},
                {"tag":2, "is_active": false},
            ]
        }
    """
    serializer_class = ManageProfileCmetagSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)
    def post(self, request, *args, **kwargs):
        in_serializer = ManageProfileCmetagSerializer(request.user.profile, request.data)
        in_serializer.is_valid(raise_exception=True)
        profile = in_serializer.save()
        qset = ProfileCmetag.objects.filter(profile=profile)
        s = ProfileCmetagSerializer(qset, many=True)
        context = {
            'cmeTags': s.data
        }
        return Response(context, status=status.HTTP_200_OK)



class UserStateLicenseList(generics.ListAPIView):
    serializer_class = StateLicenseSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        """Returns the latest (by expireDate) license per (state, license_type)
        for the given user.
        """
        user = self.request.user
        return StateLicense.objects.getLatestSetForUser(user)


class UserStateLicenseDetail(generics.RetrieveUpdateAPIView):
    queryset = StateLicense.objects.all()
    serializer_class = StateLicenseSerializer
    permission_classes = [IsOwnerOrAuthenticated, TokenHasReadWriteScope]

    def perform_update(self, serializer, format=None):
        user = self.request.user
        instance = serializer.save(user=user)
        return instance

# TODO: client should pass user in order to allow request.user to be different from document.user
class CreateDocument(LogValidationErrorMixin, generics.CreateAPIView):
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

# TODO: client should pass user in order to allow request.user to be different from document.user
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
            message = context['message'] + ' : ' + ", ".join(doc_pks)
            logError(logger, request, message)
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
        """Create UserFeedback instance and send EmailMessage for regular feedback (entry-specific does not send email)"""
        instance = serializer.save(user=self.request.user)
        if instance.entry:
            return instance
        user = self.request.user
        profile = user.profile
        from_email = settings.EMAIL_FROM
        to_email = [settings.FEEDBACK_RECIPIENT_EMAIL,]
        if profile.lastName:
            username = profile.getFullNameAndDegree()
            userinfo = username + ' ' + user.email
        else:
            username = user.email
            userinfo = username
        subject = 'Feedback from {0} on {1:%m/%d %H:%M}'.format(username, instance.asLocalTz())
        if settings.ENV_TYPE != settings.ENV_PROD:
            envtype = '[{0}] '.format(settings.ENV_TYPE)
            subject = envtype + subject
        # create EmailMessage
        ctx = {
            'userinfo': userinfo,
            'message': instance
        }
        message = get_template('email/feedback.html').render(ctx)
        msg = EmailMessage(subject, message, to=to_email, from_email=from_email)
        msg.content_subtype = 'html'
        try:
            msg.send()
        except SMTPException as e:
            logException(logger, self.request, 'UserFeedback send email failed.')
        return instance


# Eligible Site
class EligibleSiteList(LogValidationErrorMixin, generics.ListCreateAPIView):
    queryset = EligibleSite.objects.all().order_by('domain_title','created')
    serializer_class = EligibleSiteSerializer
    pagination_class = LongPagination
    permission_classes = (IsContentAdminOrAny,)

    def perform_create(self, serializer, format=None):
        """Pre-process domain_name before saving.
        """
        data = self.request.data
        domain_name = data.get('domain_name', '')
        if domain_name.startswith('http://'):
            domain_name = domain_name[7:]
        elif domain_name.startswith('https://'):
            domain_name = domain_name[8:]
        example_url = data.get('example_url', '')
        if example_url:
            # check domain_name
            res = urlparse(example_url)
            msg = "Example_url netloc: {0}. Cleaned domain_name: {1}".format(res.netloc, domain_name)
            logInfo(logger, self.request, msg)
            netloc = res.netloc
            if netloc.startswith('www.') and not domain_name.startswith('www.'):
                netloc = netloc[4:]
            if not domain_name.startswith(netloc):
                error_msg = "The domain of the example_url must be contained in the user-specified domain_name"
                raise serializers.ValidationError(error_msg, code='domain_name')
        with transaction.atomic():
            # create EligibleSite, AllowedHost, AllowedUrl
            instance = serializer.save(domain_name=domain_name)
        return instance

class EligibleSiteDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = EligibleSite.objects.all()
    serializer_class = EligibleSiteSerializer
    permission_classes = (IsContentAdminOrAny,)

