# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from datetime import datetime
import pytz
from django.conf import settings

LOCAL_TZ = pytz.timezone(settings.LOCAL_TIME_ZONE)
TIMESTAMP_FMT = "%Y-%m-%d %H:%M:S %Z"

UNKNOWN_DATE = datetime(3000,1,1,tzinfo=pytz.utc)

def makeAwareDatetime(year, month, day, tz=pytz.utc):
    """Returns datetime object with tzinfo set.
    Raise ValueError if invalid date
    """
    return datetime(year, month, day, tzinfo=tz)

def fmtLocalDatetime(dt):
    return dt.astimezone(LOCAL_TZ).strftime(TIMESTAMP_FMT)
