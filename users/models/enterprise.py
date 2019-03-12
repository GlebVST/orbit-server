from __future__ import unicode_literals
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from smtplib import SMTPException
from users.emailutils import getHostname, sendPasswordTicketEmail
from .base import (
        Organization,
        orgfile_document_path
    )

logger = logging.getLogger('gen.models')

class OrgFileManager(models.Manager):

    def getCsvFileDialect(self, orgfile):
        """This is called the OrgFileUpload hander to check the file dialect
        Args:
            orgfile: OrgFile instance
        Expected file format: lastName, firstName, email, role
        Returns: str - dialect found. None if none found
        """
        import csv
        with open(orgfile.document, 'rb') as f:
            try:
                dialect = csv.Sniffer().sniff(f.read(1024))
            except csv.Error:
                logger.error('getCsvFileDialect csv.Error for file_id {0.pk}'.format(orgfile))
                return None
            else:
                return dialect

@python_2_unicode_compatible
class OrgFile(models.Model):
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='orgfiles',
        db_index=True
    )
    organization = models.ForeignKey(Organization,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='orgfiles'
    )
    document = models.FileField(upload_to=orgfile_document_path,
        help_text='Original document uploaded by user')
    csvfile = models.FileField(null=True, blank=True, upload_to=orgfile_document_path,
            help_text='If original document is not in plain-text CSV, then upload converted file here')
    name = models.CharField(max_length=255, blank=True, help_text='document file name')
    content_type = models.CharField(max_length=100, blank=True, help_text='document content_type')
    processed = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    objects = OrgFileManager()

    class Meta:
        verbose_name_plural = 'Enterprise File Uploads'

    def __str__(self):
        return self.name

@python_2_unicode_compatible
class OrgGroup(models.Model):
    """Practice divisions. An OrgMember can belong to one of these groups"""
    organization = models.ForeignKey(Organization,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='orggroups'
    )
    name = models.CharField(max_length=100,
            help_text='Uppercase first and last name for search')
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'name')
        verbose_name_plural = 'Enterprise Practice Divisions'

    def __str__(self):
        return self.name


class OrgMemberManager(models.Manager):

    def makeFullName(self, firstName, lastName):
        return u"{0} {1}".format(firstName.upper(), lastName.upper())

    def createMember(self, org, group, profile, is_admin=False, pending=False):
        """Create new OrgMember instance.
        Args:
            org: Organization instance
            group: OrgGroup instance or None
            profile: Profile instance
            is_admin: bool default is False
            is_pending: bool default is False
        Returns: OrgMember instance
        """
        user = profile.user
        if group and group.organization != org:
            raise ValueError('createMember: group does not belong to the given org')
            return
        fullName = self.makeFullName(profile.firstName, profile.lastName)
        compliance = 4 if is_admin else 2
        m = self.model.objects.create(
                organization=org,
                group=group,
                user=user,
                fullname=fullName,
                compliance=compliance,
                is_admin=is_admin,
                pending=pending
            )
        m.inviteDate = m.created
        m.save(update_fields=('inviteDate',))
        return m

    def search_filter(self, search_term, filter_kwargs, orderByFields):
        """Returns a queryset that filters active OrgMembers by the given org and search_term
        Args:
            search_term: str : to query fullname and username
            filter_kwargs: dict must contain key: organization, else raise KeyError
            orderByFields: tuple of fields to order by
        Returns: queryset of active OrgMembers
        """
        org =  filter_kwargs['organization'] # ensure org is contained to filter by a given organization
        base_qs = self.model.objects.select_related('user', 'user__profile', 'group').filter(**filter_kwargs)
        qs1 = base_qs.filter(fullname__contains=search_term.upper())
        qs2 = base_qs.filter(user__username__istartswith=search_term)
        qs = qs1
        if not qs.exists():
            qs = qs2
        return qs.order_by(*orderByFields)

    def getInactiveRemovedUsers(self, org):
        """Find the users removed from the given org who do not
        currently have a paid subscription (regardless of status)
        Returns: list of User instances
        """
        qset = OrgMember.objects.filter(organization=org, removeDate__isnull=False).order_by('created')
        if not qset.exists():
            return []
        users = []
        for m in qset:
            user = m.user
            qs = user.subscriptions.select_related('plan').order_by('-created')
            if qs.exists():
                user_subs = qs[0]
                if not user_subs.plan.isPaid():
                    users.append(user)
            else:
                users.append(user)
        return users

    def sendPasswordTicket(self, socialId, member, apiConn):
        hostname = getHostname() # this ensures hostname is either prod or test server (not admin server)
        UI_LOGIN_URL = 'https://{0}{1}'.format(hostname, settings.UI_LINK_LOGIN)
        ticket_url = apiConn.change_password_ticket(socialId, UI_LOGIN_URL)
        # TODO remove this dangerous ticket exposure when we are sure this works and no need to try out users
        logger.info('ticket_url for {0}={1}'.format(member.user.email, ticket_url))
        try:
            delivered = sendPasswordTicketEmail(member, ticket_url)
            if delivered:
                member.setPasswordEmailSent = True
                member.inviteDate = timezone.now()
                member.save(update_fields=('setPasswordEmailSent','inviteDate'))
        except SMTPException as e:
            error_msg = u'sendPasswordTicketEmail failed for org member {0.fullname}. ticket_url={1}'.format(member, ticket_url)
            if settings.ENV_TYPE == settings.ENV_PROD:
                logger.exception(error_msg)
            else:
                logger.warning(error_msg)
        return member

@python_2_unicode_compatible
class OrgMember(models.Model):
    STATUS_ACTIVE = 'Active'
    STATUS_INVITED = 'Invited'
    STATUS_REMOVED = 'Removed'
    # fields
    organization = models.ForeignKey(Organization,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='orgmembers'
    )
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='orgmembers',
    )
    group = models.ForeignKey(OrgGroup,
        on_delete=models.SET_NULL,
        db_index=True,
        null=True,
        blank=True,
        related_name='orgmembers',
    )
    fullname = models.CharField(max_length=100, db_index=True,
            help_text='Uppercase first and last name for search')
    is_admin = models.BooleanField(default=False, db_index=True,
            help_text='True if user is an admin for this organization')
    removeDate = models.DateTimeField(null=True, blank=True,
            help_text='date the member was removed')
    inviteDate = models.DateTimeField(null=True, blank=True,
            help_text='date the member was last invited. This is updated each time the invite email is re-sent to the user.')
    compliance = models.PositiveSmallIntegerField(default=1, db_index=True,
            help_text='Cached compliance level aggregated over user goals')
    setPasswordEmailSent = models.BooleanField(default=False,
            help_text='Set to True when password-ticket email is sent')
    orgfiles = models.ManyToManyField(OrgFile, blank=True, related_name='orgmembers')
    pending = models.BooleanField(default=False,
            help_text='Set to True when invitation is sent to existing user to join team.')
    snapshot = JSONField(default='', blank=True,
            help_text='A snapshot of the goals status for this user. It is computed by a management command run periodically.')
    snapshotDate = models.DateTimeField(null=True, blank=True,
            help_text='Timestamp of the snapshot generation')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = OrgMemberManager()

    class Meta:
        unique_together = ('organization', 'user')
        verbose_name_plural = 'Enterprise Members'

    def __str__(self):
        return '{0.user}/{0.organization}'.format(self)

    def getEnterpriseStatus(self):
        """Return one of:
        STATUS_ACTIVE
        STATUS_INVITED
        STATUS_REMOVED
        for self
        """
        profile = self.user.profile
        if self.removeDate:
            return OrgMember.STATUS_REMOVED
        elif profile.verified and not self.pending:
            return OrgMember.STATUS_ACTIVE
        return OrgMember.STATUS_INVITED
