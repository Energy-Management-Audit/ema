"""Schema-ordered pagination flags shared by paragraph formatting callers."""

# pyright: reportPrivateUsage=false

from typing import Literal

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def keep_paragraph(paragraph: etree._Element, tag: Literal["keepNext", "keepLines"]) -> None:
    properties = paragraph.find(W + "pPr")
    if properties is None:
        properties = etree.Element(W + "pPr")
        paragraph.insert(0, properties)
    flag = properties.find(W + tag)
    if flag is None:
        flag = etree.Element(W + tag)
        earlier = {W + "pStyle"}
        if tag == "keepLines":
            earlier.add(W + "keepNext")
        following = next((node for node in properties if node.tag not in earlier), None)
        if following is None:
            properties.append(flag)
        else:
            following.addprevious(flag)
    flag.set(W + "val", "1")
