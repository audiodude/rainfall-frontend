from datetime import timedelta
import pip
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.request
import venv

from google.oauth2 import id_token
from google.auth.transport import requests
import flask
from flask_session import Session
import pymongo
from werkzeug.utils import secure_filename

client = pymongo.MongoClient(connect=False)
emperor_db = client.emperor
rainfall_db = client.rainfall

CLIENT_ID = os.environ['RAINFALL_CLIENT_ID']

app = flask.Flask(__name__)
app.config.update({
  'SESSION_TYPE': 'mongodb',
  'SESSION_MONGODB_DB': 'rainfall',
  'SESSION_COOKIE_SECURE': False,
  'SESSION_USE_SIGNER': True,
  'SECRET_KEY': os.environ['FLASK_SECRET'],
  'PERMANENT_SESSION_LIFETIME': timedelta(days=90),
})
app.debug = True

ALLOWED_EXTENSIONS = set(['mp3'])

def clone_repo(name):
  start_char = name[0]
  subprocess.check_call([
    'sudo', '-u', 'www-data', 'mkdir', '-p',
    '/var/data/%s' % start_char,
  ])
  path = '/var/data/%s/%s/' % (start_char, name)
  subprocess.check_call([
    'sudo', '-u', 'www-data', 'git', 'clone',
    'https://github.com/audiodude/rainfall-template.git',
    path,
  ])
  return True

def delete_repo(name):
  start_char = name[0]
  path = '/var/data/%s/%s/' % (start_char, name)
  subprocess.check_call([
    'sudo', '-u', 'www-data', 'rm', '-rf', path,
  ])
  return True

def create_venv(name):
  try:
    output = subprocess.check_output([
      'sudo', '-u', 'www-data', '/usr/bin/python3',
      '/home/tmoney/code/rainfall-frontend/create_venv.py',
    name], stderr=subprocess.STDOUT)
  except Exception as e:
    raise TypeError(e.output)
  return True

def insert_mongo_record(name):
  start_char = name[0]
  mongo_config = {
    "name" : "%s.ini" % name,
    "config" : '''[uwsgi]
virtualenv = /var/data/%(start_char)s/%(name)s/venv
uid = www-data
gid = www-data
wsgi-file = /var/data/%(start_char)s/%(name)s/sitebuilder.py
plugin = python
callable = app
env = RAINFALL_SITE_ID=%(name)s
env = CHECK_REFERER=1
''' % {'start_char': start_char, 'name': name},
    "ts" : time.gmtime(),
    "socket" : "/var/run/uwsgi/%s.socket" % name,
    "enabled" : 1
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
    subprocess.check_output(
      ['sudo', 'service', 'nginx', 'reload'], stderr=subprocess.STDOUT)
  except Exception as e:
    raise ValueError(e.output)


def delete_nginx(name):
  config_path = '/etc/nginx/sites-available/%s' % name
  enabled_path = '/etc/nginx/sites-enabled/%s' % name
  if os.path.isfile(enabled_path):
    os.unlink(enabled_path)
  if os.path.isfile(config_path):
    os.unlink(config_path)
  return True

def insert_rainfall_site(user_id, name):
  rainfall_db.sites.update_one({'user_id': user_id}, {'$set': {
      'user_id': user_id,
      'site_id': name,
      'header': 'Songs and Sounds by [Rainfall](https://rainfall.dev)',
      'footer': 'Copyright 2019, All Rights Reserved',
    }}, upsert=True)

def delete_rainfall_site(user_id):
  rainfall_db.sites.delete_one({'user_id': user_id})
  return True

def wait_for_site_ready(site_id):
  retries = 5
  retrySeconds = .5

  while True:
    if retries <= 0:
      return False
    request = urllib.request.Request(
      'https://%s.rainfall.dev/' % site_id,
      headers={'Referer' : 'https://rainfall.dev/edit'})
    try:
      with urllib.request.urlopen(request) as res:
        if res.getcode() == 200:
          return True
    except:
      pass
    finally:
      time.sleep(retrySeconds)
      retries -= 1

@app.route('/')
def index():
  if flask.session.get('user_id') and False:
    return flask.redirect('/edit')

  return flask.render_template('index.html')

@app.route('/tokensignin', methods=['POST'])
def tokensignin():
  token = flask.request.form['id_token']
  try:
    idinfo = id_token.verify_oauth2_token(token, requests.Request(), CLIENT_ID)

    if idinfo['iss'] not in (
        'accounts.google.com', 'https://accounts.google.com'):
      raise ValueError('Wrong issuer.')

    if idinfo['aud'] != CLIENT_ID:
      raise ValueError('Wrong client.')

    user_id = idinfo['sub']

    rainfall_db.users.update_one({'user_id': user_id}, {'$set': {
      'user_id': user_id,
      'email': idinfo['email'],
      'name': idinfo['name'],
      'picture': idinfo['picture'],
    }}, upsert=True)
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

  site = rainfall_db.sites.find_one({'user_id': user_id})
  if not site:
    return flask.redirect('/new')

  wait_for_site_ready(site['site_id'])
  return flask.render_template('edit.html', site=site)

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
    }, {
      '$set': {
        'header': header,
        'footer': footer,
      }
    })

  return flask.redirect('/edit#site')

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_song_directory(site_id):
  start_char = site_id[0]
  return '/var/data/%s/%s/static/mp3' % (start_char, site_id)

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
    '$addToSet': {'songs': song_document},
  })

  return ('', 203)

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

  return flask.render_template('new.html', user=user)

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

  if clone_repo(name) and create_venv(name):
    insert_mongo_record(name)
    update_nginx(name)
    insert_rainfall_site(user_id, name)
    return flask.redirect('/edit')
  else:
    return 'Error'

@app.route('/destroy', methods=['POST'])
def destroy():
  user_id = flask.session.get('user_id')
  if not user_id:
    return flask.redirect('/')

  user = rainfall_db.users.find_one({'user_id': user_id})
  if not user:
    return flask.redirect('/')

  name = user['email']
  name = sanitize(name)

  delete_repo(name)
  delete_mongo_record(name)
  delete_nginx(name)
  delete_rainfall_site(user_id)
  rainfall_db.users.delete_one({'user_id': user_id})

  return flask.redirect('/')
  
