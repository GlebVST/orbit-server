import logging
from datetime import datetime, timedelta
import pytz
from django.contrib.auth.models import User
from django.db import models
from .base import PracticeSpecialty, SubSpecialty

logger = logging.getLogger('gen.models')

class InfluencerGroupManager(models.Manager):
    def getLatestGroupForUser(self, user):
        """
        Args:
            user: User instance
        Returns: InfluencerGroup instance or None
        """
        qs = InfluencerMembership.objects.filter(user=user).order_by('-created')
        if qs.exists():
            return qs[0]
        return None

class InfluencerGroup(models.Model):
    name = models.CharField(max_length=80, unique=True, help_text='Influencer group name.')
    twitter_handle = models.CharField(max_length=20, blank=True, default='', help_text="Twitter handle (do not include the '@').")
    tweet_template = models.TextField(blank=True, default='',
        help_text='Tweet template. Template variables must be valid/be recognized by client/server code.')
    users = models.ManyToManyField(User,
        blank=True,
        through='InfluencerMembership',
        related_name='influencer_groups',
        help_text='Users assigned to this group'
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = InfluencerGroupManager()

    def __str__(self):
        return self.name

class InfluencerMembership(models.Model):
    group = models.ForeignKey(InfluencerGroup,
        on_delete=models.CASCADE,
        db_index=True,
    )
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        db_index=True,
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Influencer Group Membership'
        unique_together = ('group','user')
        ordering = ['group','-created']

    def __str__(self):
        return '{0.group}|{0.user}'.format(self)


class HashTagManager(models.Manager):
    def getTagsForUser(self, profile):
        """
        Args:
            profile: Profile instance
        Returns: queryset or None
        """
        specs = profile.specialties.all()
        subspecs = profile.subspecialties.all()
        qs_spec = None; qs_subspec = None
        # tags by spec
        if specs:
            # get the tags that apply at the specialty-level (e.g. tag must not have any subspecialties)
            qs_spec = self.model.objects.filter(
                specialties__in=[ps.pk for ps in specs],
                subspecialties=None
            )
        # tags by subspec (profile subspecs can only exist if profile specs exist)
        if subspecs:
            # get the tags that apply at the sub-specialty level (more specific)
            qs_subspec = self.model.objects.filter(subspecialties__in=[ss.pk for ss in subspecs])
        qs = None
        if qs_spec and qs_subspec:
            qs = qs_spec.union(qs_subspec)
        elif qs_spec:
            qs = qs_spec
        if qs:
            qs = qs.order_by('code')
        return qs

class HashTag(models.Model):
    code = models.CharField(max_length=30, unique=True, help_text="Unique Code (do not include the '#').")
    description = models.TextField(blank=True, default='', help_text='Description')
    specialties = models.ManyToManyField(PracticeSpecialty,
        blank=True,
        related_name='hashtags',
        help_text='Assigned specialties'
    )
    subspecialties = models.ManyToManyField(SubSpecialty,
        blank=True,
        related_name='hashtags',
        help_text='Assigned sub-specialties'
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = HashTagManager()

    def __str__(self):
        return self.code
    
    def formatSpecialties(self):
        return ", ".join([t.name for t in self.specialties.all()])
    formatSpecialties.short_description = "Specialties"

    def formatSubSpecialties(self):
        return ", ".join([t.name for t in self.subspecialties.all()])
    formatSubSpecialties.short_description = "SubSpecialties"
