import os

SONG_DIR = os.environ['RAINFALL_SONG_DIR']


def get_song_directory(site_id):
  start_char = site_id[0]
  return os.path.join(SONG_DIR, start_char, site_id, 'mp3')