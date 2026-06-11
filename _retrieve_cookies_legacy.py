import argparse
import json
import os
import re
import stat
import sys

try:
    from safaribooks import COOKIES_FILE
except ImportError:
    COOKIES_FILE = "cookies.json"

BROWSER_JS = """
// Run this in your browser console on https://learning.oreilly.com:
JSON.stringify(document.cookie.split(';').reduce((o,c) => { c=c.trim(); let i=c.indexOf('='); o[c.substring(0,i)]=c.substring(i+1); return o; }, {}))
""".strip()

SESSION_COOKIE_PATTERN = re.compile(r"(session|jwt|token|logged|csrf)", re.IGNORECASE)


def _normalize_cookies(cookies):
    return {k.strip(): v.strip() for k, v in cookies.items() if k.strip() and v.strip()}


def _parse_auto(raw):
    """Auto-detect format: flat JSON dict, extension array, or raw cookie header."""
    raw = raw.strip()

    # Try JSON first
    try:
        text = raw
        if text.startswith('"') and text.endswith('"'):
            text = json.loads(text)
        data = json.loads(text)

        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data and isinstance(data[0], dict) and "name" in data[0]:
            return {
                c["name"]: c.get("value", "")
                for c in data
                if isinstance(c, dict) and "name" in c
                and (not c.get("domain") or ".oreilly.com" in c.get("domain", ""))
            }
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Try raw cookie header string
    return _parse_header(raw)


def _parse_header(raw):
    """Parse a raw 'Cookie: k=v; k2=v2' header string."""
    text = raw.strip()
    if text.lower().startswith("cookie:"):
        text = text[len("cookie:"):].strip()
    if not text:
        return {}
    cookies = {}
    for pair in text.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        idx = pair.find("=")
        if idx == -1:
            continue
        cookies[pair[:idx].strip()] = pair[idx + 1:].strip()
    return cookies


def from_browser(browser_name):
    try:
        import browser_cookie3
    except ImportError:
        print("browser_cookie3 not found. Install with: pip install browser_cookie3")
        sys.exit(1)

    browsers = {
        "chrome": browser_cookie3.chrome,
        "firefox": browser_cookie3.firefox,
        "edge": browser_cookie3.edge,
        "chromium": browser_cookie3.chromium,
    }
    try:
        cj = browsers[browser_name](domain_name=".oreilly.com")
    except Exception as e:
        print("Error extracting cookies from %s: %s" % (browser_name, e))
        print("Make sure the browser is closed and try again, or use paste mode instead.")
        sys.exit(1)
    return {c.name: c.value for c in cj}


def from_paste():
    print("Paste cookies from your browser, then press Enter on an empty line to finish.")
    print("  Accepted formats:")
    print("    - JSON from console:  %s" % BROWSER_JS.split("\n")[-1])
    print("    - Raw Cookie header:  Cookie: k1=v1; k2=v2")
    print('    - Extension export:   [{"name":"k","value":"v",...}, ...]')
    print()
    lines = []
    while True:
        try:
            line = input("> " if not lines else "  ")
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    raw = "\n".join(lines).strip()
    if not raw:
        print("Error: empty input.")
        sys.exit(1)
    cookies = _parse_auto(raw)
    if not cookies:
        print("Error: could not parse input. Check that you copied the full output.")
        sys.exit(1)
    return cookies


def from_file(filepath):
    if not os.path.isfile(filepath):
        print("Error: file not found: %s" % filepath)
        sys.exit(1)
    with open(filepath) as f:
        raw = f.read()
    cookies = _parse_auto(raw)
    if not cookies:
        print("Error: could not parse file. Expected JSON dict, extension array, or cookie header string.")
        sys.exit(1)
    return cookies


def from_header(raw):
    cookies = _parse_header(raw)
    if not cookies:
        print("Error: could not parse cookie header string.")
        sys.exit(1)
    return cookies


def validate_cookies(cookies):
    """Returns (is_valid, warnings) for a cookie dict."""
    warnings = []
    if not cookies:
        return False, ["No cookies found."]
    if len(cookies) < 3:
        warnings.append("Only %d cookie(s) found — extraction may be incomplete." % len(cookies))
    has_session = any(SESSION_COOKIE_PATTERN.search(k) for k in cookies)
    if not has_session:
        warnings.append("No session-related cookies found (expected names containing: session, jwt, token, logged, csrf).")
    empty = [k for k, v in cookies.items() if not v]
    if empty:
        warnings.append("Empty values for: %s" % ", ".join(empty))
    is_valid = has_session and len(cookies) >= 3
    return is_valid, warnings


def _save_cookies(cookies, output_path):
    with open(output_path, "w") as f:
        json.dump(cookies, f, indent=2)
    try:
        os.chmod(output_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    print("Saved %d cookies to %s" % (len(cookies), output_path))


def main():
    parser = argparse.ArgumentParser(
        description="Extract O'Reilly cookies for safaribooks",
        epilog="Examples:\n"
               "  python retrieve_cookies.py                         # paste mode (default)\n"
               "  python retrieve_cookies.py -b chrome               # auto-extract from browser\n"
               "  python retrieve_cookies.py -f cookies_export.json  # import from file\n"
               "  python retrieve_cookies.py -H 'Cookie: k=v; ...'  # from raw header\n"
               "  python retrieve_cookies.py --validate              # check existing cookies\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--browser", "-b",
        choices=["chrome", "firefox", "edge", "chromium"],
        help="Extract cookies automatically from this browser",
    )
    parser.add_argument(
        "--paste", "-p",
        action="store_true",
        help="Paste cookies from browser (any format) — default mode",
    )
    parser.add_argument(
        "--file", "-f",
        metavar="PATH",
        help="Import cookies from a file (JSON dict, extension array, or header string)",
    )
    parser.add_argument(
        "--header", "-H",
        metavar="STRING",
        help="Parse a raw 'Cookie: ...' header string",
    )
    parser.add_argument(
        "--validate", "-v",
        action="store_true",
        help="Validate existing cookies.json without overwriting",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="PATH",
        default=COOKIES_FILE,
        help="Output path for cookies file (default: %s)" % COOKIES_FILE,
    )
    args = parser.parse_args()

    if args.validate:
        if not os.path.isfile(args.output):
            print("No cookies file found at %s" % args.output)
            sys.exit(1)
        try:
            with open(args.output) as f:
                cookies = json.load(f)
        except json.JSONDecodeError as e:
            print("Error: cookies file is corrupted: %s" % e)
            print("Re-extract with: python retrieve_cookies.py")
            sys.exit(1)
        is_valid, warnings = validate_cookies(cookies)
        for w in warnings:
            print("  WARNING: %s" % w)
        if is_valid:
            print("Cookies look valid (%d cookies)." % len(cookies))
        else:
            print("Cookies may be invalid or incomplete. Re-extract with: python retrieve_cookies.py")
            sys.exit(1)
        return

    modes = [args.paste, args.browser, args.file, args.header]
    if sum(bool(m) for m in modes) > 1:
        parser.error("specify only one of --paste, --browser, --file, --header")

    if args.file:
        cookies = from_file(args.file)
    elif args.header:
        cookies = from_header(args.header)
    elif args.browser:
        cookies = from_browser(args.browser)
    else:
        cookies = from_paste()

    cookies = _normalize_cookies(cookies)

    if not cookies:
        print("No cookies found. Make sure you're logged in at https://learning.oreilly.com")
        sys.exit(1)

    is_valid, warnings = validate_cookies(cookies)
    for w in warnings:
        print("  WARNING: %s" % w)

    _save_cookies(cookies, args.output)

    if is_valid:
        print("Cookies look valid.")
    else:
        print("Cookies saved but may be incomplete — check the warnings above.")


if __name__ == "__main__":
    main()
