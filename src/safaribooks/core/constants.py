"""URL constants, HTTP headers, and HTML/EPUB templates for safaribooks."""

# ---------------------------------------------------------------------------
# Host and URL constants
# ---------------------------------------------------------------------------
ORLY_BASE_HOST = "oreilly.com"
SAFARI_BASE_HOST = "learning." + ORLY_BASE_HOST
API_ORIGIN_HOST = "api." + ORLY_BASE_HOST

ORLY_BASE_URL = "https://www." + ORLY_BASE_HOST
SAFARI_BASE_URL = "https://" + SAFARI_BASE_HOST
API_ORIGIN_URL = "https://" + API_ORIGIN_HOST
PROFILE_URL = SAFARI_BASE_URL + "/profile/"

# ---------------------------------------------------------------------------
# API URL templates (use str.format with book_id)
# ---------------------------------------------------------------------------
LOGIN_URL = ORLY_BASE_URL + "/member/auth/login/"
LOGIN_ENTRY_URL = SAFARI_BASE_URL + "/login/unified/?next=/home/"

API_TEMPLATE = SAFARI_BASE_URL + "/api/v2/epubs/urn:orm:book:{0}/"
CHAPTERS_API_TEMPLATE = SAFARI_BASE_URL + "/api/v2/epub-chapters/?epub_identifier=urn:orm:book:{0}"
SEARCH_API_TEMPLATE = SAFARI_BASE_URL + "/api/v2/search/?query={0}&limit=1&formats=book"
SEARCH_QUERY_TEMPLATE = SAFARI_BASE_URL + "/api/v2/search/?query={query}&limit={limit}&formats=book"
FILES_API_TEMPLATE = SAFARI_BASE_URL + "/api/v2/epubs/urn:orm:book:{0}/files"

# ---------------------------------------------------------------------------
# Default HTTP headers
# ---------------------------------------------------------------------------
HEADERS: dict[str, str] = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Encoding": "gzip, deflate",
    "Referer": LOGIN_ENTRY_URL,
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

# ---------------------------------------------------------------------------
# Cookie authentication
# ---------------------------------------------------------------------------
REQUIRED_COOKIES: frozenset[str] = frozenset({
    "groot_sessionid",
    "jwt",
    "csrf_access_token",
    "logged_in",
})

BROWSER_JS: str = (
    "// Run this in your browser console on https://learning.oreilly.com:\n"
    "JSON.stringify(document.cookie.split(';').reduce((o,c) => "
    "{ c=c.trim(); let i=c.indexOf('='); "
    "o[c.substring(0,i)]=c.substring(i+1); return o; }, {}))"
)

# ---------------------------------------------------------------------------
# HTML templates for EPUB generation
# ---------------------------------------------------------------------------
BASE_01_HTML = (
    "<!DOCTYPE html>\n"
    '<html lang="en" xml:lang="en" xmlns="http://www.w3.org/1999/xhtml"'
    ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    ' xsi:schemaLocation="http://www.w3.org/2002/06/xhtml2/'
    ' http://www.w3.org/MarkUp/SCHEMA/xhtml2.xsd"'
    ' xmlns:epub="http://www.idpf.org/2007/ops">\n'
    "<head>\n"
    "{0}\n"
    '<style type="text/css">'
    "body{{margin:1em;background-color:transparent!important;}}"
    "#sbo-rt-content *{{text-indent:0pt!important;}}"
    "#sbo-rt-content .bq{{margin-right:1em!important;}}"
)

KINDLE_HTML = (
    "#sbo-rt-content *{{word-wrap:break-word!important;"
    "word-break:break-word!important;}}"
    "#sbo-rt-content table,#sbo-rt-content pre"
    "{{overflow-x:unset!important;overflow:unset!important;"
    "overflow-y:unset!important;white-space:pre-wrap!important;}}"
)

BASE_02_HTML = "</style></head>\n<body>{1}</body>\n</html>"

CONTAINER_XML = (
    '<?xml version="1.0"?>'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    "<rootfiles>"
    '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml" />'
    "</rootfiles>"
    "</container>"
)

# Format placeholders:
#   {0} ID, {1} Title, {2} Authors, {3} Description, {4} Subjects,
#   {5} Publisher, {6} Rights, {7} Date, {8} CoverId,
#   {9} MANIFEST, {10} SPINE, {11} CoverUrl
CONTENT_OPF = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="2.0" >\n'
    '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"'
    ' xmlns:opf="http://www.idpf.org/2007/opf">\n'
    "<dc:title>{1}</dc:title>\n"
    "{2}\n"
    "<dc:description>{3}</dc:description>\n"
    "{4}"
    "<dc:publisher>{5}</dc:publisher>\n"
    "<dc:rights>{6}</dc:rights>\n"
    "<dc:language>en-US</dc:language>\n"
    "<dc:date>{7}</dc:date>\n"
    '<dc:identifier id="bookid">{0}</dc:identifier>\n'
    '<meta name="cover" content="{8}"/>\n'
    "</metadata>\n"
    "<manifest>\n"
    '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />\n'
    "{9}\n"
    "</manifest>\n"
    '<spine toc="ncx">\n{10}</spine>\n'
    '<guide><reference href="{11}" title="Cover" type="cover" /></guide>\n'
    "</package>"
)

# Format placeholders:
#   {0} ID, {1} Depth, {2} Title, {3} Author, {4} NAVMAP
TOC_NCX = (
    '<?xml version="1.0" encoding="utf-8" standalone="no" ?>\n'
    '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN"'
    ' "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">\n'
    '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
    "<head>\n"
    '<meta content="ID:ISBN:{0}" name="dtb:uid"/>\n'
    '<meta content="{1}" name="dtb:depth"/>\n'
    '<meta content="0" name="dtb:totalPageCount"/>\n'
    '<meta content="0" name="dtb:maxPageNumber"/>\n'
    "</head>\n"
    "<docTitle><text>{2}</text></docTitle>\n"
    "<docAuthor><text>{3}</text></docAuthor>\n"
    "<navMap>{4}</navMap>\n"
    "</ncx>"
)
