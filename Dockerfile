FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY safaribooks.py retrieve_cookies.py ./

RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /app/Books \
    && chown -R appuser:appuser /app
USER appuser

VOLUME ["/app/Books"]

ENTRYPOINT ["python", "safaribooks.py"]
