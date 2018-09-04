"""Models managed by the plugin_server project"""
from __future__ import unicode_literals
import logging
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible

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
