---
sidebar_position: 3
title: Docker
description: Run safaribooks in a Docker container.
---

# Docker Usage

Run safaribooks in a container without installing Python locally.

## Building the image

```bash
git clone https://github.com/joeblackwaslike/safaribooks.git
cd safaribooks
docker build -t safaribooks .
```

## Running a download

Mount a volume for the output directory and pass your cookies:

```bash
docker run --rm \
  -v $(pwd)/cookies.json:/app/cookies.json:ro \
  -e SAFARI_COOKIES_FILE=/app/cookies.json \
  -v $(pwd)/Books:/app/Books \
  safaribooks safari fetch 9781492056348
```

| Mount / Env | Purpose |
|-------------|---------|
| `$(pwd)/cookies.json:/app/cookies.json` | Cookie file (read-only) |
| `SAFARI_COOKIES_FILE=/app/cookies.json` | Tell the app where to find cookies |
| `$(pwd)/Books:/app/Books` | Output directory for EPUBs |

:::tip
Set up cookies on your host machine first with `safari auth extract`, then mount the cookie file into the container.
:::

## Passing flags

All CLI flags work the same inside the container:

```bash
docker run --rm \
  -v $(pwd)/cookies.json:/app/cookies.json:ro \
  -e SAFARI_COOKIES_FILE=/app/cookies.json \
  -v $(pwd)/Books:/app/Books \
  safaribooks safari fetch --kindle --rate-limit 0.5 9781492056348
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
    command: safari fetch 9781492056348
```

```bash
docker compose run --rm safaribooks
```

## Environment variables

You can pass configuration via environment variables instead of CLI flags:

```bash
docker run --rm \
  -e SAFARI_COOKIES_FILE=/app/cookies.json \
  -e SAFARI_RATE_LIMIT=0.5 \
  -e SAFARI_KINDLE=true \
  -v $(pwd)/cookies.json:/app/cookies.json:ro \
  -v $(pwd)/Books:/app/Books \
  safaribooks safari fetch 9781492056348
```

See the [environment variables guide](./environment-variables.md) for the full list.
