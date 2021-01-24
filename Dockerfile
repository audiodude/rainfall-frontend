FROM tiangolo/uwsgi-nginx-flask:python3.8

ENV LISTEN_PORT 8080

COPY ./app /app
RUN pip3 install -r /app/requirements.txt