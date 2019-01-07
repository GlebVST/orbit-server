"""Models managed by the plugin_server project"""
from __future__ import unicode_literals
import logging
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.contrib.postgres.fields import JSONField

from common.appconstants import MAX_URL_LENGTH
from .base import (
    CMETAG_SACME,
    SACME_SPECIALTIES,
    CmeTag,
    EligibleSite,
    Organization
)
from .feed import Sponsor
logger = logging.getLogger('gen.models')


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


# User recommendations for AllowedUrls by tag
@python_2_unicode_compatible
class RecAllowedUrl(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recaurls')
    url = models.ForeignKey(AllowedUrl, on_delete=models.CASCADE, related_name='recaurls')
    cmeTag = models.ForeignKey(CmeTag, on_delete=models.CASCADE, related_name='recaurls')

    class Meta:
        managed = False
        db_table = 'trackers_recallowedurl'
        unique_together = ('user','url','cmeTag')

    def __str__(self):
        return '{0.user}|{0.cmeTag}|{0.url}'.format(self)


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
    tags = models.ManyToManyField(
        CmeTag,
        blank=True,
        related_name='new_offers',
        help_text='Suggested tags (intersected with user cmeTags by UI)'
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'trackers_orbitcmeoffer'
        verbose_name_plural = 'OrbitCME Offers'

    def __str__(self):
        return self.url.url

    def formatSuggestedTags(self):
        return ", ".join([t.name for t in self.tags.all()])
    formatSuggestedTags.short_description = "suggestedTags"

    def assignCmeTags(self):
        """Assign tags based on: eligible_site, url, and user"""
        esite = self.eligible_site
        # get suggested cmetags from the eligible_site.specialties
        specnames = [p.name for p in esite.specialties.all()]
        spectags = CmeTag.objects.filter(name__in=specnames) # tags whose name=pracspec.name
        self.tags.set(list(spectags))
        # tags from allowed_url
        for t in self.url.cmeTags.all():
            self.tags.add(t)
        # check if can add SA-CME tag
        profile = self.user.profile
        if profile.isPhysician() and profile.specialties.filter(name__in=SACME_SPECIALTIES).exists():
            self.tags.add(CmeTag.objects.get(name=CMETAG_SACME))


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
