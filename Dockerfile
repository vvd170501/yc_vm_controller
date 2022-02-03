# no grpc on alpine :(
FROM python:3.10-slim

WORKDIR /bot

COPY ./requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY ./src/* ./

STOPSIGNAL SIGINT

ENTRYPOINT ["./main.py"]
