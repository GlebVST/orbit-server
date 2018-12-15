##Organization of Orbit Server

There are two apps in Orbit Server, each with it's own database structure (models.py):
(1) User app
(2) Goals app

## Installation

To run this project, first make sure you have python2.7, python-dev, pip, and virtualenv on your machine. 

Note to setup project on Mac OSx additional step is installing graphviz via `brew install graphviz` prior to other deps.

  ```
  git clone ...
  virtualenv venv
  source venv/bin/activate
  pip install -r requirements.txt
  Create .env file in the same dir as manage.py with key=value for the keys below.
  ./run.sh
  ```


### Environment variables

The following keys are expected in the .env file which is read by manage.py and wsgi.py:

#### Django project

 * ORBIT_ENV_TYPE         - one of: dev/stage/prod.  Use prod for production, stage for test, dev for development.
 * ORBIT_SERVER_HOSTNAME  - hostname of the server (e.g. test1.orbitcme.com)
 * ORBIT_SERVER_IP_ADDR   - (optional) if set, is added to ALLOWED_HOSTS

#### Auth0 Login

 * ORBIT_AUTH0_CLIENTID
 * ORBIT_AUTH0_SECRET
 * ORBIT_AUTH0_DOMAIN
 * ORBIT_AUTH0_MGMT_CLIENTID - Auth0 non-interactive client with permission to access the Auth0 management API
 * ORBIT_AUTH0_MGMT_CLIENT_SECRET

#### Braintree

 * ORBIT_BRAINTREE_MERCHID
 * ORBIT_BRAINTREE_PUBLIC_KEY
 * ORBIT_BRAINTREE_PRIVATE_KEY

#### Amazon RDS

 * ORBIT_DB_NAME
 * ORBIT_DB_USER
 * ORBIT_DB_PASSWORD
 * ORBIT_DB_HOST

#### Amazon S3

 * ORBIT_AWS_ACCESS_KEY_ID
 * ORBIT_AWS_SECRET_ACCESS_KEY
 * ORBIT_AWS_S3_BUCKET_NAME

#### LogDNA

 * ORBIT_LOGDNA_API_KEY

#### PayPal

 * PAYPAL_APP_NAME
 * PAYPAL_CLIENTID
 * PAYPAL_SECRET


Note: AWS SES credentials are currently hard-coded in settings.py.

## Scripts

To create BrowserCme offers for testing:

  ```
  python manage.py shell
  from scripts import make_offer as mo
  user = mo.getUser('Max')  # or mo.getUser(email='some_email')
  mo.makeOffers(user)
  ```

