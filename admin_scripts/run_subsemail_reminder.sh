#!/bin/bash
# This is meant to be called by a cron task on the admin server.
# It calls the sendSubscriptionEmail management command which sends
# out reminder email to each user about their automatic annual subscription
# renewal N days before the billingDate.
cd /home/ubuntu/orbit_server
/home/ubuntu/virtualenvs/venv/bin/python manage.py sendSubscriptionEmail
