FROM python:3.12-slim

RUN pip install --no-cache-dir \
    pytest==9.1.1 \
    pyyaml==6.0.3

COPY veelcode_grader.py /opt/veelcode/veelcode_grader.py
ENV PYTHONPATH=/opt/veelcode PYTHONDONTWRITEBYTECODE=1

WORKDIR /grader
