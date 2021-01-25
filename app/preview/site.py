from collections import defaultdict
from datetime import datetime
import markdown
import random
import sys
import os

from flask import Blueprint
from flask import Flask
from flask import Markup
from flask import g
from flask import render_template
from flask import request
from flask import send_from_directory
from flask import session
from flask_frozen import Freezer
from pymongo import MongoClient

from util import get_song_directory

client = MongoClient(connect=False)
rainfall_db = client.rainfall

site = Blueprint('site',
                 __name__,
                 template_folder='templates',
                 static_folder='static')

song_colors = [
    '#FD7632',
    '#477C90',
    '#4B0082',
    '#CD4640',
    '#85D817',
    '#DDB8C7',
    '#2AC8C6',
]

ENV = os.environ.get('RAINFALL_ENV', 'development')


def _annotate(song, i):
  if 'src' in song:
    return
  if ENV == 'development':
    song['src'] = 'file/%s.mp3' % (song['slug'])
  else:
    song['src'] = '/static/mp3/' + song['slug'] + '.mp3'
  song['dt'] = datetime.fromtimestamp(song['date_created'])
  _add_color(song, i)


def _add_color(song, i):
  song['color'] = song_colors[i % len(song_colors)]


@site.url_value_preprocessor
def pull_lang_code(endpoint, values):
  g.site_id = values.pop('site_id', None)


@site.route('/')
def index():
  if ENV == 'development':
    user_id = session.get('user_id')
    if not user_id:
      return ('Not Authorized', 403)

  if g.site_id is None:
    return ('Not Found', 404)

  site = rainfall_db.sites.find_one({'site_id': g.site_id})
  if site is None:
    return ('Not Found', 404)
  elif ENV == 'development' and site['user_id'] != user_id:
    return ('Not Authorized', 403)

  songs = site.get('songs', [])

  for i, song in enumerate(songs):
    _annotate(song, i)

  sorted_songs = sorted(list(songs), key=lambda song: song['dt'], reverse=True)

  # Re-add the colors once the songs are sorted.
  for i, song in enumerate(sorted_songs):
    _add_color(song, i)

  header = Markup(markdown.markdown(site['header']))
  footer = Markup(markdown.markdown(site['footer']))

  return render_template('site/index.html',
                         songs=sorted_songs,
                         header=header,
                         footer=footer)


@site.route('/file/<filename>')
def file_(filename):
  print('Getting file')
  # Use the user id from the session, not from the URL which could be spoofed.
  user_id = session.get('user_id')
  if not user_id:
    (404, 'Not found')

  site = rainfall_db.sites.find_one({'user_id': user_id})
  if not site:
    (404, 'Not found')

  if site:
    return send_from_directory(get_song_directory(site['site_id']), filename)


@site.route('/<slug>/')
def song(slug):
  related = defaultdict(list)

  if (os.environ.get('CHECK_REFERER') and
      'rainfall.dev' not in request.headers.get("Referer")):
    return ('Not Authorized', 403)

  if g.site_id is None:
    return ('Not Found', 404)

  site = rainfall_db.sites.find_one({'site_id': g.site_id})
  if site is None:
    return ('Not Found', 404)

  songs = site.get('songs', [])
  if not songs:
    return flask.redirect('/')

  for song in songs:
    if song['slug'] == slug:
      break

  _annotate(song, random.randrange(0, len(song_colors)))

  faq = Markup(markdown.markdown(site.get('faq', '')))

  for tag in song['tags']:
    for i, s in enumerate(songs):
      if tag in s['tags']:
        _annotate(s, i)
        if s['slug'] != song['slug']:
          related[tag].append(s)
  song['related'] = related
  song['src'] = '/static/mp3/' + slug + '.mp3'
  song['description_html'] = Markup(markdown.markdown(song['description']))
  return render_template('site/song.html', song=song, title=song['name'])