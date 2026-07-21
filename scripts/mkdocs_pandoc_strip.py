"""MkDocs hook: strip Pandoc-specific attributes before rendering.

The book source uses Pandoc/LaTeX attributes that Python-Markdown does not
understand and would otherwise render as literal text:

    ## 标题 {.unnumbered}        ->  ## 标题
    ![图](x.svg){height=55%}     ->  ![图](x.svg)
    [文本](#sec:foo){.unnumbered}
"""
import re

# Patterns are intentionally strict: they only match real Pandoc attribute
# syntax so that inline code and code blocks (e.g. JSON `{"data": {...}}` or
# JS `catch (e) {...}`) are never touched.
_ID_ATTR = re.compile(r"\{#[\w:.-]+\}")
_CLASS_ATTR = re.compile(r"\{\.[\w-]+(?:\s+\.[\w-]+)*\}")
_TRAILING_ATTR = re.compile(
    r"\)\{(?:#[\w:.-]+|\.[\w-]+(?:\s+\.[\w-]+)*|[\w-]+=[^{}]*)\}"
)


def on_page_markdown(markdown, **kwargs):
    markdown = _ID_ATTR.sub("", markdown)
    markdown = _CLASS_ATTR.sub("", markdown)
    markdown = _TRAILING_ATTR.sub(")", markdown)
    return markdown
