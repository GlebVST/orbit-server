"""Models managed by the plugin_server project"""
from __future__ import unicode_literals
import logging
from datetime import datetime, timedelta
import pytz
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import Q, Subquery, Sum
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.contrib.postgres.fields import JSONField

from common.appconstants import MAX_URL_LENGTH
from .base import (
    CmeTag,
    ProfileCmetag,
    PracticeSpecialty,
    EligibleSite,
    Organization
)
from .feed import ARTICLE_CREDIT, BrowserCme, Sponsor
from .subscription import UserSubscription

logger = logging.getLogger('gen.models')

OFFER_LOOKBACK_DAYS = 365*3

class Adblocker(models.Model):
    name = models.CharField(max_length=60, unique=True)
    ios = models.BooleanField(default=False,
        help_text='Check box if this entry is for the ios app')
    file_url = models.URLField(max_length=1000, blank=True, default='',
        help_text='For ios app entry: S3 URL of the adblock file. Upload to the adblocker folder in the orbitcme-dev and orbitcme-prod S3 bucket. Filename should be unique.')
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_adblocker'
        ordering = ('-created',)

    def __str__(self):
        return self.name

class ProxyPattern(models.Model):
    proxyname = models.CharField(max_length=100, unique=True,
        help_text='proxy part of netloc only. Example: offcampus.lib.washington.edu')
    delimiter = models.CharField(max_length=10,
        help_text='delimiter used in the domain name. Example: -')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'trackers_proxypattern'
        ordering = ['proxyname',]

    def __str__(self):
        return self.proxyname


class AllowedHost(models.Model):
    id = models.AutoField(primary_key=True)
    hostname = models.CharField(max_length=100, unique=True, help_text='netloc only. No scheme')
    main_host = models.ForeignKey('self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text='Canonical host for which this host is a proxy')
    description = models.CharField(max_length=500, blank=True, default='')
    accept_query_keys = models.TextField(blank=True, default='', help_text='accepted keys in url query')
    has_paywall = models.BooleanField(blank=True, default=False, help_text='True if full text is behind paywall')
    allow_page_download = models.BooleanField(blank=True, default=False,
            help_text='False if pages under this host should not be downloaded')
    is_secure = models.BooleanField(blank=True, default=False, help_text='True if site uses a secure connection (https).')
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_allowedhost'

    def __str__(self):
        return self.hostname

class ArticleType(models.Model):
    id = models.AutoField(primary_key=True)
    eligible_site = models.ForeignKey(EligibleSite,
        on_delete=models.CASCADE,
        related_name='articletypes',
        db_index=True)
    name = models.CharField(max_length=40, help_text='e.g. Abstract')
    is_allowed = models.BooleanField(default=False, help_text='Check box if this ArticleType is allowed')
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_articletype'
        unique_together = ('eligible_site', 'name')
        ordering = ('-is_allowed', 'name')

    def __str__(self):
        return '{0.eligible_site}|{0.name}|{0.is_allowed}'.format(self)


class HostPattern(models.Model):
    id = models.AutoField(primary_key=True)
    host = models.ForeignKey(AllowedHost,
        on_delete=models.CASCADE,
        related_name='hostpatterns',
        db_index=True
    )
    eligible_site = models.ForeignKey(EligibleSite,
        on_delete=models.CASCADE,
        related_name='hostpatterns',
        db_index=True)
    path_contains = models.CharField(max_length=200, blank=True, default='',
        help_text='If given, url path part must contain this term. No trailing slash.')
    path_reject = models.CharField(max_length=200, blank=True, default='',
        help_text='If given, url path part must not contain this term. No trailing slash.')
    pattern_key = models.CharField(max_length=40, help_text='valid key in URL_PATTERNS dict')
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_hostpattern'
        ordering = ['host','eligible_site','pattern_key','path_contains']

    def __str__(self):
        return '{0.host}|{0.eligible_site.domain_name}|{0.pattern_key}|pc:{0.path_contains}|pr: {0.path_reject}'.format(self)

class AllowedUrl(models.Model):
    id = models.AutoField(primary_key=True)
    host = models.ForeignKey(AllowedHost,
        on_delete=models.CASCADE,
        related_name='aurls',
        db_index=True
    )
    eligible_site = models.ForeignKey(EligibleSite,
        on_delete=models.CASCADE,
        related_name='aurls',
        db_index=True)
    url = models.URLField(max_length=MAX_URL_LENGTH, unique=True)
    valid = models.BooleanField(default=True)
    page_title = models.TextField(blank=True, default='')
    metadata = models.TextField(blank=True, default='')
    diff_diagnosis = models.TextField(blank=True, default='')
    doi = models.CharField(max_length=100, blank=True,
        help_text='Digital Object Identifier e.g. 10.1371/journal.pmed.1002234')
    pmid = models.CharField(max_length=20, blank=True, help_text='PubMed Identifier (PMID)')
    pmcid = models.CharField(max_length=20, blank=True, help_text='PubMedCentral Identifier (PMCID)')
    set_id = models.CharField(max_length=500, blank=True,
        help_text='Used to group a set of URLs that point to the same resource')
    content_type = models.CharField(max_length=100, blank=True, help_text='page content_type')
    cmeTags = models.ManyToManyField(CmeTag, blank=True, related_name='aurls')
    pubDate = models.DateField(null=True, blank=True, help_text='article publication date')
    numOffers = models.IntegerField(default=1, help_text='cached number of redeemed offers')
    studyTopics = models.ManyToManyField('StudyTopic',
        blank=True,
        help_text='Study Topics for the article',
        related_name='aurls')
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_allowedurl'

    def __str__(self):
        return self.url

    def cleanPageTitle(self):
        esite = self.eligible_site
        title_suffix = esite.page_title_suffix
        if title_suffix:
            return self.page_title.replace(title_suffix, '')
        return self.page_title

class RejectedUrl(models.Model):
    id = models.AutoField(primary_key=True)
    host = models.ForeignKey(AllowedHost,
        on_delete=models.CASCADE,
        db_index=True)
    url = models.URLField(max_length=MAX_URL_LENGTH, unique=True)
    starts_with = models.BooleanField(default=False, help_text='True if any sub URL under it should also be rejected')
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_rejectedurl'

    def __str__(self):
        return self.url

# ActivitySet is a collection of 1+ ActivityLogs for a (user, url)
class ActivitySet(models.Model):
    MAX_EXTENT_SECONDS = 60*60*8 # max time extent of an activity set
    TOTAL_SECONDS_THRESHOLD = 20
    ENGAGED_SECONDS_THRESHOLD = 1
    # fields
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activitysets')
    url = models.ForeignKey(AllowedUrl, on_delete=models.CASCADE, related_name='activitysets')
    total_tracking_seconds = models.PositiveIntegerField(help_text='Sum of x_tracking_seconds over a set of logs')
    computed_value = models.DecimalField(max_digits=9, decimal_places=2, help_text='Total number of engaged seconds')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'trackers_activityset'

    def __str__(self):
        return '{0}/{1} on {2}'.format(self.user, self.url, self.created)

    def meetsThreshold(self):
        """Returns True if cumulative values meet or exceed threshold"""
        return self.total_tracking_seconds >= ActivitySet.TOTAL_SECONDS_THRESHOLD and self.computed_value >= ActivitySet.ENGAGED_SECONDS_THRESHOLD

# ActivityLog is a log sent by the plugin client upon page load and every x_tracking_seconds while user is on the page
class ActivityLog(models.Model):
    id = models.AutoField(primary_key=True)
    activity_set = models.ForeignKey(ActivitySet, on_delete=models.CASCADE, related_name='logs')
    valid = models.BooleanField(default=True)
    x_tracking_seconds = models.PositiveIntegerField()
    browser_extensions = JSONField(blank=True)
    # user stats recorded by the plugin
    num_highlight = models.PositiveIntegerField(default=0)
    num_mouse_click = models.PositiveIntegerField(default=0)
    num_mouse_move = models.PositiveIntegerField(default=0)
    num_start_scroll = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_activitylog'

    def __str__(self):
        return '{0.activity_set} on {0.created}'.format(self)

    def isEngaged(self):
        return self.valid and any([self.num_highlight + self.num_mouse_click + self.num_mouse_move + self.num_start_scroll])

# Requests made by plugin users for new AllowedUrl entries
class RequestedUrl(models.Model):
    id = models.AutoField(primary_key=True)
    url = models.URLField(max_length=MAX_URL_LENGTH, unique=True)
    valid = models.NullBooleanField(default=None)
    users = models.ManyToManyField(User, through='WhitelistRequest')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'trackers_requestedurl'

    def __str__(self):
        return self.url

# User-RequestedUrl association
class WhitelistRequest(models.Model):
    id = models.AutoField(primary_key=True)
    req_url = models.ForeignKey(RequestedUrl, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'trackers_whitelistrequest'
        unique_together = ('req_url', 'user')

    def __str__(self):
        return '{0}-{1}'.format(self.user, self.req_url.url)

class OrbitCmeOfferManager(models.Manager):
    def makeOffer(self, aurl, user, activityDate, expireDate):
        esite = aurl.eligible_site
        with transaction.atomic():
            offer = OrbitCmeOffer.objects.create(
                user=user,
                eligible_site=esite,
                url=aurl,
                activityDate=activityDate,
                expireDate=expireDate,
                suggestedDescr=aurl.page_title,
                credits=ARTICLE_CREDIT,
                sponsor_id=1
            )
            offer.assignCmeTags()
        return offer

    def makeDebugOffer(self, aurl, user):
        now = timezone.now()
        activityDate = now + timedelta(seconds=20)
        expireDate = now + timedelta(days=365)
        return self.makeOffer(aurl, user, activityDate, expireDate)

    def makeWelcomeOffer(self, user):
        aurl = None
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        # Need to be sure that welcome article exists in this db instance
        try:
            if user_subs and user_subs.plan.welcome_offer_url:
                plan = user_subs.plan
                urlpath = plan.welcome_offer_url
            else:
                urlpath = settings.WELCOME_ARTICLE_URL
            aurl = AllowedUrl.objects.get(url=urlpath)
        except AllowedUrl.DoesNotExist:
            logger.error("makeWelcomeOffer: URL {0} does not exist in AllowedUrl".format(urlpath))
            return None
        now = timezone.now()
        activityDate = now - timedelta(seconds=10)
        expireDate = now + timedelta(days=365)
        return self.makeOffer(aurl, user, activityDate, expireDate)

    def sumCredits(self, user, startDate, endDate):
        """Compute credit sum over the given time period for the given user for:
            (redeemed offers, valid, non-expired unredeemed offers)
        Returns: tuple (credit_sum_redeemed:float, credit_sum_unredeemed:float)
        """
        now = timezone.now()
        # redeemed offers - no filter on expireDate
        fkw1 = {
            'redeemed': True,
            'valid': True,
            'user': user,
            'activityDate__gte': startDate,
            'activityDate__lte': endDate,
        }
        qs_redeemed = self.model.objects.filter(**fkw1)
        # unredeemed offers - filter on expireDate
        fkw2 = {
            'redeemed': False,
            'valid': True,
            'user': user,
            'activityDate__gte': startDate,
            'activityDate__lte': endDate,
            'expireDate__gt': now
        }
        qs_unredeemed = self.model.objects.filter(**fkw2)
        total_redeemed = qs_redeemed.aggregate(credit_sum=Sum('credits'))
        credit_sum_redeemed = total_redeemed['credit_sum'] or 0
        if credit_sum_redeemed:
            credit_sum_redeemed = float(credit_sum_redeemed)
        total_unredeemed = qs_unredeemed.aggregate(credit_sum=Sum('credits'))
        credit_sum_unredeemed = total_unredeemed['credit_sum'] or 0
        if credit_sum_unredeemed:
            credit_sum_unredeemed = float(credit_sum_unredeemed)
        return (credit_sum_redeemed, credit_sum_unredeemed)

    def sumArticlesRead(self, user, startDate, endDate):
        """Calls sumCredits for the given args
        Returns: tuple (
            numArticlesRead:int sum(redeemed + unredeemed)/ARTICLE_CREDIT,
            creditsRedeemed: float
        )
        """
        creditsTuple = self.sumCredits(user, startDate, endDate)
        creditsRedeemed, creditsUnredeemed = (float(cred) for cred in creditsTuple)
        creditsEarned = creditsRedeemed + creditsUnredeemed
        numArticlesRead = int(creditsEarned/ARTICLE_CREDIT)
        return (numArticlesRead, creditsRedeemed)

    def getRedeemedOffersForUser(self, user):
        """Helper method for updateRecs
        Returns tuple (
            offers_blank_setid: query for redeemed offers w. blank setid
            offers_setid: queryset for redeemed offers w. non-blank setid)
        """
        # offers redeemed by user since OFFER_LOOKBACK_DAYS.
        now = timezone.now()
        startdate = now - timedelta(days=OFFER_LOOKBACK_DAYS)
        filter_kwargs = dict(
            user=user,
            redeemed=True,
            valid=True,
            activityDate__gte=startdate,
        )
        Q_setid = Q(url__set_id='')
        # redeemed offers whose aurl.set_id is blank
        offers_blank_setid = OrbitCmeOffer.objects.select_related('url').filter(Q_setid, **filter_kwargs)
        # redeemed offers whose aurl.set_id is not blank (e.g. abs/pdf versions of the same article have the same set_id)
        offers_setid = OrbitCmeOffer.objects.select_related('url').filter(~Q_setid, **filter_kwargs)
        return (offers_blank_setid, offers_setid)

    def addTagToUserOffers(self, user, add_tag):
        """Used by ProfileUpdateSerializer to add a new tag to existing offers
            for the given user.
        Args:
            user: User instance
            add_tag: CmeTag instance
        Returns: tuple (num_redeemed_updated:int, num_unredeemed_updated:int)
        """
        num_upd_redeemed = 0
        num_upd_unredeemed = 0
        # Get unredeemed offers that don't already have add_tag as a pre-selected tag
        qs_unredeemed = OrbitCmeOffer.objects \
            .filter(user=user, valid=True, redeemed=False) \
            .exclude(selectedTags=add_tag) \
            .order_by('pk')
        num_upd_unredeemed = qs_unredeemed.count()
        for offer in qs_unredeemed:
            offer.selectedTags.add(add_tag)
            offer.tags.remove(add_tag) # remove from the un-selected pool if exists (else it does not do anything)
        # Get redeemed offers that don't already have add_tag as a pre-selected tag
        qs_redeemed = OrbitCmeOffer.objects \
            .filter(user=user, valid=True, redeemed=True) \
            .exclude(selectedTags=add_tag) \
            .order_by('pk')
        num_upd_redeemed = qs_redeemed.count()
        for offer in qs_redeemed:
            offer.selectedTags.add(add_tag)
            offer.tags.remove(add_tag) # remove from the un-selected pool if exists (else it does not do anything)
            # update the associated brcme Entry
            try:
                brcme = BrowserCme.objects.get(offerId=offer.pk)
            except BrowserCme.DoesNotExist:
                logger.warning('addTagToUserOffers: no BrowerCme Entry found for offerid {0.pk}'.format(offer))
            else:
                entry = brcme.entry
                entry.tags.add(add_tag)
                logger.info('addTagToUserOffers: add {0} to BrowerCme Entry {1.pk}'.format(add_tag, entry))
        return (num_upd_redeemed, num_upd_unredeemed)

# OrbitCmeOffer
# An offer for a user is generated based on the user's plugin activity.
class OrbitCmeOffer(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='new_offers',
        db_index=True
    )
    sponsor = models.ForeignKey(Sponsor,
        on_delete=models.PROTECT,
        related_name='new_offers',
        db_index=True
    )
    eligible_site = models.ForeignKey(EligibleSite,
        on_delete=models.PROTECT,
        related_name='new_offers',
        db_index=True)
    url = models.ForeignKey(AllowedUrl,
        on_delete=models.PROTECT,
        related_name='new_offers',
        db_index=True)
    activityDate = models.DateTimeField()
    suggestedDescr = models.TextField(blank=True, default='')
    expireDate = models.DateTimeField()
    redeemed = models.BooleanField(default=False)
    valid = models.BooleanField(default=True)
    requireUserTag = models.BooleanField(default=False,
        help_text='If True, user must select a non-SACME/MOC tag for the article because the system could not pre-select one.')
    credits = models.DecimalField(max_digits=5, decimal_places=2,
        help_text='CME credits to be awarded upon redemption')
    tags = models.ManyToManyField(CmeTag,
        blank=True,
        related_name='offers',
        help_text='Recommended/suggested tags'
    )
    selectedTags = models.ManyToManyField(CmeTag,
        blank=True,
        related_name='seloffers',
        help_text='Pre-selected tags in the redeem offer form'
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = OrbitCmeOfferManager()

    class Meta:
        managed = False
        db_table = 'trackers_orbitcmeoffer'
        verbose_name_plural = 'OrbitCME Offers'

    def __str__(self):
        return self.url.url

    def formatTags(self):
        seltags = [t.name for t in self.selectedTags.all()]
        rectags = [t.name for t in self.tags.all()]
        return ",".join(seltags) + '|' + ", ".join(tags)
    formatTags.short_description = "Tags"

    def assignCmeTags(self):
        """Assign selected tags, and other recommended tags based on the
        intersection of the user's profile tags with tags from url/esite.
        """
        aurl = self.url
        esite = self.eligible_site
        profile = self.user.profile
        specnames = [ps.name for ps in profile.specialties.all()]
        profile_specs = set(specnames)
        # user's active profile cmetags
        pcts = ProfileCmetag.objects.filter(profile=profile, is_active=True).order_by('pk')
        pct_tags = [pct.tag for pct in pcts]
        if not pct_tags:
            logger.warning('assignCmeTags Offer {0.pk}: user {0.user} has no profile tags.'.format(self))
            return
        # partition into pct_spectags, pct_condtags, and pct_othertags
        pct_spectags = set([]) # specialty name tags
        pct_condtags = set([]) # conditional tags (sacme/moc)
        pct_othertags = set([]) # other
        for tag in pct_tags:
            if tag.name in profile_specs:
                pct_spectags.add(tag)
            elif tag.exemptFrom1Tag: # sacme/moc
                pct_condtags.add(tag)
            else:
                pct_othertags.add(tag)

        # If condtags exist: they are pre-selected
        for t in pct_condtags:
            self.selectedTags.add(t)

        # 1. Intersection of UrlTagFreq tags with pct_othertags
        urlUserTags = [] # Exclude pct_spectags in order to give more weight to pct_othertags
        if pct_othertags:
            qs = UrlTagFreq.objects \
                .filter(url=aurl, tag__in=pct_othertags, numOffers__gte=MIN_VOTE_FOR_REC) \
                .order_by('-numOffers','id') # tag has met or exceeded the MIN_VOTE count
            for utf in qs:
                urlUserTags.append(utf.tag)
        # Url default tags (usually present in UrlTagFreq, but in some cases, a default tag may have been manually assigned)
        uut_set = set(urlUserTags)
        for t in aurl.cmeTags.all():
            if t in pct_othertags and t not in uut_set: # aurl.tag is contained in othertags and not already in set
                urlUserTags.append(t)

        # 2. Intersection of esite spectags with profile_specs
        esite_specs = set([s.name for s in esite.specialties.all()])
        int_specs = profile_specs.intersection(esite_specs)
        specTags = CmeTag.objects.filter(name__in=int_specs).order_by('name')
        #
        # Determine selected tag from:
        #
        # 1: offer url matches a recommended article
        recaurls = self.user.recaurls.filter(url=aurl).order_by('id')
        if recaurls.exists():
            # Assign recaurl.cmeTag as pre-selected tag
            recaurl = recaurls[0]
            self.selectedTags.add(recaurl.cmeTag)
            logger.info('SelectedTag from recaurl {0}'.format(recaurl))
            # Add urlUserTags to recommendedTags
            for t in urlUserTags:
                if t != recaurl.cmeTag:
                    self.tags.add(t)
            # Add specTags to recommendedTags
            for t in specTags:
                if t != recaurl.cmeTag:
                    self.tags.add(t)
            return
        # 2. No recaurl. Use top tag from urlUserTags (tag with the most votes)
        if urlUserTags:
            selTag = urlUserTags.pop(0)
            self.selectedTags.add(selTag)
            logger.info('SelectedTag from urlUserTag {0} for offer {1.pk}'.format(selTag, self))
            # Add remaining urlUserTags to recommendedTags
            for t in urlUserTags:
                self.tags.add(t)
            # Add specTags to recommendedTags
            for t in specTags:
                if t != selTag:
                    self.tags.add(t)
            return
        # 3. No good assignment of pre-selected tag. User must explicitly select one.
        # 2020-05-26: Previously, we used to default to any of the user's specialty tags
        #  but this did not work for users who weren't aware that they needed to
        #  explicitly select a different tag for their own needs.
        self.requireUserTag = True
        self.save(update_fields=('requireUserTag',))

    def setTagsFromRedeem(self, tags):
        """Called by redeem offer serializer to sync offer.selectedTags with the given tags:
        Args:
            tags: CmeTag queryset from an entry
        """
        self.selectedTags.set(tags) # the actual selected tags


# OrbitCmeOffer stats per org
class OrbitCmeOfferAgg(models.Model):
    id = models.AutoField(primary_key=True)
    organization = models.ForeignKey(Organization,
        on_delete=models.CASCADE,
        db_index=True
    )
    day = models.DateField()
    offers = models.PositiveIntegerField(default=0,
        help_text='Number of offers generated for this day (counted from 00:00:00 UTC - 23:59:59 UTC)')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'trackers_orbitcmeofferagg'
        verbose_name_plural = 'OrbitCME Offer Stats'

    def __str__(self):
        return "{0.day}".format(self)

MIN_VOTE_FOR_REC = 5 # should match with value in defined in plugin_server
class UrlTagFreqManager(models.Manager):
    def getFromUrlTagFreq(self, tag, exclude_offers_blank_setid, exclude_offers_setid):
        """Get articles with the highest freq of the given tag and exclude already read.
        This only considers articles that have numOffers >= MIN_VOTE for the given tag (in order to improve quality of recommendations).
        Returns: UrlTagFreq queryset
        """
        fkwargs = {
            'tag': tag,
            'numOffers__gte': MIN_VOTE_FOR_REC, # voting mechanism
            'url__host__has_paywall': False,
            'url__host__main_host__isnull': True, # omit proxy hosts
        }
        Q_setid = Q(url__set_id='')
        base_qs = UrlTagFreq.objects.select_related('url__host')
        # urls with blank set_id
        qs_blank_setid = base_qs.filter(Q_setid, **fkwargs) \
            .exclude(url__in=Subquery(exclude_offers_blank_setid.values('url_id'))) \
            .order_by('-numOffers', 'pk')
        # offers with non-blank set_id
        qs_setid = base_qs.filter(~Q_setid, **fkwargs) \
            .exclude(url__set_id__in=Subquery(exclude_offers_setid.values('url__set_id').distinct())) \
            .order_by('-numOffers', 'pk')
        # union and order by numOffers desc
        qs = qs_blank_setid.union(qs_setid).order_by('-numOffers', 'pk')
        return qs

class UrlTagFreq(models.Model):
    id = models.AutoField(primary_key=True)
    url = models.ForeignKey(AllowedUrl, on_delete=models.CASCADE, related_name='urltagfreqs')
    tag = models.ForeignKey(CmeTag, on_delete=models.CASCADE, related_name='urltagfreqs')
    numOffers = models.PositiveIntegerField(default=MIN_VOTE_FOR_REC,
        help_text='Specify a number gte to {0} in order to make this a recommended article for this tag.'.format(MIN_VOTE_FOR_REC)
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = UrlTagFreqManager()

    class Meta:
        managed = False
        db_table = 'trackers_urltagfreq'
        unique_together = ('url','tag')
        verbose_name_plural = 'URL Tag Frequencies'

    def __str__(self):
        return "{0.tag}|{0.url}|{0.numOffers}".format(self)


class RecAllowedUrlManager(models.Manager):
    def createRecsForNewIndivUser(self, user, tag, num_recs):
        """This is intended for new users who have signed up on a plan that
        offers recommended articles for a given tag.
        Args:
            user: User
            tag: CmeTag
            num_recs: int
        """
        welcome_url = AllowedUrl.objects.get(url=settings.WELCOME_ARTICLE_URL)
        qs = UrlTagFreq.objects \
            .filter(tag=tag, numOffers__gte=MIN_VOTE_FOR_REC) \
            .exclude(url=welcome_url) \
            .order_by('-numOffers')
        num_created = 0
        for utf in qs[0:num_recs]:
            recaurl, created = self.model.objects.get_or_create(user=user, cmeTag=tag, url=utf.url)
            if created:
                num_created += 1
        return num_created

    def updateRecsForUser(self, user, tag, total_recs, do_full_refresh=False):
        """Maintain a list of upto total_recs recommended aurls for the given user and tag.
        Args:
            user: User instance
            tag: CmeTag instance
            total_recs: int
            do_full_refresh:bool If True: all old recs are deleted and replaced with new ones
                else, existing recs are retained and new ones added until total_recs is reached.
        Returns: int - number of recs created
        """
        max_recs = total_recs if total_recs > 0 else self.model.MAX_RECS_PER_USERTAG
        # existing recs for (user, tag)
        qs = user.recaurls.filter(cmeTag=tag)
        if qs.count():
            if do_full_refresh:
                qs.delete()
            else:
                max_recs -= qs.count()
        if max_recs <= 0:
            return
        profile = user.profile
        # exclude_offers redeemed by user since OFFER_LOOKBACK_DAYS. This is used as a subquery below
        exclude_offers_blank_setid, exclude_offers_setid = OrbitCmeOffer.objects.getRedeemedOffersForUser(user)
        urls = []
        qs_url = UrlTagFreq.objects.getFromUrlTagFreq(tag, exclude_offers_blank_setid, exclude_offers_setid)
        num_recs = 100 # limit queryset to top 100 entries
        data = qs_url[0:num_recs]
        urls.extend([m.url for m in data])
        # Finally: populate RecAllowedUrl from urls and as we iterate check that aurl is unique for this user
        num_created = 0
        for aurl in urls[0:max_recs]:
            # check if user already has a rec for this aurl (for any tag)
            qs = user.recaurls.filter(url=aurl)
            if qs.exists():
                continue
            m, created = RecAllowedUrl.objects.get_or_create(user=user, cmeTag=tag, url=aurl)
            if created:
                num_created += 1
        return num_created

class RecAllowedUrl(models.Model):
    MAX_RECS_PER_USERTAG = 20
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recaurls')
    url = models.ForeignKey(AllowedUrl, on_delete=models.CASCADE, related_name='recaurls')
    cmeTag = models.ForeignKey(CmeTag, on_delete=models.CASCADE, related_name='recaurls')
    offer = models.ForeignKey(OrbitCmeOffer, on_delete=models.CASCADE, null=True, blank=True, related_name='recaurls')
    objects = RecAllowedUrlManager()

    class Meta:
        managed = False
        db_table = 'trackers_recallowedurl'
        unique_together = ('user','url','cmeTag')

    def __str__(self):
        return '{0.user}|{0.cmeTag}|{0.url}'.format(self)

#
# Models for study topics (used for residency users)
#
class StudyTopicGroup(models.Model):
    id = models.AutoField(primary_key=True)
    groupID = models.PositiveIntegerField(unique=True,
        help_text='User-assigned numerical ID for this group. Must be unique.')
    name = models.CharField(max_length=60, unique=True,
        help_text='Group name. Must be unique')
    description = models.CharField(max_length=100, blank=True, default='',
        help_text='Optional description')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'trackers_studytopicgroup'

    def __str__(self):
        return self.name

class StudyTopic(models.Model):
    id = models.AutoField(primary_key=True)
    topicID = models.PositiveIntegerField(unique=True,
        help_text='User-assigned numerical ID for this topic. Must be unique.')
    name= models.CharField(max_length=60,
        help_text='Topic short name. The tuple (specialty, name) must be unique.')
    long_name= models.CharField(max_length=80,
        help_text='Topic long name')
    alternate_name= models.CharField(max_length=60, blank=True, default='',
        help_text='Alternate name (e.g. from radiopaedia). Used to map from a different source.')
    specialty = models.ForeignKey(PracticeSpecialty,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='studytopics',
    )
    group = models.ForeignKey(StudyTopicGroup,
        on_delete=models.SET_NULL,
        db_index=True,
        null=True,
        blank=True,
        related_name='studytopics',
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'trackers_studytopic'
        unique_together = ('specialty','name')

    def __str__(self):
        return self.name
#
# Models for related article recommendation
#
class GArticleSearch(models.Model):
    SEARCH_TERM_MAX_LENGTH = 500
    id = models.AutoField(primary_key=True)
    search_term = models.CharField(max_length=SEARCH_TERM_MAX_LENGTH, help_text='search term passed to the query')
    gsearchengid = models.CharField(max_length=50, help_text='Google search engineid passed to the query')
    searchDate = models.DateTimeField(null=True, blank=True, help_text='timestamp of the search')
    specialties = models.ManyToManyField(PracticeSpecialty,
        blank=True,
        related_name='garticlesearches')
    articles = models.ManyToManyField(AllowedUrl,
        blank=True,
        help_text='Articles assigned to this search entry',
        related_name='garticlesearches')
    reference_article= models.ForeignKey(AllowedUrl,
        on_delete=models.SET_NULL,
        db_index=True,
        null=True,
        blank=True,
        related_name='ref_garticlesearches',
        help_text='The Reference Article determines which ddx/studytopics are used for the articles assigned to this entry. By default, the ReferenceUrl is set from the top search result that was done using the internalSearchEngineid of a specialty.'
    )
    results = JSONField(blank=True)
    processed_results = JSONField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_garticlesearch'
        unique_together = ('search_term','gsearchengid')
        verbose_name = 'Related Article Search'
        verbose_name_plural = 'Related Article Searches'

    def __str__(self):
        return self.search_term


class Topic(models.Model):
    id = models.AutoField(primary_key=True)
    name= models.CharField(max_length=300, help_text='Topic name')
    lcname= models.CharField(max_length=300, help_text='Topic name - all lowercased')
    specialty = models.ForeignKey(PracticeSpecialty,
        on_delete=models.SET_NULL,
        db_index=True,
        null=True,
        blank=True,
        related_name='topics',
    )
    source_aurl= models.ForeignKey(AllowedUrl,
        on_delete=models.SET_NULL,
        db_index=True,
        null=True,
        blank=True,
        related_name='topics',
        help_text='AllowedUrl source of this topic'
    )
    diffdiag_topics = models.ManyToManyField('self',
        related_name='diffdiag_parents',
        symmetrical=False,
        through='DiffDiagnosis',
        blank=True,
        help_text='Related topics listed under Differential Diagnosis for this topic'
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'trackers_topic'
        unique_together = ('specialty', 'lcname')
        ordering = ('specialty', 'name')

    def __str__(self):
        return "{0.name}|{0.specialty}".format(self)

class DiffDiagnosis(models.Model):
    id = models.AutoField(primary_key=True)
    from_topic = models.ForeignKey(Topic, related_name='from_topics', on_delete=models.CASCADE, db_index=True)
    to_topic = models.ForeignKey(Topic, related_name='to_topics', on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'trackers_diffdiagnosis'
        unique_together = ('from_topic','to_topic')

    def __str__(self):
        return "{0.from_topic.name} to {0.to_topic.name}".format(self)
