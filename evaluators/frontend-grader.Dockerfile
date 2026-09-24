FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

RUN pip install --no-cache-dir --break-system-packages \
    pytest==9.1.1 \
    pytest-playwright==0.9.0 \
    playwright==1.63.0

COPY veelcode_grader.py /opt/veelcode/veelcode_grader.py
ENV PYTHONPATH=/opt/veelcode PYTHONDONTWRITEBYTECODE=1

WORKDIR /grader
