---
sidebar_position: 2
title: SSL Issues
description: Troubleshoot SSL/TLS certificate errors.
---

# SSL Issues

SSL certificate verification errors can occur in corporate environments or with certain network configurations.

## Symptoms

- `SSLError` or `SSLCertVerificationError` in the output
- Error mentions "certificate verify failed"
- Downloads work on home network but not at work

## Common causes

### Corporate proxy / MITM inspection

Many corporate networks use SSL inspection proxies that replace certificates. Python's `certifi` CA bundle doesn't include your corporate CA.

### Outdated CA certificates

The system or Python's CA certificate bundle may be outdated.

### VPN interference

Some VPN configurations interfere with SSL verification.

## Quick fix: skip SSL verification

```bash
safari fetch --ssl-skip 9781492056348
```

Or via environment variable:

```bash
SAFARI_SSL_SKIP=true safari fetch 9781492056348
```

:::danger
`--ssl-skip` disables all SSL certificate verification. This makes your connection vulnerable to man-in-the-middle attacks. Only use this when you understand the risk and trust the network you're on.
:::

## Proper fix: install corporate CA

If your organization provides a root CA certificate:

```bash
# Add corporate CA to certifi bundle
pip install pip-system-certs

# Or set the CA bundle explicitly
export REQUESTS_CA_BUNDLE=/path/to/corporate-ca-bundle.pem
```

## Verify the fix

```bash
safari auth validate
```

If validation succeeds without `--ssl-skip`, SSL is working correctly.
