---
sidebar_position: 4
title: Docker Usage
description: Build and run safaribooks with Docker.
---

# Docker Usage Examples

Run safaribooks in a container without a local Python installation.

## Build

```bash
git clone https://github.com/joeblackwaslike/safaribooks.git
cd safaribooks
docker build -t safaribooks .
```

## Download a book

```bash
docker run --rm \
  -v $(pwd)/cookies.json:/app/cookies.json:ro \
  -e SAFARI_COOKIES_FILE=/app/cookies.json \
  -v $(pwd)/Books:/app/Books \
  safaribooks safari fetch 9781492056348
```

## Download with Kindle optimization

```bash
docker run --rm \
  -v $(pwd)/cookies.json:/app/cookies.json:ro \
  -e SAFARI_COOKIES_FILE=/app/cookies.json \
  -v $(pwd)/Books:/app/Books \
  safaribooks safari fetch --kindle 9781492056348
```

## Download from a file

```bash
docker run --rm \
  -v $(pwd)/cookies.json:/app/cookies.json:ro \
  -e SAFARI_COOKIES_FILE=/app/cookies.json \
  -v $(pwd)/Books:/app/Books \
  -v $(pwd)/books.txt:/app/books.txt:ro \
  safaribooks safari fetch --file /app/books.txt
```

## Docker Compose

```yaml title="docker-compose.yml"
services:
  safaribooks:
    build: .
    volumes:
      - ./cookies.json:/app/cookies.json:ro
      - ./Books:/app/Books
    environment:
      - SAFARI_COOKIES_FILE=/app/cookies.json
```

```bash
# Download a specific book
docker compose run --rm safaribooks safari fetch 9781492056348

# Download from a file
docker compose run --rm -v $(pwd)/books.txt:/app/books.txt:ro \
  safaribooks safari fetch --file /app/books.txt
```

:::tip
Set up authentication on your host machine first with `safari auth extract --browser chrome`, then mount the config directory read-only into the container.
:::
