#!/bin/bash
# This is meant to be called by a cron task on the admin server.
cd /home/ubuntu/orbit_server
/home/ubuntu/virtualenvs/venv/bin/python manage.py inviterDiscount
