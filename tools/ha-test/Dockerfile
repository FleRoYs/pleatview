# Test environment for the Home Assistant integration (HA needs Python 3.14).
FROM python:3.14
COPY requirements-test.txt /tmp/
RUN pip install --no-cache-dir -q --root-user-action=ignore -r /tmp/requirements-test.txt
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /src
