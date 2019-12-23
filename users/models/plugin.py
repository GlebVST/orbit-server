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
    CMETAG_SACME,
    SACME_SPECIALTIES,
    CmeTag,
    ProfileCmetag,
    EligibleSite,
    Organization
)
from .feed import Sponsor, ARTICLE_CREDIT

logger = logging.getLogger('gen.models')

OFFER_LOOKBACK_DAYS = 365*3

@python_2_unicode_compatible
class AllowedHost(models.Model):
    id = models.AutoField(primary_key=True)
    hostname = models.CharField(max_length=100, unique=True, help_text='netloc only. No scheme')
    main_host = models.ForeignKey('self', null=True, blank=True, help_text='Main host for which this host is a proxy')
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

@python_2_unicode_compatible
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


@python_2_unicode_compatible
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

@python_2_unicode_compatible
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
    host = models.ForeignKey(AllowedHost, db_index=True)
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
@python_2_unicode_compatible
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
@python_2_unicode_compatible
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
@python_2_unicode_compatible
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
@python_2_unicode_compatible
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
        # Need to be sure that welcome article exists in this db instance
        qset = AllowedUrl.objects.filter(url=settings.WELCOME_ARTICLE_URL)
        if qset.exists():
            aurl = qset[0]
        if not aurl:
            logger.error("No Welcome article listed in allowed urls!")
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


# OrbitCmeOffer
# An offer for a user is generated based on the user's plugin activity.
@python_2_unicode_compatible
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
        profile_specs = set([s.name for s in profile.specialties.all()])
        # user's profile cmetags
        pcts = ProfileCmetag.objects.filter(profile=profile, is_active=True).order_by('pk')
        pct_tags = [pct.tag for pct in pcts]
        # partition into pct_spectags and pct_othertags
        pct_spectags = set([]); pct_othertags = set([])
        for tag in pct_tags:
            if tag.name in profile_specs:
                pct_spectags.add(tag)
            else:
                pct_othertags.add(tag)

        sacmeTag = CmeTag.objects.get(name=CMETAG_SACME)
        # First check if can select SA-CME tag
        if profile.isPhysician() and profile.specialties.filter(name__in=SACME_SPECIALTIES).exists():
            self.selectedTags.add(sacmeTag)
        if not pct_tags:
            logger.warning('assignCmeTags Offer {0.pk}: user {0.user} has no profile tags.'.format(self))
            return
        urlUserTags = []
        # 1. Intersection of UrlTagFreq tags with pct_othertags
        #   Exclude pct_spectags in order to give more weight to the other tags
        #   Exclude SA-CME tag b/c that is handled separately
        if pct_othertags:
            qs = UrlTagFreq.objects \
                .filter(url=aurl, tag__in=pct_othertags, numOffers__gte=MIN_VOTE_FOR_REC) \
                .exclude(tag=sacmeTag) \
                .order_by('-numOffers','id')
            for utf in qs:
                urlUserTags.append(utf.tag)
        # Url default tags (usually present in UrlTagFreq, but in some cases, a default tag may have been manually assigned)
        uut_set = set(urlUserTags)
        for t in aurl.cmeTags.exclude(pk=sacmeTag.pk):
            if t in pct_othertags and t not in uut_set: # aurl.tag is contained in user's tags and not already in set
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
            # Assign recaurl.cmeTag as selected tag
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
        # 2. No recaurl. Use top tag from urlUserTags
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
        # 3. No urlUserTags. Try specTags queryset
        if specTags.exists():
            selTag = specTags[0]
            self.selectedTags.add(selTag)
            logger.info('SelectedTag from specialty {0} for offer {1.pk}'.format(selTag, self))
            # add any remaining spectags to recommendedTags
            if len(specTags) > 1:
                for t in specTags[1:]:
                    self.tags.add(t)
            return
        # 4. No specTags. User read an article whose esite/url tags do not intersect with user's profile tags.
        if pct_spectags:
            selTag = pct_spectags.pop()
        elif pct_othertags:
            selTag = pct_othertags.pop()
        self.selectedTags.add(selTag)
        logger.info('SelectedTag from non-match profileTag {0} for offer {1.pk}'.format(selTag, self))
        return

    def setTagsFromRedeem(self, tags):
        """Called by redeem offer serializer to sync offer.selectedTags with the given tags:
        Args:
            tags: CmeTag queryset from an entry
        """
        self.selectedTags.set(tags) # the actual selected tags


# OrbitCmeOffer stats per org
@python_2_unicode_compatible
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
