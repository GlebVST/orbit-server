#!/bin/bash
# This is meant to be called by a cron task
# With the esp_name option, an Email Service Provider can be specified. Default is "Mailchimp"
cd /home/ubuntu/orbit_server
/home/ubuntu/virtualenvs/venv/bin/python manage.py emailSync
