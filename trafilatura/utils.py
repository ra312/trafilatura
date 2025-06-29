# pylint:disable-msg=E0611,I1101
"""
Module bundling functions related to HTML and text processing,
content filtering and language detection.
"""

import logging
import re


from functools import lru_cache
from itertools import islice
from typing import Any, cast, Literal, Optional
from unicodedata import normalize


from lxml.etree import _Element
from lxml.html import HtmlElement, HTMLParser, fromstring



LOGGER = logging.getLogger(__name__)

UNICODE_ALIASES = {"utf-8", "utf_8"}

DOCTYPE_TAG = re.compile("^< ?! ?DOCTYPE[^>]*/[^<]*>", re.I)
FAULTY_HTML = re.compile(r"(<html.*?)\s*/>", re.I)
HTML_STRIP_TAGS = re.compile(r"(<!--.*?-->|<[^>]*>)")

# note: htmldate could use HTML comments
# huge_tree=True, remove_blank_text=True
HTML_PARSER = HTMLParser(
    collect_ids=False,
    default_doctype=False,
    encoding="utf-8",
    remove_comments=True,
    remove_pis=True,
)

LINES_TRIMMING = re.compile(r"(?<![p{P}>])\n", flags=re.UNICODE | re.MULTILINE)

URL_BLACKLIST_REGEX = re.compile(r"^https?://|/+$")

# Regex to check image file extensions
IMAGE_EXTENSION = re.compile(
    r"[^\s]+\.(avif|bmp|gif|hei[cf]|jpe?g|png|webp)(\b|$)"
)

FORMATTING_PROTECTED = {
    "cell",
    "head",
    "hi",
    "item",
    "p",
    "quote",
    "ref",
    "td",
}
SPACING_PROTECTED = {"code", "pre"}

# https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Language
# TARGET_LANG_ATTRS = ('http-equiv="content-language"', 'property="og:locale"')
# RE_HTML_LANG = re.compile(r'([a-z]{2})')

# Mostly filters for social media
RE_FILTER = re.compile(
    r"\W*(Drucken|E-?Mail|Facebook|Flipboard|Google|Instagram|"
    "Linkedin|Mail|PDF|Pinterest|Pocket|Print|QQ|Reddit|Twitter|"
    "WeChat|WeiBo|Whatsapp|Xing|Mehr zum Thema:?|More on this.{,8}$)$",
    flags=re.IGNORECASE,
)
# COMMENTS_BLACKLIST = ('( Abmelden / Ändern )') # Fill in your details below|Trage deine Daten unten|Kommentar verfassen|Bitte logge dich|Hinterlasse einen Kommentar| to %s| mit %s)


def isutf8(data: bytes) -> bool:
    """Simple heuristic to determine if a bytestring uses standard unicode encoding"""
    try:
        data.decode("UTF-8")
    except UnicodeDecodeError:
        return False
    return True


# def detect_encoding(bytesobject: bytes) -> List[str]:
#     """ "Read all input or first chunk and return a list of encodings"""
#     # alternatives: https://github.com/scrapy/w3lib/blob/master/w3lib/encoding.py
#     # unicode-test
#     if isutf8(bytesobject):
#         return ["utf-8"]
#     guesses = []
#     # additional module
#     if cchardet_detect is not None:
#         cchardet_guess = cchardet_detect(bytesobject)["encoding"]
#         if cchardet_guess is not None:
#             guesses.append(cchardet_guess.lower())
#     # try charset_normalizer on first part, fallback on full document
#     if len(bytesobject) < 10000:
#         detection_results = from_bytes(bytesobject)
#     else:
#         detection_results = from_bytes(
#             bytesobject[:5000] + bytesobject[-5000:]
#         ) or from_bytes(bytesobject)
#     # return alternatives
#     if len(detection_results) > 0:
#         guesses.extend([r.encoding for r in detection_results])
#     # it cannot be utf-8 (tested above)
#     return [g for g in guesses if g not in UNICODE_ALIASES]


# def decode_file(filecontent: Union[bytes, str]) -> str:
#     """Check if the bytestring could be GZip and eventually decompress it,
#        guess bytestring encoding and try to decode to Unicode string.
#        Resort to destructive conversion otherwise."""
#     if isinstance(filecontent, str):
#         return filecontent

#     htmltext = None

#     # GZip and Brotli test
#     # filecontent = handle_compressed_file(filecontent)
#     # encoding
#     for guessed_encoding in detect_encoding(filecontent):
#         try:
#             htmltext = filecontent.decode(guessed_encoding)
#         except (LookupError, UnicodeDecodeError): # VISCII: lookup
#             LOGGER.warning('wrong encoding detected: %s', guessed_encoding)
#             htmltext = None
#         else:
#             break

#     # return original content if nothing else succeeded
#     return htmltext or str(filecontent, encoding='utf-8', errors='replace')


def is_dubious_html(beginning: str) -> bool:
    "Assess if the object is proper HTML (awith a corresponding tag or declaration)."
    return "html" not in beginning


def repair_faulty_html(htmlstring: str, beginning: str) -> str:
    "Repair faulty HTML strings to make then palatable for libxml2."
    # libxml2/LXML issue: https://bugs.launchpad.net/lxml/+bug/1955915
    if "doctype" in beginning:
        firstline, _, rest = htmlstring.partition("\n")
        htmlstring = DOCTYPE_TAG.sub("", firstline, count=1) + "\n" + rest
    # other issue with malformed documents: check first three lines
    for i, line in enumerate(iter(htmlstring.splitlines())):
        if "<html" in line and line.endswith("/>"):
            htmlstring = FAULTY_HTML.sub(r"\1>", htmlstring, count=1)
            break
        if i > 2:
            break
    return htmlstring


def fromstring_bytes(htmlobject: str) -> Optional[HtmlElement]:
    "Try to pass bytes to LXML parser."
    tree = None
    try:
        tree = fromstring(
            htmlobject.encode("utf8", "surrogatepass"), parser=HTML_PARSER
        )
    except Exception as err:
        LOGGER.error("lxml parser bytestring %s", err)
    return tree


def load_html(htmlobject: Any) -> Optional[HtmlElement]:
    """Load object given as input and validate its type
    (accepted: lxml.html tree, trafilatura/urllib3 response, bytestring and string)
    """
    if isinstance(htmlobject, HtmlElement):
        return htmlobject
    if not isinstance(htmlobject, (bytes, str)):
        raise TypeError("incompatible input type", type(htmlobject))
    tree = None
    beginning = htmlobject[:50].lower()
    check_flag = is_dubious_html(beginning)
    htmlobject = repair_faulty_html(htmlobject, beginning)
    fallback_parse = False
    try:
        tree = fromstring(htmlobject, parser=HTML_PARSER)
    except ValueError:
        tree = fromstring_bytes(htmlobject)
        fallback_parse = True
    except Exception as err:  # pragma: no cover
        LOGGER.error("lxml parsing failed: %s", err)
    if (tree is None or len(tree) < 1) and not fallback_parse:
        tree = fromstring_bytes(htmlobject)
    if tree is not None and check_flag is True and len(tree) < 2:
        LOGGER.error(
            "parsed tree length: %s, wrong data type or not valid HTML",
            len(tree),
        )
        tree = None
    return tree


@lru_cache(maxsize=2**14)
def return_printables_and_spaces(char: str) -> str:
    "Return a character if it belongs to certain classes"
    return char if char.isprintable() or char.isspace() else ""


def remove_control_characters(string: str) -> str:
    """Prevent non-printable and XML invalid character errors"""
    return "".join(map(return_printables_and_spaces, string))


def normalize_unicode(
    string: str, unicodeform: Literal["NFC", "NFD", "NFKC", "NFKD"] = "NFC"
) -> str:
    "Normalize the given string to the specified unicode format."
    return normalize(unicodeform, string)


@lru_cache(maxsize=1024)
def line_processing(
    line: str, preserve_space: bool = False, trailing_space: bool = False
) -> Optional[str]:
    """Remove HTML space entities, then discard incompatible unicode
    and invalid XML characters on line level"""
    # spacing HTML entities: https://www.w3.org/MarkUp/html-spec/html-spec_13.html
    # unique code spaces
    new_line = remove_control_characters(
        line.replace("&#13;", "\r")
        .replace("&#10;", "\n")
        .replace("&nbsp;", "\u00A0")
    )
    if not preserve_space:
        # remove newlines that are not related to punctuation or markup
        # remove non-printable chars and normalize space characters (including Unicode spaces)
        new_line = trim(LINES_TRIMMING.sub(r" ", new_line))
        # prune empty lines
        if all(map(str.isspace, new_line)):
            new_line = None  # type: ignore[assignment]
        elif trailing_space:
            space_before = " " if line[0].isspace() else ""
            space_after = " " if line[-1].isspace() else ""
            new_line = "".join([space_before, new_line, space_after])
    return new_line


def sanitize(
    text: str, preserve_space: bool = False, trailing_space: bool = False
) -> Optional[str]:
    """Convert text and discard incompatible and invalid characters"""
    # consider all text as a single line
    if trailing_space:
        return line_processing(text, preserve_space, True)
    # process line by line
    try:
        return "\n".join(
            filter(
                None,
                (
                    line_processing(l, preserve_space)
                    for l in text.splitlines()
                ),
            )
        ).replace("\u2424", "")
    except AttributeError:
        return None


def sanitize_tree(tree: _Element) -> _Element:
    """Trims spaces, removes control characters and normalizes unicode"""
    for elem in tree.iter():
        parent = elem.getparent()
        parent_tag = parent.tag if parent is not None else ""

        # preserve space if the element or its parent is a specific tag, or if the element has text and children
        # the last part is relevant for item elements with ref inside for example
        preserve_space = (
            elem.tag in SPACING_PROTECTED or parent_tag in SPACING_PROTECTED
        )
        trailing_space = (
            elem.tag in FORMATTING_PROTECTED
            or parent_tag in FORMATTING_PROTECTED
            or preserve_space
        )

        # remove invalid attributes
        for attribute in elem.attrib:
            if ":" in attribute:  # colon is reserved for namespaces in XML
                if (
                    not elem.attrib[attribute]
                    or attribute.split(":", 1)[0] not in tree.nsmap
                ):
                    elem.attrib.pop(attribute)

        if elem.text:
            elem.text = sanitize(elem.text, preserve_space, trailing_space)
        if elem.tail:
            elem.tail = sanitize(elem.tail, preserve_space, trailing_space)
    return tree


@lru_cache(maxsize=1024)
def trim(string: str) -> str:
    "Remove unnecessary spaces within a text string."
    try:
        # remove newlines that are not related to punctuation or markup + proper trimming
        return " ".join(string.split()).strip()
    except (AttributeError, TypeError):
        return ""


def is_image_element(element: _Element) -> bool:
    """Check if an element is a valid img element"""
    for attr in ("data-src", "src"):
        src = element.get(attr, "")
        if is_image_file(src):
            return True
    else:
        # take the first corresponding attribute
        for attr, value in element.attrib.items():
            if attr.startswith("data-src") and is_image_file(value):
                return True
    return False


def is_image_file(imagesrc: Optional[str]) -> bool:
    """Check if the observed string corresponds to a valid image extension.
    Use a length threshold and apply a regex on the content."""
    if imagesrc is None or len(imagesrc) > 8192:
        return False
    return bool(IMAGE_EXTENSION.search(imagesrc))


def make_chunks(iterable: Any, n: int) -> Any:
    "Chunk data into smaller pieces."
    # 3.12+: https://docs.python.org/3/library/itertools.html#itertools.batched
    iterator = iter(iterable)
    while batch := tuple(islice(iterator, n)):
        yield batch


# def is_acceptable_length(my_len: int, options: Any) -> bool:
#     "Check if the document length is within acceptable boundaries."
#     if my_len < options.min_file_size:
#         LOGGER.error("too small/incorrect for URL %s", options.url)
#         return False
#     if my_len > options.max_file_size:
#         LOGGER.error("too large: length %s for URL %s", my_len, options.url)
#         return False
#     return True


def textfilter(element: _Element) -> bool:
    """Filter out unwanted text"""
    testtext = element.tail if element.text is None else element.text
    # to check: line len → continue if len(line) <= 5
    return (
        not testtext
        or testtext.isspace()
        or any(map(RE_FILTER.match, testtext.splitlines()))
    )


def text_chars_test(string: Optional[str]) -> bool:
    """Determine if a string is only composed of spaces and/or control characters"""
    # or not re.search(r'\w', string)
    # return string is not None and len(string) != 0 and not string.isspace()
    return bool(string) and not string.isspace()  # type: ignore[union-attr]


def copy_attributes(dest_elem: _Element, src_elem: _Element) -> None:
    """Copy attributes from src element to dest element"""
    for key in src_elem.keys():
        dest_elem.set(key, src_elem.attrib[key])


def is_in_table_cell(elem: _Element) -> bool:
    """Check whether an element is in a table cell"""
    # return elem.getparent() is not None and bool(elem.xpath('//ancestor::cell'))
    if elem.getparent() is None:
        return False
    current: Optional[_Element] = elem
    while current is not None:
        if current.tag == "cell":
            return True
        current = current.getparent()
    return False


def is_last_element_in_cell(elem: _Element) -> bool:
    """Check whether an element is the last element in table cell"""
    if not is_in_table_cell(elem):  # shortcut
        return False

    if elem.tag == "cell":
        children = elem.getchildren()
        return not children or children[-1] == elem
    else:
        parent = cast(_Element, elem.getparent())
        children = parent.getchildren()
        return not children or children[-1] == elem


def is_element_in_item(element: _Element) -> bool:
    """Check whether an element is a list item or within a list item"""
    current: Optional[_Element] = element
    while current is not None:
        if current.tag == "item":
            return True
        current = current.getparent()
    return False


def is_first_element_in_item(element: _Element) -> bool:
    """Check whether an element is the first element in list item"""
    if element.tag == "item" and element.text:
        return True

    current: Optional[_Element] = element
    item_ancestor = None
    while current is not None:
        if current.tag == "item":
            item_ancestor = current
            break
        current = current.getparent()

    if item_ancestor is None:
        return False
    elif not item_ancestor.text:
        return True
    return False


def is_last_element_in_item(element: _Element) -> bool:
    """Check whether an element is the last element in list item"""
    if not is_element_in_item(element):
        return False

    # pure text only in list item
    if element.tag == "item":
        return len(element.getchildren()) == 0
    # element within list item
    next_element = element.getnext()
    if next_element is None:
        return True
    else:
        return next_element.tag == "item"
