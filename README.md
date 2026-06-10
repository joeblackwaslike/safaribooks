# SafariBooks
Download and generate *EPUB* of your favorite books from [*Safari Books Online*](https://www.safaribooksonline.com) library.  
I'm not responsible for the use of this program, this is only for *personal* and *educational* purpose.  
Before any usage please read the *O'Reilly*'s [Terms of Service](https://learning.oreilly.com/terms/).  

<a href='https://ko-fi.com/Y8Y0MPEGU' target='_blank'><img height='80' style='border:0px;height:60px;' src='https://storage.ko-fi.com/cdn/kofi6.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com'/></a>

## Note

- Login through `--cred` / `--login` no longer works (O'Reilly blocks programmatic login).
- **Authentication is now cookie-based only.** See [Getting Cookies](#getting-cookies) below.
- The tool has been updated to use O'Reilly's v2 API.

---

## Overview:
  * [Requirements & Setup](#requirements--setup)
  * [Getting Cookies](#getting-cookies)
  * [Usage](#usage)
  * [Calibre EPUB conversion](https://github.com/lorenzodifuccia/safaribooks#calibre-epub-conversion)
  * [Example: Download *Test-Driven Development with Python, 2nd Edition*](#download-test-driven-development-with-python-2nd-edition)
  * [Example: Use or not the `--kindle` option](#use-or-not-the---kindle-option)
  * [Contributors & Credits](docs/CONTRIBUTORS.md)

## Requirements & Setup:
First of all, it requires `python3` and `pip3` or `pipenv` to be installed.  
```shell
$ git clone https://github.com/lorenzodifuccia/safaribooks.git
Cloning into 'safaribooks'...

$ cd safaribooks/
$ pip3 install -r requirements.txt

OR

$ pipenv install && pipenv shell
```  

The program depends of only two **Python _3_** modules:
```python3
lxml>=4.1.1
requests>=2.20.0
```
  
## Getting Cookies

Since O'Reilly blocks programmatic login, you need to extract cookies from your browser session.

**Step 1:** Log in to [https://learning.oreilly.com](https://learning.oreilly.com) in your browser.

**Step 2:** Get your cookies using one of these methods:

### Method 1: Paste Mode (Recommended)

Run the cookie helper and paste output from any of the accepted formats:
```shell
$ python retrieve_cookies.py
```
It auto-detects whether you pasted a JSON dict, a browser extension export, or a raw cookie header — just paste whatever you have.

To get the JSON from your browser: open DevTools (F12) → Console → paste this snippet → copy the output:
```javascript
JSON.stringify(document.cookie.split(';').reduce((o,c) => {
  c = c.trim(); let i = c.indexOf('=');
  o[c.substring(0, i)] = c.substring(i + 1); return o;
}, {}))
```

### Method 2: Raw Cookie Header

Open DevTools → Network tab → pick any request to `learning.oreilly.com` → right-click → **Copy as cURL** → extract the `Cookie:` header value, then:
```shell
$ python retrieve_cookies.py -H 'Cookie: k1=v1; k2=v2; ...'
```

### Method 3: Browser Extension Export

Install a cookie export extension (e.g. EditThisCookie), navigate to `learning.oreilly.com`, export cookies as JSON, then:
```shell
$ python retrieve_cookies.py -f exported_cookies.json
```
The extension's array-of-objects format `[{"name":"k","value":"v",...}]` is auto-detected and converted.

### Method 4: Auto-Extract from Browser

```shell
$ pip install browser_cookie3
$ python retrieve_cookies.py -b chrome
```
Also supports `firefox`, `edge`, `chromium`. The browser should be closed when running this.

### Method 5: Manual `cookies.json`

For advanced users — create `cookies.json` directly in the project directory:
```json
{
  "groot_sessionid": "...",
  "logged_in": "y",
  "orm-jwt": "...",
  "csrf_access_token": "..."
}
```

### Validate Existing Cookies

Check whether your `cookies.json` is still valid:
```shell
$ python retrieve_cookies.py --validate
```

### Troubleshooting

| Problem | Solution |
|---------|----------|
| **"Out-of-Session"** error | Your cookies expired (typically after ~2 hours). Re-extract them. A backup is saved as `cookies.json.expired`. |
| **"No cookies found"** | Make sure you're logged in at learning.oreilly.com before extracting. |
| **Browser auto-extract fails** | Close the browser first, or use paste mode instead. |
| **Download interrupted** | If your session expires mid-download, you'll be prompted to re-extract cookies and press Enter. Already-downloaded chapters are cached. |

> **Security warning:** `cookies.json` contains your active session — treat it like a password.
> Delete it when you're done downloading. Never commit it to git (it's already in `.gitignore`).
> On shared machines, be especially careful — anyone with access to this file can use your O'Reilly session.

## Usage:

**Step 1:** Extract your cookies (see [Getting Cookies](#getting-cookies) above).

**Step 2:** Find the book ID — it's the digits in the URL of the book page:  
`https://learning.oreilly.com/library/view/book-name/XXXXXXXXXXXXX/`  
For example: `https://learning.oreilly.com/library/view/test-driven-development-with/9781491958698/`

**Step 3:** Run:
```shell
$ python3 safaribooks.py XXXXXXXXXXXXX
```

You can also pass a full O'Reilly URL instead of the book ID:
```shell
$ python3 safaribooks.py https://learning.oreilly.com/library/view/test-driven-development-with/9781491958698/
```

#### Download multiple books:
```shell
$ python3 safaribooks.py 9781491958698 9781492056355 9781492078005
```

#### Download all books from a playlist:
```shell
$ python3 safaribooks.py --playlist 6f612b99-bebc-41e1-8fff-6b655507b7af
```

#### Program options:
```shell
$ python3 safaribooks.py --help
usage: safaribooks.py [--kindle] [--preserve-log] [--ssl-skip] [--playlist <PLAYLIST_ID>] [--help]
                      [<BOOK ID> ...]

Download and generate an EPUB of your favorite books from Safari Books Online.

positional arguments:
  <BOOK ID>            Book digits ID(s) that you want to download. You can
                       specify multiple IDs. You can find them in the URL:
                       `https://learning.oreilly.com/library/view/book-
                       name/XXXXXXXXXXXXX/`

optional arguments:
  --kindle             Add some CSS rules that block overflow on `table` and
                       `pre` elements. Use this option if you're going to
                       export the EPUB to E-Readers like Amazon Kindle.
  --preserve-log       Leave the `info_XXXXXXXXXXXXX.log` file even if there
                       isn't any error.
  --ssl-skip           Skip SSL certificate verification. Useful for corporate
                       proxies with MITM certificates.
  --playlist ID        Download all books from a playlist. Provide the playlist UUID.
  --image-max-size N   Resize images if width/height exceeds N pixels (0 = no resize). Requires Pillow.
  --image-quality N    JPEG compression quality 1-95 (0 = keep original). Requires Pillow.
  --help               Show this help message.

deprecated (no longer functional):
  --cred <EMAIL:PASS>  No longer works. Use cookies.json instead.
  --login              No longer works. Use cookies.json instead.
  --no-cookies         No longer relevant with cookie-based auth.
```

You can configure proxies by setting the environment variable `HTTPS_PROXY` or using the `USE_PROXY` directive in the script.

#### Using Docker:
```shell
$ cd safaribooks/
$ docker build . -t safaribooks

# Extract cookies first (on host):
$ python3 retrieve_cookies.py

# Run with Docker:
$ docker run --rm \
    -v $(pwd)/cookies.json:/app/cookies.json \
    -v $(pwd)/Books:/app/Books \
    safaribooks 9781491958698
```

#### Calibre EPUB conversion
**Important**: since the script only download HTML pages and create a raw EPUB, many of the CSS and XML/HTML directives are wrong for an E-Reader. To ensure best quality of the output, I suggest you to always convert the `EPUB` obtained by the script to standard-`EPUB` with [Calibre](https://calibre-ebook.com/).
You can also use the command-line version of Calibre with `ebook-convert`, e.g.:
```bash
$ ebook-convert "XXXX/safaribooks/Books/Test-Driven Development with Python 2nd Edition (9781491958698)/9781491958698.epub" "XXXX/safaribooks/Books/Test-Driven Development with Python 2nd Edition (9781491958698)/9781491958698_CLEAR.epub"
```
After the execution, you can read the `9781491958698_CLEAR.epub` in every E-Reader and delete all other files.

The program offers also an option to ensure best compatibilities for who wants to export the `EPUB` to E-Readers like Amazon Kindle: `--kindle`, it blocks overflow on `table` and `pre` elements (see [example](#use-or-not-the---kindle-option)).  
In this case, I suggest you to convert the `EPUB` to `AZW3` with Calibre or to `MOBI`, remember in this case to select `Ignore margins` in the conversion options:  
  
![Calibre IgnoreMargins](https://github.com/lorenzodifuccia/cloudflare/raw/master/Images/safaribooks/safaribooks_calibre_IgnoreMargins.png "Select Ignore margins")  
  
## Examples:
  * ## Download [Test-Driven Development with Python, 2nd Edition](https://learning.oreilly.com/library/view/test-driven-development-with/9781491958698/):  
    ```shell
    $ python3 safaribooks.py 9781491958698

           ____     ___         _ 
          / __/__ _/ _/__ _____(_)
         _\ \/ _ `/ _/ _ `/ __/ / 
        /___/\_,_/_/ \_,_/_/ /_/  
          / _ )___  ___  / /__ ___
         / _  / _ \/ _ \/  ‘_/(_-<
        /____/\___/\___/_/\_\/___/

    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    [*] Retrieving book info... 
    [-] Title: Test-Driven Development with Python, 2nd Edition                     
    [-] Authors: Harry J.W. Percival                                                
    [-] Identifier: 9781491958698                                                   
    [-] ISBN: 9781491958704                                                         
    [-] Publishers: O’Reilly Media, Inc.                                            
    [-] Rights: Copyright © O’Reilly Media, Inc.                                    
    [-] Description: By taking you through the development of a real web application 
    from beginning to end, the second edition of this hands-on guide demonstrates the 
    practical advantages of test-driven development (TDD) with Python. You’ll learn 
    how to write and run tests before building each part of your app, and then develop
    the minimum amount of code required to pass those tests. The result? Clean code
    that works.In the process, you’ll learn the basics of Django, Selenium, Git, 
    jQuery, and Mock, along with curre...
    [-] Release Date: 2017-08-18
    [-] URL: https://learning.oreilly.com/library/view/test-driven-development-with/9781491958698/
    [*] Retrieving book chapters...                                                 
    [*] Output directory:                                                           
        /XXXX/safaribooks/Books/Test-Driven Development with Python 2nd Edition (9781491958698)
    [-] Downloading book contents... (53 chapters)                                  
        [#####################################################################] 100%
    [-] Downloading book CSSs... (2 files)                                          
        [#####################################################################] 100%
    [-] Downloading book images... (142 files)                                      
        [#####################################################################] 100%
    [-] Creating EPUB file...                                                       
    [*] Done: /XXXX/safaribooks/Books/Test-Driven Development with Python 2nd Edition 
    (9781491958698)/9781491958698.epub
    
        If you like it, please * this project on GitHub to make it known:
            https://github.com/lorenzodifuccia/safaribooks
        And don’t forget to renew your Safari Books Online subscription:
            https://learning.oreilly.com
    
    [!] Bye!!
    ```  
     The result will be (opening the `EPUB` file with Calibre):  

    ![Book Appearance](https://github.com/lorenzodifuccia/cloudflare/raw/master/Images/safaribooks/safaribooks_example01_TDD.png "Book opened with Calibre")  
 
  * ## Use or not the `--kindle` option:
    ```bash
    $ python3 safaribooks.py --kindle 9781491958698
    ```  
    On the right, the book created with `--kindle` option, on the left without (default):  
    
    ![NoKindle Option](https://github.com/lorenzodifuccia/cloudflare/raw/master/Images/safaribooks/safaribooks_example02_NoKindle.png "Version compare")  
    
---  

## Contributors & Credits

This fork was built by synthesizing ideas and code from **20+ community PRs** on the upstream repo. Every contribution was evaluated, and the best approaches were combined into a working v2 migration.

**[View the full contributors page](docs/CONTRIBUTORS.md)** — includes everyone who contributed, what they built, how their work was used, and links to their original PRs.

Implementation plans are preserved in [`docs/plans/`](docs/plans/) for full transparency.

---  
  
## Thanks!!
For any kind of problem, please don't hesitate to open an issue here on *GitHub*.  
  
*Original project by [Lorenzo Di Fuccia](https://github.com/lorenzodifuccia)*
