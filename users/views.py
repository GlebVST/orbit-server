import calendar
from datetime import datetime
from hashids import Hashids
import logging
from operator import itemgetter
from urlparse import urlparse
from smtplib import SMTPException
import pytz
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.postgres.search import SearchVector
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db import transaction
from django.forms.models import model_to_dict
from django.template.loader import get_template
from django.utils import timezone

from rest_framework import generics, exceptions, permissions, status, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope, TokenHasScope
# proj
from common.logutils import *
# app
from .models import *
from .serializers import *
from .permissions import *
from .pdf_tools import SAMPLE_CERTIFICATE_NAME, MDCertificate, NurseCertificate, MDStoryCertificate, NurseStoryCertificate

logger = logging.getLogger('api.views')

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
    queryset = Degree.objects.all().order_by('sort_order')
    serializer_class = DegreeSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class DegreeDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Degree.objects.all()
    serializer_class = DegreeSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]


# Hospital
class HospitalList(generics.ListCreateAPIView):
    serializer_class = HospitalSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

    def get_queryset(self):
        """Filter by GET parameter: q"""
        qset = Hospital.objects.select_related('state').annotate(
                search=SearchVector('name','city', 'state__name')).all()
        q = self.request.query_params.get('q', '')
        if q:
            q = q.replace(' in', '')
            qset = qset.filter(search=q)
        return qset.order_by('state','city','name')

class HospitalDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Hospital.objects.all()
    serializer_class = HospitalSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]


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
    #queryset = CmeTag.objects.all().order_by('-priority', 'name')
    serializer_class = CmeTagWithSpecSerializer
    pagination_class = LongPagination
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

    def get_queryset(self):
        return CmeTag.objects.all().prefetch_related('specialties').order_by('-priority','name')

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
# A profile cannot be created from the API because it is created by the auth_backend
class ProfileList(generics.ListAPIView):
    queryset = Profile.objects.all().order_by('-created').select_related('country')
    serializer_class = ReadProfileSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

# A profile can be edited only by the owner from the API
# A profile cannot be deleted from the API
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


class SignupDiscountList(APIView):
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get(self, request, *args, **kwargs):
        user = request.user
        profile = user.profile
        data = []
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        if user_subs is None or (user_subs.display_status == UserSubscription.UI_TRIAL) or (user_subs.display_status == UserSubscription.UI_TRIAL_CANCELED):
            # User has never had an active subscription.
            promo = SignupEmailPromo.objects.get_casei(user.email)
            if promo:
                # this overrides any other discount
                plan = SubscriptionPlan.objects.get(planId=profile.planId)
                d = Discount.objects.get(discountType=BASE_DISCOUNT_TYPE, activeForType=True)
                discount_amount = plan.discountPrice - promo.first_year_price
                data = [{
                    'discountId': d.discountId,
                    'amount': discount_amount,
                    'displayLabel': promo.display_label,
                    'discountType': 'signup-email'
                }]
            else:
                discounts = UserSubscription.objects.getDiscountsForNewSubscription(user)
                data = [{
                    'discountId': d['discount'].discountId,
                    'amount': d['discount'].amount,
                    'discountType': d['discountType'],
                    'displayLabel': d['displayLabel']
                    } for d in discounts]
        # sort by amount desc
        display_data = sorted(data, key=itemgetter('amount'), reverse=True)
        context = {'discounts': display_data}
        return Response(context, status=status.HTTP_200_OK)


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
            profile.save()
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
        context = {
            'cmeTags': [ProfileCmetagSerializer(m).data for m in qset]
        }
        return Response(context, status=status.HTTP_200_OK)


class VerifyProfileEmail(APIView):
    """
    This endpoint will user the current user's profile to send gmail verification email with a special link.
    2017-08-07: disable sending the email because Auth0 is supposed to send the verification email.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def get(self, request, *args, **kwargs):
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

# Current usage is for nurse state licenses
class UserStateLicenseList(generics.ListCreateAPIView):
    serializer_class = StateLicenseSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        user = self.request.user
        return StateLicense.objects.filter(user=user).order_by('-created')

    def perform_create(self, serializer, format=None):
        """At present time, only RN StateLicense is supported
        Note: In order to handle unique constraint on ('user','state','license_type','license_no'), caller must instantiate serializer with the instance if the constraint already exists. In this case, the serializer.save will update the existing instance.
        """
        user = self.request.user
        lt = LicenseType.objects.get(name='RN')
        instance = serializer.save(user=user, license_type=lt)
        return instance

    def create(self, request, *args, **kwargs):
        """Override create to handle unique constraint on StateLicense model."""
        form_data = request.data.copy()
        serializer = self.get_serializer(data=form_data)
        serializer.is_valid(raise_exception=True)
        lt = LicenseType.objects.get(name='RN')
        # check if unique constraint already exists
        qset = StateLicense.objects.filter(
                user=request.user,
                license_type=lt,
                state_id=form_data['state'],
                license_no=form_data['license_no']
            )
        if qset.exists():
            m = qset[0]
            logDebug(logger, request, 'Update existing statelicense {0.pk}'.format(m))
            serializer = self.get_serializer(instance=m, data=form_data)
            serializer.is_valid(raise_exception=True)
        instance = self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class UserStateLicenseDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = StateLicense.objects.all()
    serializer_class = StateLicenseSerializer
    permission_classes = [IsOwnerOrAuthenticated, TokenHasReadWriteScope]

    def perform_update(self, serializer, format=None):
        user = self.request.user
        instance = serializer.save(user=user)
        return instance

# SubscriptionPlan
class SubscriptionPlanList(generics.ListAPIView):
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

    def get_queryset(self):
        """Filter plans by plan_key sourced from the planId in request.user.profile"""
        profile = self.request.user.profile
        try:
            plan = SubscriptionPlan.objects.get(planId=profile.planId)
            plan_key = plan.plan_key
        except SubscriptionPlan.DoesNotExist:
            logWarning(logger, self.request, "Invalid profile.planId: {0.planId}".format(profile))
            return SubscriptionPlan.objects.none().order_by('id')
        else:
            filter_kwargs = dict(active=True, plan_key=plan_key)
            return SubscriptionPlan.objects.filter(**filter_kwargs).order_by('price','pk')

class SubscriptionPlanDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# SubscriptionPlanPublic : for AllowAny
class SubscriptionPlanPublic(generics.ListAPIView):
    """Returns a list of eligible plans for a given landing page key using the SubscriptionPlanPublicSerializer
    """
    serializer_class = SubscriptionPlanPublicSerializer
    permission_classes = (permissions.AllowAny,)

    def get_queryset(self):
        """Filter plans by plan_key in url using iexact search"""
        lkey = self.kwargs['landing_key']
        if lkey.endswith('/'):
            lkey = lkey[0:-1]
        try:
            plan_key = SubscriptionPlanKey.objects.get(name__iexact=lkey)
        except SubscriptionPlanKey.DoesNotExist:
            logWarning(logger, self.request, "Invalid key: {0}".format(lkey))
            return SubscriptionPlan.objects.none().order_by('id')
        else:
            return SubscriptionPlan.objects.getPlansForKey(plan_key)

# custom pagination for OrbitCmeOfferList
class OrbitCmeOfferPagination(PageNumberPagination):
    page_size = 5

class OrbitCmeOfferList(generics.ListAPIView):
    """
    Get the un-redeemed and unexpired valid offers order by modified desc
    (latest modified first) for the authenticated user.
    """
    serializer_class = OrbitCmeOfferSerializer
    pagination_class = OrbitCmeOfferPagination
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanViewOffer)

    def get_queryset(self):
        user = self.request.user
        now = timezone.now()
        filter_kwargs = dict(
            valid=True,
            user=user,
            expireDate__gt=now,
            redeemed=False)
        return OrbitCmeOffer.objects.filter(**filter_kwargs).select_related('sponsor','url').order_by('-modified')


#
# FEED
#

class FeedListPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000

class FeedList(generics.ListAPIView):
    serializer_class = EntryReadSerializer
    pagination_class = FeedListPagination
    permission_classes = (CanViewFeed, permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        user = self.request.user
        return Entry.objects.filter(user=user, valid=True).select_related('entryType','sponsor').order_by('-created')


class FeedEntryDetail(LogValidationErrorMixin, generics.RetrieveDestroyAPIView):
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
                logDebug(logger, request, 'Deleting document {0}'.format(doc))
                doc.delete()
        return self.destroy(request, *args, **kwargs)


class InvalidateEntry(generics.UpdateAPIView):
    serializer_class = EntryReadSerializer
    permission_classes = (CanInvalidateEntry, IsOwnerOrAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        user = self.request.user
        return Entry.objects.filter(user=user, valid=True)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        msg = 'Invalidate entry {0}'.format(instance)
        logInfo(logger, request, msg)
        instance.valid = False
        instance.save()
        context = {'success': True}
        return Response(context)


class InvalidateOffer(generics.UpdateAPIView):
    serializer_class = OrbitCmeOfferSerializer
    permission_classes = (IsOwnerOrAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        user = self.request.user
        return OrbitCmeOffer.objects.filter(user=user, valid=True)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.redeemed:
            context = {
                'success': False,
                'message': 'Offer has already been redeemed.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        msg = 'Invalidate offer {0.pk}/{0}'.format(instance)
        logInfo(logger, request, msg)
        instance.valid = False
        instance.save()
        context = {'success': True}
        return Response(context)


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

class CreateBrowserCme(LogValidationErrorMixin, TagsMixin, generics.CreateAPIView):
    """
    Create a BrowserCme Entry in the user's feed.
    This action redeems the offer specified in the request.
    """
    serializer_class = BRCmeCreateSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanPostBRCme)

    def perform_create(self, serializer, format=None):
        user = self.request.user
        with transaction.atomic():
            # Create entry, brcme instances and redeem offer
            brcme = serializer.save(user=user)
        return brcme

    def create(self, request, *args, **kwargs):
        """Override create to add custom keys to response"""
        form_data = request.data.copy()
        self.get_tags(form_data)
        serializer = self.get_serializer(data=form_data)
        serializer.is_valid(raise_exception=True)
        brcme = self.perform_create(serializer)
        entry = brcme.entry
        user = request.user
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        pdata = UserSubscription.objects.serialize_permissions(user, user_subs)
        context = {
            'success': True,
            'id': entry.pk,
            'logo_url': entry.sponsor.logo_url,
            'created': entry.created,
            'brcme': model_to_dict(brcme),
            'permissions': pdata['permissions'],
            'brcme_limit': pdata['brcme_limit']
        }
        return Response(context, status=status.HTTP_201_CREATED)


class UpdateBrowserCme(LogValidationErrorMixin, TagsMixin, generics.UpdateAPIView):
    """
    Update a BrowserCme Entry in the user's feed.
    This action does not change the credits earned from the original creation.
    """
    serializer_class = BRCmeUpdateSerializer
    permission_classes = (IsEntryOwner, TokenHasReadWriteScope)

    def get_queryset(self):
        return BrowserCme.objects.select_related('entry')

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        form_data = request.data.copy()
        self.get_tags(form_data)
        serializer = self.get_serializer(instance, data=form_data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        entry = Entry.objects.get(pk=instance.pk)
        context = {
            'success': True,
            'modified': entry.modified
        }
        return Response(context)



class CreateSRCme(LogValidationErrorMixin, TagsMixin, generics.CreateAPIView):
    """
    Create SRCme Entry in the user's feed.
    """
    serializer_class = SRCmeFormSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanPostSRCme)

    def get_queryset(self):
        user = self.request.user
        return SRCme.objects.filter(user=user).select_related('entry')

    def perform_create(self, serializer, format=None):
        """
        If documents is specified, verify that document.user
            is request.user, else raise ValidationError.
        """
        user = self.request.user
        doc_ids = self.request.data.get('documents', [])
        for doc_id in doc_ids:
            qset = Document.objects.filter(pk=doc_id)
            if qset.exists():
                doc = qset[0]
                if doc.user != user:
                    error_msg = 'CreateSRCme: The documentId {0} is not owned by user: {1}.'.format(doc_id, user)
                    logWarning(logger, self.request, error_msg)
                    raise serializers.ValidationError(error_msg)
            else:
                error_msg = 'CreateSRCme: Invalid documentId {0} - does not exist.'.format(doc_id)
                logWarning(logger, self.request, error_msg)
                raise serializers.ValidationError(error_msg)
        # validate creditType (enable code after ui changes)
        #creditType = self.request.data.get('creditType', '')
        #if creditType != Entry.CREDIT_CATEGORY_1 or creditType != Entry.CREDIT_OTHER:
        #    raise serializers.ValidationError('Invalid creditType.')
        with transaction.atomic():
            srcme = serializer.save(user=user)
        return srcme

    def create(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""
        form_data = request.data.copy()
        #pprint(form_data)
        self.get_tags(form_data)
        in_serializer = self.get_serializer(data=form_data)
        in_serializer.is_valid(raise_exception=True)
        srcme = self.perform_create(in_serializer)
        out_serializer = CreateSRCmeOutSerializer(srcme.entry)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)


class UpdateSRCme(LogValidationErrorMixin, TagsMixin, generics.UpdateAPIView):
    """
    Update an existing SRCme Entry in the user's feed.
    """
    serializer_class = SRCmeFormSerializer
    permission_classes = (IsEntryOwner, TokenHasReadWriteScope)

    def get_queryset(self):
        return SRCme.objects.select_related('entry')

    def perform_update(self, serializer, format=None):
        """If documents is specified, verify that document.user
        is request.user, else raise ValidationError.
        """
        user = self.request.user
        # check documents
        doc_ids = self.request.data.get('documents', [])
        for doc_id in doc_ids:
            qset = Document.objects.filter(pk=doc_id)
            if qset.exists():
                doc = qset[0]
                if doc.user != user:
                    error_msg = 'UpdateSRCme: The documentId {0} is not owned by user: {1}.'.format(doc_id, user)
                    logWarning(logger, self.request, error_msg)
                    raise serializers.ValidationError(error_msg)
            else:
                error_msg = 'UpdateSRCme: Invalid documentId {0} - does not exist.'.format(doc_id)
                logWarning(logger, self.request, error_msg)
                raise serializers.ValidationError(error_msg)
        with transaction.atomic():
            srcme = serializer.save(user=user)
        return srcme

    def update(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        form_data = request.data.copy()
        self.get_tags(form_data)
        in_serializer = self.get_serializer(instance, data=form_data, partial=partial)
        in_serializer.is_valid(raise_exception=True)
        self.perform_update(in_serializer)
        entry = Entry.objects.get(pk=instance.pk)
        out_serializer = UpdateSRCmeOutSerializer(entry)
        return Response(out_serializer.data)


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


class AccessDocumentOrCert(APIView):
    """
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


class PinnedMessageDetail(APIView):
    """Finds the latest active PinnedMessage for the user, and returns the info. Value is None if none exists.
    """
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def serialize_and_render(self, message):
        context = {'message': None}
        if message:
            s = PinnedMessageSerializer(message)
            context['message'] = s.data
        return Response(context, status=status.HTTP_200_OK)

    def get(self, request, format=None):
        message = PinnedMessage.objects.getLatestForUser(request.user)
        return self.serialize_and_render(message)


class StoryDetail(APIView):
    """Finds the latest non-expired Story and returns the info with the launch_url customized for the user.
    Value is None if none exists.
    """
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def serialize_and_render(self, user_id, story):
        context = {'story': None}
        if story:
            s = StorySerializer(story)
            context['story'] = s.data
            context['story']['launch_url'] += "={0}".format(user_id)
        return Response(context, status=status.HTTP_200_OK)

    def get(self, request, format=None):
        story = None
        user_id = request.user.profile.getAuth0Id()
        now = timezone.now()
        qset = Story.objects.filter(startDate__lte=now, endDate__gt=now).order_by('-created')
        if qset.exists():
            story = qset[0]
        return self.serialize_and_render(user_id, story)


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
