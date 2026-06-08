import json
import argparse
import sys

try:
    from safaribooks import COOKIES_FILE
except ImportError:
    COOKIES_FILE = "cookies.json"

BROWSER_JS = """
// Run this in your browser console on https://learning.oreilly.com:
JSON.stringify(document.cookie.split(';').reduce((o,c) => { c=c.trim(); let i=c.indexOf('='); o[c.substring(0,i)]=c.substring(i+1); return o; }, {}))
""".strip()


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
    cj = browsers[browser_name](domain_name=".oreilly.com")
    return {c.name: c.value for c in cj}


def from_paste():
    print("Paste the JSON output from your browser console, then press Enter:")
    print("  (Run this in console on learning.oreilly.com: %s)\n" % BROWSER_JS.split('\n')[-1])
    raw = input("> ").strip()
    try:
        if raw.startswith('"') and raw.endswith('"'):
            raw = json.loads(raw)
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as e:
        print("Error: invalid JSON. Make sure you copied the full output from the browser console.")
        print("  Details: %s" % e)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Extract O'Reilly cookies for safaribooks",
        epilog="Examples:\n"
               "  python retrieve_cookies.py --paste\n"
               "  python retrieve_cookies.py -b chrome\n",
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
        help="Paste cookies JSON from browser console (default)",
    )
    args = parser.parse_args()

    if not args.browser and not args.paste:
        args.paste = True

    if args.paste:
        cookies = from_paste()
    else:
        cookies = from_browser(args.browser)

    if not cookies:
        print("No cookies found. Make sure you're logged in at https://learning.oreilly.com")
        sys.exit(1)

    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f, indent=2)

    print("Saved %d cookies to %s" % (len(cookies), COOKIES_FILE))


if __name__ == "__main__":
    main()
