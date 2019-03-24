import pip
import os
import pathlib
import subprocess
import sys
import time
import venv

import flask
import pymongo

client = pymongo.MongoClient(connect=False)
emperor_db = client.emperor

app = flask.Flask(__name__)
app.debug = True

def clone_repo(name):
  start_char = name[0]
  pathlib.Path('/var/data/%s' % start_char).mkdir(parents=True, exist_ok=True)
  path = '/var/data/%s/%s/' % (start_char, name)
  completed = subprocess.run([
    'git', 'clone',
    'https://github.com/audiodude/rainfall.git',
    path,
  ])
  return completed.returncode == 0

def create_venv(name):
  try:
    output = subprocess.check_output([
      '/usr/bin/python3',
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
  return flask.render_template('index.html')

@app.route('/create', methods=['POST'])
def create():
  name = flask.request.form['username']

  if clone_repo(name) and create_venv(name):
    insert_mongo_record(name)
    update_nginx(name)
    return flask.redirect('https://%s.rainfall.dev' % name)
  else:
    return 'Error'
