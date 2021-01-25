FROM tiangolo/uwsgi-nginx-flask:python3.8

RUN pip3 install -r /app/requirements.txt