import logging
from datetime import datetime, timedelta
import pytz
from django.contrib.auth.models import User
from django.db import models

logger = logging.getLogger('gen.models')

class InfluencerGroupManager(models.Model):
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
    twitter_handle = models.CharField(max_length=20, blank=True, default='', help_text="Twitter handle (including the '@').")
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
        unique_together = ('group','user')
        ordering = ['group','-created']

    def __str__(self):
        return '{0.group}|{0.user}'.format(self)
