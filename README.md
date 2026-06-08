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

  * **Quick way (browser console):** Open DevTools (F12) → Console tab → paste this snippet → copy the output → save it as `cookies.json` in the project directory:
    ```javascript
    JSON.stringify(document.cookie.split(';').reduce((o,c) => {
      c = c.trim(); let i = c.indexOf('=');
      o[c.substring(0, i)] = c.substring(i + 1); return o;
    }, {}))
    ```

  * **Paste mode (default):** Run `python retrieve_cookies.py` — it will prompt you to paste the JSON output from the browser console snippet above.

  * **Auto-extract from browser:** Run `python retrieve_cookies.py -b chrome` (also supports `firefox`, `edge`, `chromium`). Requires the `browser_cookie3` package (`pip install browser_cookie3`).

Both script modes write `cookies.json` automatically.

> **Note:** If you use a shared PC, anyone with access to `cookies.json` can use your session. Delete it when you're done.

## Usage:

**Step 1:** Extract your cookies (see [Getting Cookies](#getting-cookies) above).

**Step 2:** Find the book ID — it's the digits in the URL of the book page:  
`https://learning.oreilly.com/library/view/book-name/XXXXXXXXXXXXX/`  
For example: `https://learning.oreilly.com/library/view/test-driven-development-with/9781491958698/`

**Step 3:** Run:
```shell
$ python3 safaribooks.py XXXXXXXXXXXXX
```

#### Program options:
```shell
$ python3 safaribooks.py --help
usage: safaribooks.py [--kindle] [--preserve-log] [--help]
                      <BOOK ID>

Download and generate an EPUB of your favorite books from Safari Books Online.

positional arguments:
  <BOOK ID>            Book digits ID that you want to download. You can find
                       it in the URL (X-es):
                       `https://learning.oreilly.com/library/view/book-
                       name/XXXXXXXXXXXXX/`

optional arguments:
  --kindle             Add some CSS rules that block overflow on `table` and
                       `pre` elements. Use this option if you're going to
                       export the EPUB to E-Readers like Amazon Kindle.
  --preserve-log       Leave the `info_XXXXXXXXXXXXX.log` file even if there
                       isn't any error.
  --help               Show this help message.

deprecated (no longer functional):
  --cred <EMAIL:PASS>  No longer works. Use cookies.json instead.
  --login              No longer works. Use cookies.json instead.
  --no-cookies         No longer relevant with cookie-based auth.
```

You can configure proxies by setting the environment variable `HTTPS_PROXY` or using the `USE_PROXY` directive in the script.

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
        e don’t forget to renew your Safari Books Online subscription:
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
  
## Thanks!!
For any kind of problem, please don't hesitate to open an issue here on *GitHub*.  
  
*Lorenzo Di Fuccia*
