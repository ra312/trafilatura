# # pylint:disable-msg=E0611,I1101
# """
# All functions related to XML generation, processing and validation.
# """


from html import unescape
from typing import List, Optional
import logging
from lxml.etree import   _Element

from importlib.metadata import version

from .utils import (
    is_element_in_item,
    is_first_element_in_item,
    is_in_table_cell,
    is_last_element_in_cell,
    is_last_element_in_item,
    sanitize,
    text_chars_test,
)

MAX_TABLE_WIDTH = 1000
LOGGER = logging.getLogger(__name__)
PKG_VERSION = version("trafilatura")

NEWLINE_ELEMS = {"graphic", "head", "lb", "list", "p", "quote", "row", "table"}
SPECIAL_FORMATTING = {"code", "del", "head", "hi", "ref", "item", "cell"}

META_ATTRIBUTES = [
    "sitename",
    "title",
    "author",
    "date",
    "url",
    "hostname",
    "description",
    "categories",
    "tags",
    "license",
    "id",
    "fingerprint",
    "language",
]

HI_FORMATTING = {"#b": "**", "#i": "*", "#u": "__", "#t": "`"}


# # https://github.com/lxml/lxml/blob/master/src/lxml/html/__init__.py
def delete_element(element: _Element, keep_tail: bool = True) -> None:
    """
    Removes this element from the tree, including its children and
    text. The tail text is joined to the previous element or parent.
    """
    parent = element.getparent()
    if parent is None:
        return

    if keep_tail and element.tail:
        previous = element.getprevious()
        if previous is None:
            parent.text = (parent.text or "") + element.tail
        else:
            previous.tail = (previous.tail or "") + element.tail

    parent.remove(element)



def replace_element_text(element: _Element, include_formatting: bool) -> str:
    """Determine element text based on just the text of the element. One must deal with the tail separately."""
    elem_text = element.text or ""
    # handle formatting: convert to markdown
    if include_formatting and element.text:
        if element.tag in ("article", "list", "table"):
            elem_text = elem_text.strip()
        elif element.tag == "head":
            try:
                number = int(element.get("rend")[1])  # type: ignore[index]
            except (TypeError, ValueError):
                number = 2
            elem_text = f'{"#" * number} {elem_text}'
        elif element.tag == "del":
            elem_text = f"~~{elem_text}~~"
        elif element.tag == "hi":
            rend = element.get("rend")
            if rend in HI_FORMATTING:
                elem_text = (
                    f"{HI_FORMATTING[rend]}{elem_text}{HI_FORMATTING[rend]}"
                )
        elif element.tag == "code":
            if "\n" in elem_text or element.xpath(
                ".//lb"
            ):  # Handle <br> inside <code>
                # Convert <br> to \n within code blocks
                for lb in element.xpath(".//lb"):
                    elem_text = f'{elem_text}\n{lb.tail or ""}'
                    lb.getparent().remove(lb)
                elem_text = f"```\n{elem_text}\n```\n"
            else:
                elem_text = f"`{elem_text}`"
    # handle links
    if element.tag == "ref":
        if elem_text:
            link_text = f"[{elem_text}]"
            target = element.get("target")
            if target:
                elem_text = f"{link_text}({target})"
            else:
                LOGGER.warning(
                    "missing link attribute: %s %s'", elem_text, element.attrib
                )
                elem_text = link_text
        else:
            LOGGER.warning("empty link: %s %s", elem_text, element.attrib)
    # cells
    if element.tag == "cell":
        elem_text = elem_text.strip()

        if elem_text and not is_last_element_in_cell(element):
            elem_text = f"{elem_text} "

    # within lists
    if is_first_element_in_item(element) and not is_in_table_cell(element):
        elem_text = f"- {elem_text}"

    return elem_text


def process_element(
    element: _Element, returnlist: List[str], include_formatting: bool
) -> None:
    "Recursively convert a LXML element and its children to a flattened string representation."
    if element.tag == "cell" and element.getprevious() is None:
        returnlist.append("| ")

    if element.text:
        # this is the text that comes before the first child
        returnlist.append(replace_element_text(element, include_formatting))

    if element.tail and element.tag != "graphic" and is_in_table_cell(element):
        # if element is in table cell, append tail after element text when element is not graphic since we deal with
        # graphic tail alone, textless elements like lb should be processed here too, otherwise process tail at the end
        returnlist.append(element.tail.strip())

    for child in element:
        process_element(child, returnlist, include_formatting)

    if not element.text:
        if element.tag == "graphic":
            # add source, default to ''
            text = f'{element.get("title", "")} {element.get("alt", "")}'
            returnlist.append(f'![{text.strip()}]({element.get("src", "")})')

            if element.tail:
                returnlist.append(f" {element.tail.strip()}")
        # newlines for textless elements
        elif element.tag in NEWLINE_ELEMS:
            # add line after table head
            if element.tag == "row":
                cell_count = len(element.xpath(".//cell"))
                # restrict columns to a maximum of 1000
                span_info = element.get("colspan") or element.get("span")
                if not span_info or not span_info.isdigit():
                    max_span = 1
                else:
                    max_span = min(int(span_info), MAX_TABLE_WIDTH)
                # row ended so draw extra empty cells to match max_span
                if cell_count < max_span:
                    returnlist.append(f'{"|" * (max_span - cell_count)}\n')
                # if this is a head row, draw the separator below
                if element.xpath("./cell[@role='head']"):
                    returnlist.append(f'\n|{"---|" * max_span}\n')
            else:
                returnlist.append("\n")
        elif element.tag != "cell" and element.tag != "item":
            # cells still need to append vertical bars
            # but nothing more to do with other textless elements
            return

    # Process text

    # Common elements (Now processes end-tag logic correctly)
    if (
        element.tag in NEWLINE_ELEMS
        and not element.xpath("ancestor::cell")
        and not is_element_in_item(element)
    ):
        # spacing hack
        returnlist.append(
            "\n\u2424\n"
            if include_formatting and element.tag != "row"
            else "\n"
        )
    elif element.tag == "cell":
        returnlist.append(" | ")
    elif element.tag not in SPECIAL_FORMATTING and not is_last_element_in_cell(
        element
    ):  #  and not is_in_table_cell(element)
        returnlist.append(" ")

    # this is text that comes after the closing tag, so it should be after any NEWLINE_ELEMS
    # unless it's within a list item or a table
    is_in_cell = is_in_table_cell(element)
    if element.tail and not is_in_cell:
        returnlist.append(
            element.tail.strip()
            if is_element_in_item(element) or element.tag == "list"
            else element.tail
        )

    # deal with list items alone
    if is_last_element_in_item(element) and not is_in_cell:
        returnlist.append("\n")


def xmltotxt(xmloutput: Optional[_Element], include_formatting: bool) -> str:
    "Convert to plain text format and optionally preserve formatting as markdown."
    if xmloutput is None:
        return ""

    returnlist: List[str] = []

    process_element(xmloutput, returnlist, include_formatting)

    return unescape(sanitize("".join(returnlist), True) or "")
