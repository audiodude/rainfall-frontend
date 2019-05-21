from datetime import timedelta
import pip
import os
import pathlib
import subprocess
import sys
import time
import venv

from google.oauth2 import id_token
from google.auth.transport import requests
import flask
from flask_session import Session
import pymongo

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

def clone_repo(name):
  start_char = name[0]
  subprocess.check_call([
    'sudo', '-u', 'www-data', 'mkdir', '-p',
    '/var/data/%s' % start_char,
  ])
  path = '/var/data/%s/%s/' % (start_char, name)
  subprocess.check_call([
    'sudo', '-u', 'www-data', 'git', 'clone',
    'https://github.com/audiodude/rainfall.git',
    path,
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
env = RAINFALL_USERNAME=%s(name)
''' % {'start_char': start_char, 'name': name},
    "ts" : time.gmtime(),
    "socket" : "/var/run/uwsgi/%s.socket" % name,
    "enabled" : 1
  }

  emperor_db.vassals.insert_one(mongo_config)

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

@app.route('/')
def index():
  if flask.session.get('user_id'):
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
    flask.session['user_id'] = user_id
    return ('', 201)
  except ValueError:
    # Invalid token
    return ('Sign in error', 403)

@app.route('/edit')
def edit():
  user_id = flask.session.get('user_id')
  if not user_id:
    return flask.redirect('/')

  site = rainfall_db.sites.find_one({'user_id': user_id})
  if not site:
    return flask.redirect('/new')

  return flask.render_template('edit.html', site=site)

@app.route('/new')
def new():
  return flask.render_template('new.html')

@app.route('/create', methods=['POST'])
def create():
  name = flask.request.form['username']

  if clone_repo(name) and create_venv(name):
    insert_mongo_record(name)
    update_nginx(name)
    return flask.redirect('https://%s.rainfall.dev' % name)
  else:
    return 'Error'
