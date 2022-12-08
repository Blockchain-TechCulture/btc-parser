FROM docker.io/python:3.9-alpine3.16
WORKDIR /home/app
COPY . .
RUN apk update && apk add --no-cache bash
RUN pip install -r requirements.txt && mkdir logs
CMD ["python3", "main.py"]
