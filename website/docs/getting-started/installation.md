---
sidebar_position: 2
title: Installation
description: Install safaribooks via uv, pip, Docker, or from source.
---

# Installation

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

<Tabs>
<TabItem value="uv" label="uv (recommended)" default>

[uv](https://docs.astral.sh/uv/) is the recommended package manager for safaribooks.

```bash
# Install as a CLI tool
uv tool install safaribooks

# Or add to an existing project
uv add safaribooks
```

</TabItem>
<TabItem value="pip" label="pip">

```bash
pip install safaribooks
```

</TabItem>
<TabItem value="docker" label="Docker">

```bash
git clone https://github.com/joeblackwaslike/safaribooks.git
cd safaribooks
docker build -t safaribooks .
```

See the [Docker guide](../guides/docker.md) for usage details.

</TabItem>
<TabItem value="source" label="From Source">

```bash
git clone https://github.com/joeblackwaslike/safaribooks.git
cd safaribooks
uv sync
```

Run commands with `uv run safari` when developing from source.

</TabItem>
</Tabs>

## Verify installation

```bash
safari --version
```

You should see the version number printed to the terminal.

## Optional dependencies

| Package | Purpose |
|---------|---------|
| `Pillow` | Image resizing and quality optimization (`--image-max-size`, `--image-quality`) |

Install optional dependencies:

```bash
uv tool install 'safaribooks[images]'
```

## Next step

[Set up authentication](./authentication.md) to connect safaribooks with your O'Reilly account.
