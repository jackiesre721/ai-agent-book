#!/usr/bin/env python3
"""Flatten an EPUB table of contents within each chapter group."""

import copy
import os
import sys
import tempfile
import zipfile
from xml.etree import ElementTree as ET


XHTML = "http://www.w3.org/1999/xhtml"
EPUB = "http://www.idpf.org/2007/ops"
NCX = "http://www.daisy.org/z3986/2005/ncx/"

ET.register_namespace("", XHTML)
ET.register_namespace("epub", EPUB)


def direct_children(element, tag):
    return [child for child in element if child.tag == tag]


def toc_item(identifier, href, label):
    item = ET.Element(f"{{{XHTML}}}li", {"id": identifier})
    link = ET.SubElement(item, f"{{{XHTML}}}a", {"href": href})
    link.text = label
    return item


def flatten_nav(data, title_label, toc_label):
    root = ET.fromstring(data)
    nav = next(
        element
        for element in root.iter(f"{{{XHTML}}}nav")
        if element.get(f"{{{EPUB}}}type") == "toc"
    )
    top_list = next(child for child in nav if child.tag == f"{{{XHTML}}}ol")
    top_list.insert(0, toc_item("toc-li-contents", "nav.xhtml#toc", toc_label))
    top_list.insert(0, toc_item("toc-li-title-page", "text/title_page.xhtml", title_label))

    for group in direct_children(top_list, f"{{{XHTML}}}li"):
        classes = group.get("class", "").split()
        if "chapter-group" not in classes:
            classes.append("chapter-group")
        group.set("class", " ".join(classes))

        nested_lists = direct_children(group, f"{{{XHTML}}}ol")
        if not nested_lists:
            continue

        descendants = []
        for nested_list in nested_lists:
            descendants.extend(nested_list.iter(f"{{{XHTML}}}li"))
            group.remove(nested_list)

        flat_list = ET.Element(f"{{{XHTML}}}ol", {"class": "toc"})
        for descendant in descendants:
            flat_item = copy.deepcopy(descendant)
            for child in direct_children(flat_item, f"{{{XHTML}}}ol"):
                flat_item.remove(child)
            flat_list.append(flat_item)
        group.append(flat_list)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def flatten_ncx(data, title_label, toc_label):
    ET.register_namespace("", NCX)
    root = ET.fromstring(data)
    nav_map = root.find(f"{{{NCX}}}navMap")

    title_point = None
    for point in direct_children(nav_map, f"{{{NCX}}}navPoint"):
        content = point.find(f"{{{NCX}}}content")
        if content is not None and content.get("src") == "text/title_page.xhtml":
            title_point = point
            label = point.find(f"{{{NCX}}}navLabel/{{{NCX}}}text")
            label.text = title_label
            break

    contents_point = ET.Element(f"{{{NCX}}}navPoint", {"id": "navPoint-contents"})
    contents_label = ET.SubElement(contents_point, f"{{{NCX}}}navLabel")
    ET.SubElement(contents_label, f"{{{NCX}}}text").text = toc_label
    ET.SubElement(contents_point, f"{{{NCX}}}content", {"src": "nav.xhtml#toc"})
    insertion_index = list(nav_map).index(title_point) + 1 if title_point is not None else 0
    nav_map.insert(insertion_index, contents_point)

    for group in direct_children(nav_map, f"{{{NCX}}}navPoint"):
        children = direct_children(group, f"{{{NCX}}}navPoint")
        if not children:
            continue

        descendants = []
        for child in children:
            descendants.extend(child.iter(f"{{{NCX}}}navPoint"))
            group.remove(child)

        for descendant in descendants:
            flat_point = copy.deepcopy(descendant)
            for child in direct_children(flat_point, f"{{{NCX}}}navPoint"):
                flat_point.remove(child)
            group.append(flat_point)

    depth = root.find(f".//{{{NCX}}}meta[@name='dtb:depth']")
    if depth is not None:
        depth.set("content", "2")

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def rewrite_epub(path, title_label, toc_label):
    replacements = {}
    with zipfile.ZipFile(path) as source:
        names = set(source.namelist())
        if "EPUB/nav.xhtml" not in names or "EPUB/toc.ncx" not in names:
            raise RuntimeError("EPUB navigation files not found")
        replacements["EPUB/nav.xhtml"] = flatten_nav(
            source.read("EPUB/nav.xhtml"), title_label, toc_label
        )
        replacements["EPUB/toc.ncx"] = flatten_ncx(
            source.read("EPUB/toc.ncx"), title_label, toc_label
        )

        directory = os.path.dirname(os.path.abspath(path))
        descriptor, temporary_path = tempfile.mkstemp(suffix=".epub", dir=directory)
        os.close(descriptor)
        try:
            with zipfile.ZipFile(temporary_path, "w") as target:
                for info in source.infolist():
                    target.writestr(info, replacements.get(info.filename, source.read(info.filename)))
            os.replace(temporary_path, path)
        except BaseException:
            os.unlink(temporary_path)
            raise


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(f"Usage: {sys.argv[0]} BOOK.epub TITLE_LABEL TOC_LABEL")
    rewrite_epub(sys.argv[1], sys.argv[2], sys.argv[3])
