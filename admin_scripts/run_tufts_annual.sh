#!/bin/bash
# This is meant to be called by a cron task on the prod admin server.
# It should be called on 7/1 to generate Annual Report for 06/30 of prior year
# to 06/30 inclusive of current year.
cd /home/ubuntu/orbit_server
/home/ubuntu/virtualenvs/venv/bin/python manage.py makeTuftsReport --end_of_year
