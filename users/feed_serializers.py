import logging
from rest_framework import serializers
from .models import (
    ENTRYTYPE_BRCME,
    ENTRYTYPE_SRCME,
    ENTRYTYPE_STORY_CME,
    ENTRYTYPE_NOTIFICATION,
    CmeTag,
    Document,
    EntryType,
    Sponsor,
    OrbitCmeOffer,
    Entry,
    BrowserCme,
    SRCme,
    Story,
    StoryCme,
    Notification
)
from .serializers import DocumentReadSerializer

logger = logging.getLogger('gen.fsrl')

SACME_LABEL = 'Self-Assessed CME'

class EntryTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntryType
        fields = ('id', 'name','description')


class SponsorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sponsor
        fields = ('id', 'abbrev', 'name', 'logo_url')

# Offer is read-only because offers are created by the plugin server.
# A separate serializer exists to redeem the offer (and create br-cme entry in the user's feed).
class OrbitCmeOfferSerializer(serializers.ModelSerializer):
    userId = serializers.IntegerField(source='user.id', read_only=True)
    credits = serializers.DecimalField(max_digits=5, decimal_places=2, coerce_to_string=False, read_only=True)
    sponsor = serializers.PrimaryKeyRelatedField(read_only=True)
    url = serializers.StringRelatedField(read_only=True)
    pageTitle = serializers.CharField(source='url.page_title', max_length=500, read_only=True, default='')
    logo_url = serializers.URLField(source='sponsor.logo_url', max_length=1000, read_only=True, default='')
    cmeTags = serializers.PrimaryKeyRelatedField(source='tags', many=True, read_only=True)

    class Meta:
        model = OrbitCmeOffer
        fields = (
            'id',
            'userId',
            'activityDate',
            'url',
            'pageTitle',
            'suggestedDescr',
            'expireDate',
            'credits',
            'sponsor',
            'logo_url',
            'cmeTags'
        )
        read_only_fields = fields


# intended to be used by SerializerMethodField on EntrySerializer
class NotificationSubSerializer(serializers.ModelSerializer):
    expireDate = serializers.ReadOnlyField()
    class Meta:
        model = Notification
        fields = (
            'expireDate',
        )

# intended to be used by SerializerMethodField on EntrySerializer
class SRCmeSubSerializer(serializers.ModelSerializer):
    credits = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False)
    class Meta:
        model = SRCme
        fields = (
            'credits',
        )

# intended to be used by SerializerMethodField on EntrySerializer
class BRCmeSubSerializer(serializers.ModelSerializer):
    offer = serializers.ReadOnlyField(source='offerId')
    credits = serializers.DecimalField(max_digits=5, decimal_places=2, coerce_to_string=False, read_only=True)

    class Meta:
        model = BrowserCme
        fields = (
            'offer',
            'credits',
            'url',
            'pageTitle',
            'planEffect',
            'planText',
            'competence',
            'performance',
            'commercialBias',
            'commercialBiasText'
        )
        read_only_fields = fields

# intended to be used by SerializerMethodField on EntrySerializer
class StoryCmeSubSerializer(serializers.ModelSerializer):
    story = serializers.PrimaryKeyRelatedField(read_only=True)
    credits = serializers.DecimalField(max_digits=5, decimal_places=2, coerce_to_string=False, read_only=True)
    url = serializers.ReadOnlyField()
    title = serializers.ReadOnlyField()

    class Meta:
        model = StoryCme
        fields = (
            'story',
            'credits',
            'url',
            'title'
        )



class CreateSRCmeOutSerializer(serializers.ModelSerializer):
    """Serializer for the response returned for create srcme entry"""
    documents = DocumentReadSerializer(many=True, required=False)

    class Meta:
        model = Entry
        fields = (
            'id',
            'documents',
            'created',
            'success'
        )
    success = serializers.SerializerMethodField()

    def get_success(self, obj):
        return True

class UpdateSRCmeOutSerializer(serializers.ModelSerializer):
    """Serializer for the response returned for update srcme entry"""
    documents = DocumentReadSerializer(many=True, required=False)

    class Meta:
        model = Entry
        fields = (
            'id',
            'documents',
            'modified',
            'success'
        )
    success = serializers.SerializerMethodField()

    def get_success(self, obj):
        return True

class EntryReadSerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source='user.id', read_only=True)
    entryTypeId = serializers.PrimaryKeyRelatedField(source='entryType.id', read_only=True)
    entryType = serializers.StringRelatedField(read_only=True)
    sponsor = serializers.PrimaryKeyRelatedField(read_only=True)
    logo_url = serializers.URLField(source='sponsor.logo_url', max_length=1000, read_only=True, default='')
    tags = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    documents = DocumentReadSerializer(many=True, required=False)
    creditType = serializers.ReadOnlyField(source='ama_pra_catg')
    extra = serializers.SerializerMethodField()

    def get_extra(self, obj):
        etype = obj.entryType.name
        if etype == ENTRYTYPE_BRCME:
            s = BRCmeSubSerializer(obj.brcme)
        elif etype == ENTRYTYPE_SRCME:
            s = SRCmeSubSerializer(obj.srcme)
        elif etype == ENTRYTYPE_STORY_CME:
            s = StoryCmeSubSerializer(obj.storycme)
        else:
            s = NotificationSubSerializer(obj.notification)
        return s.data  # <class 'rest_framework.utils.serializer_helpers.ReturnDict'>

    class Meta:
        model = Entry
        fields = (
            'id',
            'user',
            'entryType',
            'entryTypeId',
            'activityDate',
            'description',
            'tags',
            'documents',
            'creditType',
            'extra',
            'sponsor',
            'logo_url',
            'created',
            'modified'
        )
        read_only_fields = fields

# Serializer for Create brcme entry
class BRCmeCreateSerializer(serializers.Serializer):
    id = serializers.IntegerField(label='ID', read_only=True)
    description = serializers.CharField(max_length=500)
    planEffect = serializers.IntegerField(min_value=0, max_value=1)
    competence = serializers.IntegerField(min_value=0, max_value=2, allow_null=True)
    performance = serializers.IntegerField(min_value=0, max_value=2, allow_null=True)
    commercialBias = serializers.IntegerField(min_value=0, max_value=2)
    planText = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    commercialBiasText = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    offerId = serializers.PrimaryKeyRelatedField(
        queryset=OrbitCmeOffer.objects.filter(redeemed=False)
    )
    tags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.all(),
        many=True,
        required=False
    )

    class Meta:
        fields = (
            'id',
            'offerId',
            'description',
            'planEffect',
            'planText',
            'competence',
            'performance',
            'commercialBias',
            'commercialBiasText',
            'tags'
        )

    def create(self, validated_data):
        """Create parent Entry and BrowserCme instances.
        Note: this expects the following keys in validated_data:
            user: User instance
        """
        etype = EntryType.objects.get(name=ENTRYTYPE_BRCME)
        offer = validated_data['offerId']
        user=validated_data.get('user')
        planText = validated_data.get('planText')
        if planText is None:
            planText = ''
        commercialBiasText = validated_data.get('commercialBiasText')
        if commercialBiasText is None:
            commercialBiasText = ''
        commercialBias = validated_data.get('commercialBias')
        competence = validated_data.get('competence')
        if competence is None:
            competence = BrowserCme.objects.randResponse()
        performance = validated_data.get('performance')
        if performance is None:
            performance = BrowserCme.objects.randResponse()
        planEffect = validated_data.get('planEffect')
        if planEffect:
            if not planText:
                planText = BrowserCme.objects.getDefaultPlanText(user)
        else:
            planEffect, planText = BrowserCme.objects.randPlanChange(user)
        entry = Entry.objects.create(
            entryType=etype,
            sponsor=offer.sponsor,
            activityDate=offer.activityDate,
            description=validated_data.get('description'),
            ama_pra_catg=Entry.CREDIT_CATEGORY_1,
            user=user
        )
        # associate tags with saved entry
        tag_ids = validated_data.get('tags', [])
        if tag_ids:
            entry.tags.set(tag_ids)
        # Using parent entry, create BrowserCme instance
        aurl = offer.url # AllowedUrl instance
        instance = BrowserCme.objects.create(
            entry=entry,
            offerId=offer.pk,
            purpose=0, # deprecated field
            competence=competence,
            performance=performance,
            planEffect=planEffect,
            planText=planText,
            commercialBias=commercialBias,
            commercialBiasText=commercialBiasText,
            url=aurl.url,
            pageTitle=aurl.page_title,
            credits=offer.credits
        )
        # set redeemed flag on offer
        offer.redeemed = True
        offer.save()
        # remove url from recommended aurls for user if exist
        qset = user.recaurls.filter(url=aurl)
        if qset.exists():
            qset.delete()
        # update usergoals
        for tag in entry.tags.all():
            qs = user.usergoals.select_related('goal').filter(cmeTag=tag)
            if qs.exists():
                ug = qs[0]
                ug.handleRedeemOffer()
        return instance

# Serializer for Update BrowserCme entry
class BRCmeUpdateSerializer(serializers.Serializer):
    id = serializers.IntegerField(label='ID', read_only=True)
    description = serializers.CharField(max_length=500)
    planEffect = serializers.IntegerField(min_value=0, max_value=1)
    competence = serializers.IntegerField(min_value=0, max_value=2)
    performance = serializers.IntegerField(min_value=0, max_value=2)
    commercialBias = serializers.IntegerField(min_value=0, max_value=2)
    planText = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    commercialBiasText = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    tags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.all(),
        many=True,
        required=False
    )

    class Meta:
        fields = (
            'id',
            'description',
            'purpose',
            'planEffect',
            'planText',
            'competence',
            'performance',
            'commercialBias',
            'commercialBiasText',
            'tags'
        )

    def update(self, instance, validated_data):
        entry = instance.entry
        user = entry.user
        entry.description = validated_data.get('description', entry.description)
        entry.save() # updates modified timestamp
        # if tags key is present: replace old with new (wholesale)
        if 'tags' in validated_data:
            vtags = validated_data['tags']
            newTags = set(vtags)
            curTags = set(entry.tags.all())
            newlyAdded = newTags.difference(curTags)
            delTags = curTags.difference(newTags)
            if vtags:
                entry.tags.set(vtags)
            else:
                entry.tags.set([])
            for tag in newlyAdded:
                qs = user.usergoals.select_related('goal').filter(cmeTag=tag)
                if qs.exists():
                    ug = qs[0]
                    ug.handleRedeemOffer()
            for tag in delTags:
                qs = user.usergoals.select_related('goal').filter(cmeTag=tag)
                if qs.exists():
                    ug = qs[0]
                    ug.recompute() # just recompute
        instance.competence = validated_data.get('competence', instance.competence)
        instance.performance = validated_data.get('performance', instance.performance)
        instance.commercialBias = validated_data.get('commercialBias', instance.commercialBias)
        instance.planEffect = validated_data.get('planEffect', instance.planEffect)
        if 'planText' in validated_data:
            planText=validated_data.get('planText')
            if planText is None:
                planText = ''
            instance.planText = planText
        if 'commercialBiasText' in validated_data:
            commercialBiasText=validated_data.get('commercialBiasText')
            if commercialBiasText is None:
                commercialBiasText = ''
            instance.commercialBiasText = commercialBiasText
        instance.save()
        return instance


# Serializer for the combined fields of Entry + SRCme
# Used for both create and update
class SRCmeFormSerializer(serializers.Serializer):
    id = serializers.IntegerField(label='ID', read_only=True)
    activityDate = serializers.DateTimeField()
    description = serializers.CharField(max_length=500)
    creditType = serializers.CharField(max_length=2)
    credits = serializers.DecimalField(max_digits=5, decimal_places=2, coerce_to_string=False)
    tags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.all(),
        many=True,
        required=False
    )
    documents = serializers.PrimaryKeyRelatedField(
        queryset=Document.objects.all(),
        many=True,
        required=False
    )

    class Meta:
        fields = (
            'id',
            'activityDate',
            'description',
            'creditType',
            'credits',
            'tags',
            'documents'
        )

    def create(self, validated_data):
        """Create parent Entry and SRCme instances.
        It expects that View has passed the following keys to the serializer.save
        method, which then appear in validated_data:
            user: User instance
        """
        etype = EntryType.objects.get(name=ENTRYTYPE_SRCME)
        user = validated_data['user']
        creditType = validated_data.get('creditType', Entry.CREDIT_CATEGORY_1)
        entry = Entry(
            entryType=etype,
            activityDate=validated_data.get('activityDate'),
            description=validated_data.get('description'),
            ama_pra_catg=creditType,
            user=user
        )
        entry.save()
        # associate tags with saved entry
        tags = validated_data.get('tags', [])
        if tags:
            entry.tags.set(tags)
        # associate documents with saved entry
        docs = validated_data.get('documents', [])
        if docs:
            entry.documents.set(docs)
        # Using parent entry, create SRCme instance
        instance = SRCme.objects.create(
            entry=entry,
            credits=validated_data.get('credits')
        )
        # recompute usergoals
        for tag in entry.tags.all():
            qs = user.usergoals.select_related('goal').filter(cmeTag=tag)
            if qs.exists():
                ug = qs[0]
                logger.info('srcme: recompute UserGoal {0} for tag: {0.cmeTag}'.format(ug))
                ug.recompute()
        return instance

    def update(self, instance, validated_data):
        #entry = Entry.objects.get(pk=instance.pk)
        entry = instance.entry
        user = entry.user
        entry.activityDate = validated_data.get('activityDate', entry.activityDate)
        entry.description = validated_data.get('description', entry.description)
        entry.ama_pra_catg = validated_data.get('creditType', entry.ama_pra_catg)
        entry.save()  # updates modified timestamp
        # if tags key is present: replace old with new (wholesale)
        if 'tags' in validated_data:
            vtags = validated_data['tags']
            newTags = set(vtags)
            curTags = set(entry.tags.all())
            newlyAdded = newTags.difference(curTags)
            delTags = curTags.difference(newTags)
            updTags = newlyAdded.union(delTags)
            if vtags:
                entry.tags.set(vtags)
            else:
                entry.tags.set([])
            for tag in updTags:
                qs = user.usergoals.select_related('goal').filter(cmeTag=tag)
                if qs.exists():
                    ug = qs[0]
                    ug.recompute()
        if 'documents' in validated_data:
            currentDocs = entry.documents.all()
            current_doc_ids = set([m.pk for m in currentDocs])
            #logger.debug(current_doc_ids)
            docs = validated_data['documents']
            doc_ids = [m.pk for m in docs]
            #logger.debug(doc_ids)
            if doc_ids:
                # are there any docs to delete
                delete_doc_ids = current_doc_ids.difference(set(doc_ids))
                for docid in delete_doc_ids:
                    m = Document.objects.get(pk=docid)
                    logger.debug('updateSRCme: delete document {0}'.format(m))
                    m.document.delete()
                    m.delete()
                # associate entry with docs
                entry.documents.set(doc_ids)
            else:
                entry.documents.set([])
        instance.credits = validated_data.get('credits', instance.credits)
        instance.save()
        return instance


class StorySerializer(serializers.ModelSerializer):
    sponsor = serializers.PrimaryKeyRelatedField(read_only=True)
    logo_url = serializers.URLField(source='sponsor.logo_url', max_length=1000, read_only=True, default='')
    displayLabel = serializers.SerializerMethodField()

    def get_displayLabel(self, obj):
        return SACME_LABEL

    class Meta:
        model = Story
        fields = (
            'id',
            'title',
            'description',
            'startDate',
            'expireDate',
            'launch_url',
            'sponsor',
            'logo_url',
            'displayLabel'
        )
