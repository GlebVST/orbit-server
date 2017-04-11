## Installation

To run this project, first make sure you have python2.7, python-dev, pip, and virtualenv on your machine. 

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
 * ORBIT_SERVER_DEBUG     - true in development only, false otherwise.

#### FB Login

 * ORBIT_FB_AUTH_KEY
 * ORBIT_FB_AUTH_SECRET

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

Note: AWS SES credentials are currently hard-coded in settings.py.


## Scripts

To create BrowserCme offers for testing:

  ```
  python manage.py shell
  from scripts import make_offer as mo
  user = mo.getUser('Max')  # or mo.getUser(email='some_email')
  mo.makeOffers(user)
  ```

