FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY safaribooks.py retrieve_cookies.py ./

VOLUME ["/app/Books"]

ENTRYPOINT ["python", "safaribooks.py"]
