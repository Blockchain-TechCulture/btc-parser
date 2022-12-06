FROM python:3.9-alpine3.16
ENV APP_HOME=/home/app
RUN mkdir -p $APP_HOME

RUN apk update && apk add --no-cache bash

COPY /btc_parser/ $APP_HOME
RUN pip install -r $APP_HOME/requirements.txt; mkdir -p $APP_HOME/logs;
COPY .env $APP_HOME

WORKDIR $APP_HOME
CMD ["python3", "main.py"]