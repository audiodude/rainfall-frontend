import os
import subprocess
import sys
import venv

def create_venv(name):
  start_char = name[0]  
  base_path = '/var/data/%s/%s' % (start_char, name)
  path = '%s/venv' % base_path
  req_path = '%s/requirements.txt' % base_path
  venv.create(path, with_pip=True, clear=True)

  try:
    subprocess.check_output([
      '%s/bin/pip' % path, 'install',
      '-r', req_path, '--no-cache-dir'
    ], stderr=subprocess.STDOUT)
  except Exception as e:
    print(e.output)
    raise

if __name__ == '__main__':
  create_venv(sys.argv[1])
