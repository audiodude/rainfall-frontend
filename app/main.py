from datetime import timedelta, datetime
import json
import pip
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.request
import venv

from dotenv import load_dotenv
import flask
from flask_session import Session
from flask_wtf.csrf import CSRFProtect
from google.oauth2 import id_token
from google.auth.transport import requests as googrequests
import pymongo
import requests
from werkzeug.utils import secure_filename

from preview.site import site
from util import get_song_directory

load_dotenv()
GOOGLE_CLIENT_ID = os.environ['RAINFALL_CLIENT_ID']
NETLIFY_CLIENT_ID = os.environ['RAINFALL_NETLIFY_CLIENT_ID']
NETLIFY_CLIENT_SECRET = os.environ['RAINFALL_NETLIFY_CLIENT_SECRET']
SITE_URL = os.environ['RAINFALL_SITE_URL']
MONGO_URI = os.environ['RAINFALL_MONGO_URI']

client = pymongo.MongoClient(MONGO_URI, connect=False)
emperor_db = client.emperor
rainfall_db = client.rainfall

app = flask.Flask(__name__)
app.config.update({
    'SESSION_TYPE': 'mongodb',
    'SESSION_MONGODB_DB': 'rainfall',
    'SESSION_COOKIE_SECURE': False,
    'SESSION_USE_SIGNER': True,
    'SECRET_KEY': os.environ['FLASK_SECRET'],
    'PERMANENT_SESSION_LIFETIME': timedelta(days=90),
})
csrf = CSRFProtect(app)
app.debug = True

ALLOWED_EXTENSIONS = set(['mp3'])


def register_sites():
  for s in rainfall_db.sites.find():
    app.register_blueprint(site,
                           url_prefix='/preview/%s' % s['site_id'],
                           url_defaults={'site_id': s['site_id']})


register_sites()


def clone_repo(name):
  start_char = name[0]
  subprocess.check_call([
      'sudo',
      '-u',
      'www-data',
      'mkdir',
      '-p',
      '/var/data/%s' % start_char,
  ])
  path = '/var/data/%s/%s/' % (start_char, name)
  subprocess.check_call([
      'sudo',
      '-u',
      'www-data',
      'git',
      'clone',
      'https://github.com/audiodude/rainfall-template.git',
      path,
  ])
  return True


def create_venv(name):
  try:
    output = subprocess.check_output([
        'sudo', '-u', 'www-data', '/usr/bin/python3',
        '/home/tmoney/code/rainfall-frontend/create_venv.py', name
    ],
                                     stderr=subprocess.STDOUT)
  except Exception as e:
    raise ValueError(e.output)
  return True


def build_site(site_id):
  start_char = site_id[0]
  base_path = '/var/data/%s/%s' % (start_char, site_id)
  try:
    subprocess.check_call([
        'sudo', '-u', 'www-data',
        'RAINFALL_SITE_ID=%s' % site_id,
        '%s/venv/bin/python3' % base_path,
        '%s/sitebuilder.py' % base_path, 'build'
    ],
                          stderr=subprocess.STDOUT)
  except Exception as e:
    raise ValueError(e.output)


def create_site_zip(site_id):
  start_char = site_id[0]
  base_path = '/var/data/%s/%s' % (start_char, site_id)
  zip_path = '%s/site.zip' % base_path
  if os.path.isfile(zip_path):
    os.unlink(zip_path)
  try:
    subprocess.check_call([
        'sudo', '-u', 'www-data', 'zip', zip_path, '-r',
        '%s/build' % base_path
    ])
  except Exception as e:
    raise ValueError(e.output)


def create_netlify_site(site_id, access_token):
  start_char = site_id[0]
  zip_path = '/var/data/%s/%s/site.zip' % (start_char, site_id)
  with open(zip_path, 'rb') as f:
    data = f.read()
  res = requests.post(url='https://api.netlify.com/api/v1/sites',
                      data=data,
                      headers={
                          'Content-Type': 'application/zip',
                          'Authorization': 'Bearer %s' % access_token,
                      })
  return res.json()['id']


def insert_mongo_record(name):
  start_char = name[0]
  mongo_config = {
      "name":
          "%s.ini" % name,
      "config":
          '''[uwsgi]
virtualenv = /var/data/%(start_char)s/%(name)s/venv
uid = www-data
gid = www-data
wsgi-file = /var/data/%(start_char)s/%(name)s/sitebuilder.py
plugin = python
callable = app
env = RAINFALL_SITE_ID=%(name)s
env = CHECK_REFERER=1
''' % {
              'start_char': start_char,
              'name': name
          },
      "ts":
          time.gmtime(),
      "socket":
          "/var/run/uwsgi/%s.socket" % name,
      "enabled":
          1
  }

  emperor_db.vassals.insert_one(mongo_config)


def delete_mongo_record(name):
  emperor_db.vassals.delete_one({'name': '%s.ini' % name})


def update_nginx(name):
  config = flask.render_template('nginx.txt', name=name)
  config_path = '/etc/nginx/sites-available/%s' % name
  enabled_path = '/etc/nginx/sites-enabled/%s' % name
  with open(config_path, 'w') as f:
    f.write(config)

  if os.path.isfile(enabled_path):
    os.unlink(enabled_path)
  os.symlink(config_path, enabled_path)
  try:
    subprocess.check_output(['sudo', 'service', 'nginx', 'reload'],
                            stderr=subprocess.STDOUT)
  except Exception as e:
    raise ValueError(e.output)


def insert_rainfall_site(user_id, name):
  year_text = datetime.now().year
  rainfall_db.sites.update_one({'user_id': user_id}, {
      '$set': {
          'user_id': user_id,
          'site_id': name,
          'header': 'Songs and Sounds by [Rainfall](https://rainfall.dev)',
          'footer': 'Copyright %s, All Rights Reserved' % year_text,
      }
  },
                               upsert=True)


@app.route('/')
def index():
  if flask.session.get('user_id'):
    return flask.redirect('/edit')

  return flask.render_template('index.html', SITE_URL=SITE_URL)


@app.route('/oauth2')
def oauth2():
  return flask.render_template('capture_token.html', SITE_URL=SITE_URL)


@app.route('/capture_token')
def capture_token():
  user_id = flask.session.get('user_id')
  if user_id:
    access_token = flask.request.args.get('access_token')
    if access_token:
      rainfall_db.users.update_one(
          {'user_id': user_id},
          {'$set': {
              'netlify_access_token': access_token,
          }},
          upsert=True)

  return ('', 204)


@app.route('/has_netlify')
def has_netlify():
  user_id = flask.session.get('user_id')
  if not user_id:
    return flask.jsonify({'has_netlify': False})

  user = rainfall_db.users.find_one({'user_id': user_id})
  if not user:
    return flask.jsonify({'has_netlify': False})

  return flask.jsonify({'has_netlify': bool(user.get('netlify_access_token'))})


@app.route('/tokensignin', methods=['POST'])
def tokensignin():
  token = flask.request.form['id_token']
  try:
    idinfo = id_token.verify_oauth2_token(token, googrequests.Request(),
                                          GOOGLE_CLIENT_ID)

    if idinfo['iss'] not in ('accounts.google.com',
                             'https://accounts.google.com'):
      raise ValueError('Wrong issuer.')

    if idinfo['aud'] != GOOGLE_CLIENT_ID:
      raise ValueError('Wrong client.')

    user_id = idinfo['sub']

    rainfall_db.users.update_one({'user_id': user_id}, {
        '$set': {
            'user_id': user_id,
            'email': idinfo['email'],
            'name': idinfo['name'],
            'picture': idinfo['picture'],
        }
    },
                                 upsert=True)
    flask.session['user_id'] = user_id
    return ('', 204)
  except ValueError as e:
    print(e)
    # Invalid token
    return ('Sign in error', 403)


@app.route('/signout')
def signout():
  del flask.session['user_id']
  return flask.redirect('/')


@app.route('/edit')
def edit():
  user_id = flask.session.get('user_id')
  if not user_id:
    return flask.redirect('/')

  user = rainfall_db.users.find_one({'user_id': user_id})
  netlify_token = user and user.get('netlify_access_token')

  site = rainfall_db.sites.find_one({'user_id': user_id})
  if not site:
    return flask.redirect('/new')

  initial_state = {
      'netlify_client_id': NETLIFY_CLIENT_ID,
      'has_connected_netlify': bool(netlify_token),
  }

  return flask.render_template('edit.html',
                               SITE_URL=SITE_URL,
                               site=site,
                               initial_state=json.dumps(initial_state))


@app.route('/publish', methods=['POST'])
def publish():
  user_id = flask.session.get('user_id')
  if not user_id:
    return ('Not Authorized', 403)

  user = rainfall_db.users.find_one({'user_id': user_id})
  netlify_token = user and user.get('netlify_access_token')
  if not netlify_token:
    return ('Bad Request', 400)

  site = rainfall_db.sites.find_one({'user_id': user_id})
  if not site:
    return ('Bad Request', 400)

  build_site(site['site_id'])
  create_site_zip(site['site_id'])
  netlify_site_id = create_netlify_site(site['site_id'], netlify_token)

  rainfall_db.users.update_one({'user_id': user_id},
                               {'$set': {
                                   'netlify_site_id': netlify_site_id,
                               }},
                               upsert=True)

  return ('No Content', 204)


@app.route('/update', methods=['POST'])
def update():
  user_id = flask.session.get('user_id')
  if not user_id:
    return flask.redirect('/')

  site = rainfall_db.sites.find_one({'user_id': user_id})
  if not site:
    return flask.redirect('/new')

  header = flask.request.form.get('header')
  footer = flask.request.form.get('footer')

  if header is not None or footer is not None:
    rainfall_db.sites.update({
        'site_id': site['site_id'],
    }, {'$set': {
        'header': header,
        'footer': footer,
    }})

  return flask.redirect('/edit#site')


def allowed_file(filename):
  return '.' in filename and \
         filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def create_song_directory(site_id):
  subprocess.check_call(['mkdir', '-p', get_song_directory(site_id)])


def delete_song_directory(site_id):
  subprocess.check_call(['rm', '-rf', get_song_directory(site_id)])


def get_slug(filename):
  base = filename.split('.', 1)[0]
  filename = re.sub('\W', '_', base)
  return re.sub('--+', '', filename)


def process_tags(raw_tags):
  tags = []
  chunks = re.split('[ ,]', raw_tags)
  for chunk in chunks:
    if chunk.startswith('#'):
      tags.append(chunk.replace('#', ''))
  return tags


@app.route('/upload', methods=['POST'])
def upload():
  user_id = flask.session.get('user_id')
  if not user_id:
    return ('Not Authorized', 403)

  site = rainfall_db.sites.find_one({'user_id': user_id})
  if not site:
    return ('No site', 404)

  name = flask.request.form.get('name')
  if not name:
    return flask.jsonify({'errors': ['Name is required']})

  song = flask.request.files['song']
  if song and allowed_file(song.filename):
    slug = get_slug(secure_filename(name))
    path = os.path.join(get_song_directory(site['site_id']), slug + '.mp3')
    song.save(path)
  else:
    return flask.jsonify({'errors': ['Song is required and must be an mp3']})

  description = flask.request.form.get('description', '')
  raw_tags = flask.request.form.get('tags', '')
  tags = process_tags(raw_tags)

  song_document = {
      'name': name,
      'slug': slug,
      'description': description,
      'tags': tags,
      'date_created': time.time(),
  }

  rainfall_db.sites.update({
      'site_id': site['site_id'],
  }, {
      '$addToSet': {
          'songs': song_document
      },
  })

  return ('', 204)


@app.route('/new')
def new():
  user_id = flask.session.get('user_id')
  if not user_id:
    return flask.redirect('/')

  user = rainfall_db.users.find_one({'user_id': user_id})
  if not user:
    return flask.redirect('/')

  site = rainfall_db.sites.find_one({'user_id': user_id})
  if site:
    return flask.redirect('/edit')

  return flask.render_template('new.html', SITE_URL=SITE_URL, user=user)


def sanitize(name):
  name = re.sub('[^a-zA-Z0-9]', '-', name)
  name = re.sub('-+', '-', name)
  return name


@app.route('/create', methods=['POST'])
def create():
  user_id = flask.session.get('user_id')
  if not user_id:
    return flask.redirect('/')

  user = rainfall_db.users.find_one({'user_id': user_id})
  if not user:
    return flask.redirect('/')

  terms = flask.request.form.get('terms-check')
  if not terms:
    return flask.render_template('new.html', user=user, errors=['terms'])

  name = user['email']
  name = sanitize(name)

  create_song_directory(name)
  insert_rainfall_site(user_id, name)
  return flask.redirect('/edit')


@app.route('/destroy', methods=['POST'])
def destroy():
  user_id = flask.session.get('user_id')
  if not user_id:
    return ('Bad Request', 400)

  user = rainfall_db.users.find_one({'user_id': user_id})
  if not user:
    return ('Bad Request', 400)

  del flask.session['user_id']
  name = sanitize(user['email'])

  delete_song_directory(name)
  delete_mongo_record(name)

  result = rainfall_db.sites.delete_one({'user_id': user_id})
  if result.deleted_count < 1:
    raise Exception(user_id)
  result = rainfall_db.users.delete_one({'user_id': user_id})
  if result.deleted_count < 1:
    raise Exception(user_id)

  return flask.redirect('/')