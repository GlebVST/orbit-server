## Installation

To run this project, first make sure you have python2.7, python-dev, pip, and virtualenv on your machine. 
  
  ```
  git clone ...
  virtualenv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ./run.sh
  ```
  
Optionally override environment variables in run.sh to use your own Braintree & Facebook secrets.

## Scripts

To create BrowserCme offers for testing:

  ```
  python manage.py shell
  from scripts import make_offer as mo
  user = mo.getUser('Max')  # or mo.getUser(email='some_email')
  mo.makeOffers(user)
  ```

