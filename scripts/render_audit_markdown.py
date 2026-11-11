#!/usr/bin/env python3
"""Render a repository audit Markdown document as a standalone HTML report."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from markdown_it import MarkdownIt


TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{--ink:#203340;--muted:#5d6c71;--paper:#faf8f2;--line:#c9d2cf;--navy:#183b60;--teal:#177d80;--orange:#c57625;--soft:#ecf1ed;--high:#176c58;--low:#9c4724}}
*{{box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{margin:0;color:var(--ink);background:var(--paper);font:16px/1.82 "Avenir Next","PingFang SC","Microsoft YaHei",sans-serif}}
header{{padding:52px max(24px,calc((100vw - 1250px)/2)) 36px;border-bottom:4px solid var(--navy);background:#eaf0e9}}
.eyebrow{{font-size:12px;letter-spacing:.15em;color:var(--teal);font-weight:700}}
h1{{font:normal 43px/1.25 Georgia,"Songti SC",serif;margin:14px 0 18px;max-width:1000px}}
.dek{{font-size:19px;max-width:980px;margin:0}}
.meta{{display:flex;flex-wrap:wrap;gap:7px 18px;font-size:12px;color:var(--muted);margin-top:24px}}
.meta span{{white-space:nowrap}}.meta a{{font-weight:700}}
.layout{{display:grid;grid-template-columns:205px minmax(0,1fr);gap:38px;max-width:1370px;padding:30px 24px 76px;margin:auto}}
nav{{position:sticky;top:18px;align-self:start;border-top:2px solid var(--teal);padding-top:12px;font-size:13px}}
nav a{{display:block;padding:5px 0;text-decoration:none}}
main{{min-width:0;counter-reset:section}}
h2{{font:normal 29px/1.3 Georgia,"Songti SC",serif;border-bottom:1px solid var(--ink);padding:0 0 13px;margin:58px 0 24px;scroll-margin-top:24px}}
h2:first-child{{margin-top:10px}}h2::before{{counter-increment:section;content:counter(section,decimal-leading-zero) " · ";color:var(--teal)}}
h3{{font-size:19px;line-height:1.5;margin:28px 0 10px;padding-left:12px;border-left:3px solid var(--orange);scroll-margin-top:24px}}
p{{margin:15px 0}}a{{color:var(--teal);text-underline-offset:3px;overflow-wrap:anywhere}}
code{{font-family:"SFMono-Regular",Consolas,monospace;font-size:.88em;background:#e7ece8;padding:.12em .34em;border-radius:3px}}
pre{{overflow:auto;padding:16px;background:#182b38;color:#edf4f1;border-radius:4px}}pre code{{background:none;padding:0;color:inherit}}
.table-scroll{{overflow-x:auto;border:1px solid var(--line);margin:24px 0;background:#fffdf8}}
table{{border-collapse:collapse;width:100%;min-width:760px;font-size:13px;line-height:1.55}}
th,td{{padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}}
th{{font-size:12px;background:#dfe9e4;white-space:nowrap}}
tbody tr:last-child td{{border-bottom:0}}tbody tr:nth-child(even){{background:#f0f3ed}}
td:first-child{{min-width:145px;font-weight:600}}
.case-tag{{display:inline-block;padding:1px 7px;border:1px solid currentColor;border-radius:999px;font-size:11px;font-weight:700;white-space:nowrap}}
.case-tag.high{{color:var(--high);background:#e8f2ed}}.case-tag.low{{color:var(--low);background:#f8ebe2}}
ul,ol{{padding-left:24px}}li{{margin:8px 0}}blockquote{{margin:22px 0;padding:12px 18px;border-left:4px solid var(--orange);background:#f4ead5}}
.revision{{border-left:4px solid var(--teal);padding:2px 18px;background:#edf3ef;margin:18px 0 28px}}
footer{{max-width:1320px;margin:auto;border-top:1px solid var(--line);padding:24px;font-size:12px;color:var(--muted)}}
@media(max-width:1000px){{.layout{{grid-template-columns:1fr}}nav{{position:static;display:flex;gap:10px 18px;overflow:auto;white-space:nowrap}}nav a{{display:inline-block}}h1{{font-size:36px}}}}
@media(max-width:600px){{body{{font-size:15px}}header{{padding:30px 18px}}h1{{font-size:29px}}.layout{{padding:22px 16px}}h2{{font-size:24px}}h3{{font-size:18px}}.meta{{display:block}}.meta span{{display:block;white-space:normal;margin:4px 0}}}}
@media print{{nav{{display:none!important}}.layout{{display:block;padding:0}}header{{padding:20px 0}}body{{background:white}}h2,h3{{break-after:avoid}}.table-scroll{{overflow:visible}}table{{min-width:0}}a{{color:inherit}}}}
</style>
</head>
<body>
<header>
<div class="eyebrow">AUDIT REPORT / AGENT TRAJECTORY EVIDENCE</div>
<h1>{title}</h1>
<p class="dek">{dek}</p>
<div class="meta">{meta}<span><a href="{source_name}">Markdown源文档</a></span></div>
</header>
<div class="layout">
<nav aria-label="报告目录">{nav}</nav>
<main>{body}</main>
</div>
<footer>Harbor Agent Infra · 静态HTML审计报告 · 正式实验成绩与原始证据保持不变</footer>
</body>
</html>
"""


def slugify(text: str, used: set[str]) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", text).strip("-").lower()
    slug = slug or "section"
    base = slug
    suffix = 2
    while slug in used:
        slug = f"{base}-{suffix}"
        suffix += 1
    used.add(slug)
    return slug


def split_document(markdown: str) -> tuple[str, list[str], str]:
    lines = markdown.splitlines()
    if not lines or not lines[0].startswith("# "):
        raise ValueError("Audit document must start with one H1 heading.")
    title = lines[0][2:].strip()
    index = 1
    metadata: list[str] = []
    while index < len(lines) and not lines[index].startswith("## "):
        value = lines[index].strip().rstrip("  ")
        if value:
            metadata.append(value)
        index += 1
    return title, metadata, "\n".join(lines[index:]) + "\n"


def render(source: Path, output: Path, dek: str) -> None:
    title, metadata, body_markdown = split_document(source.read_text())
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    tokens = md.parse(body_markdown)
    used: set[str] = set()
    headings: list[tuple[int, str, str]] = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        level = int(token.tag[1])
        inline = tokens[index + 1]
        text = inline.content.strip()
        anchor = slugify(text, used)
        token.attrSet("id", anchor)
        headings.append((level, text, anchor))

    default_table_open = md.renderer.rules.get("table_open")
    default_table_close = md.renderer.rules.get("table_close")

    def table_open(tokens, idx, options, env):
        rendered = default_table_open(tokens, idx, options, env) if default_table_open else "<table>\n"
        return '<div class="table-scroll">' + rendered

    def table_close(tokens, idx, options, env):
        rendered = default_table_close(tokens, idx, options, env) if default_table_close else "</table>\n"
        return rendered + "</div>"

    md.renderer.rules["table_open"] = table_open
    md.renderer.rules["table_close"] = table_close
    body = md.renderer.render(tokens, md.options, {})
    body = body.replace("<td>高分</td>", '<td><span class="case-tag high">高分</span></td>')
    body = body.replace("<td>低分</td>", '<td><span class="case-tag low">低分</span></td>')
    body = body.replace('<h2 id="修订记录">', '<h2 id="修订记录">')
    revision_start = body.find('<h2 id="修订记录">')
    next_heading = body.find("<h2", revision_start + 1) if revision_start >= 0 else -1
    if revision_start >= 0 and next_heading > revision_start:
        segment = body[revision_start:next_heading]
        first_end = segment.find("</h2>") + len("</h2>")
        wrapped = segment[:first_end] + '<div class="revision">' + segment[first_end:] + "</div>"
        body = body[:revision_start] + wrapped + body[next_heading:]

    h2_headings = [(text, anchor) for level, text, anchor in headings if level == 2]
    nav = "".join(
        f'<a href="#{html.escape(anchor)}">{number:02d}　{html.escape(text)}</a>'
        for number, (text, anchor) in enumerate(h2_headings, start=1)
    )
    meta = "".join(f"<span>{html.escape(item)}</span>" for item in metadata)
    output.write_text(
        TEMPLATE.format(
            title=html.escape(title),
            dek=html.escape(dek),
            meta=meta,
            source_name=html.escape(source.name),
            nav=nav,
            body=body,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--dek",
        default="冻结正式Trial的完整轨迹对照：科学方法、证据解释与资源投入如何共同影响结果。",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    render(args.source.resolve(), args.output.resolve(), args.dek)


if __name__ == "__main__":
    main()
