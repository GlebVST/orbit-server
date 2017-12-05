#!/bin/bash
# This is meant to be called by a cron task on the admin server.
# With the report_only option, it only sends an email to admins.
# A user must log in and execute the command without the report_only option in order to make a BatchPayout.
cd /home/ubuntu/orbit_server
/home/ubuntu/virtualenvs/venv/bin/python manage.py afflPayout --report_only
