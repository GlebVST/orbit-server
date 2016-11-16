from __future__ import unicode_literals

import datetime
import uuid
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db import models
#from django.contrib.contenttypes.fields import GenericForeignKey
#from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

@python_2_unicode_compatible
class Degree(models.Model):
    abbrev = models.CharField(max_length=5, unique=True)
    name = models.CharField(max_length=30)
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    def __str__(self):
        return self.abbrev

@python_2_unicode_compatible
class Profile(models.Model):
    user = models.OneToOneField(User,
        on_delete=models.CASCADE,
        primary_key=True
    )
    firstName = models.CharField(max_length=30)
    lastName = models.CharField(max_length=30)
    jobTitle = models.CharField(max_length=100, blank=True)
    degrees = models.ManyToManyField(Degree)
    description = models.TextField(blank=True) # about me
    npiNumber = models.CharField(max_length=20, blank=True)
    socialUrl = models.URLField(blank=True)
    pictureUrl = models.URLField(max_length=300, blank=True)
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    def __str__(self):
        return self.npiNumber

@python_2_unicode_compatible
class Customer(models.Model):
    user = models.OneToOneField(User,
        on_delete=models.CASCADE,
        primary_key=True
    )
    customerId = models.UUIDField(unique=True, editable=False, default=uuid.uuid4)
    contactEmail = models.EmailField(blank=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    def __str__(self):
        return str(self.customerId)


@python_2_unicode_compatible
class PointTransaction(models.Model):
    customer = models.ForeignKey(Customer,
        on_delete=models.CASCADE,
        db_index=True
    )
    points = models.DecimalField(max_digits=6, decimal_places=2)
    pricePaid = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    transactionId = models.CharField(max_length=36, unique=True)
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    def __str__(self):
        return self.transactionId

# Available options for purchasing points
@python_2_unicode_compatible
class PointPurchaseOption(models.Model):
    points = models.DecimalField(max_digits=6, decimal_places=2)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    def __str__(self):
        return str(self.points)
