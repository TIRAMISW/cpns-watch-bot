from __future__ import annotations

import datetime as dt
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET

import gradio as gr
import requests
from bs4 import BeautifulSoup


USER_AGENT = "cpns-watch-space/1.0 (+https://sscasn.bkn.go.id/)"
KEYWORDS = [
    "cpns",
    "casn",
    "sscasn",
    "formasi",
    "pendaftaran",
    "skd",
    "skb",
    "pppk",
    "non-asn",
    "honorer",
    "rekrutmen",
    "pengadaan asn",
    "kebutuhan asn",
    "sekolah kedinasan",
    "hoaks",
    "hoax",
]
CONTEXT_KEYWORDS = ["asn", "bkn", "seleksi", "pengumuman"]
SOURCES = [
    ("BKN Berita", "rss", "https://www.bkn.go.id/category/publikasi/berita/feed/", False),
    ("BKN Pengumuman", "rss", "https://www.bkn.go.id/category/publikasi/pengumuman/feed/", False),
    ("BKN Search CPNS", "html", "https://www.bkn.go.id/?s=cpns", False),
    ("BKN Search CASN", "html", "https://www.bkn.go.id/?s=casn", False),
    ("BKN Search SSCASN", "html", "https://www.bkn.go.id/?s=sscasn", False),
    ("KemenPANRB CPNS", "html", "https://www.menpan.go.id/site/berita-terkini/cpns", False),
    ("KemenPANRB Search CPNS", "html", "https://www.menpan.go.id/site/search?searchphrase=all&searchword=cpns", False),
    ("SSCASN Portal", "html", "https://sscasn.bkn.go.id/", True),
    ("SSCASN Formasi", "html", "https://sscasn.bkn.go.id/daftar-formasi/", True),
    ("SSCASN FAQ", "html", "https://sscasn.bkn.go.id/faq/", True),
]
IGNORED_TITLES = {
    "skip to main content",
    "profil",
    "publikasi",
    "berita",
    "siaran pers",
    "pengumuman",
    "search",
}


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def clean_markup(value: str) -> str:
    return normalize_space(BeautifulSoup(value or "", "html.parser").get_text(" "))


def contains_keyword(text: str, keyword: str) -> bool:
    escaped = re.escape(keyword.casefold()).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text.casefold()) is not None


def matched_keywords(text: str) -> list[str]:
    hits = [keyword for keyword in KEYWORDS if contains_keyword(text, keyword)]
    if not hits:
        return []
    return list(dict.fromkeys(hits + [keyword for keyword in CONTEXT_KEYWORDS if contains_keyword(text, keyword)]))


def fetch(url: str) -> requests.Response:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    response.raise_for_status()
    return response


def short(text: str, limit: int = 280) -> str:
    text = normalize_space(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def parse_rss(name: str, url: str) -> list[dict]:
    root = ET.fromstring(fetch(url).content)
    results = []
    for node in root.findall(".//item")[:20]:
        title = normalize_space(node.findtext("title") or "")
        link = normalize_space(node.findtext("link") or url)
        published = normalize_space(node.findtext("pubDate") or "")
        snippet = clean_markup(node.findtext("description") or "")
        hits = matched_keywords(f"{title} {snippet} {link}")
        if hits:
            results.append(
                {
                    "source": name,
                    "title": title,
                    "url": link,
                    "published": published,
                    "snippet": short(snippet),
                    "keywords": hits,
                }
            )
    return results


def parse_html(name: str, url: str, always_include: bool) -> list[dict]:
    soup = BeautifulSoup(fetch(url).text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    results = []
    if always_include:
        page_text = normalize_space(soup.get_text(" "))
        results.append(
            {
                "source": name,
                "title": name,
                "url": url,
                "published": "",
                "snippet": short(page_text),
                "keywords": matched_keywords(page_text) or ["monitor"],
            }
        )

    seen = set()
    for anchor in soup.select("article a, h1 a, h2 a, h3 a, .item-title a, .entry-title a, a"):
        title = normalize_space(anchor.get_text(" "))
        href = anchor.get("href")
        if not title or not href or title.casefold() in IGNORED_TITLES:
            continue
        link = urllib.parse.urljoin(url, href)
        parsed = urllib.parse.urlparse(link)
        if (
            link in seen
            or parsed.fragment
            or parsed.path.startswith("/tag/")
            or parsed.path.startswith("/page/")
            or title.startswith("#")
            or re.fullmatch(r"page\s+\d+", title, flags=re.IGNORECASE)
        ):
            continue
        hits = matched_keywords(f"{title} {link}")
        if not hits:
            continue
        seen.add(link)
        results.append(
            {
                "source": name,
                "title": title,
                "url": link,
                "published": "",
                "snippet": short(title),
                "keywords": hits,
            }
        )
    return results[:25]


def run_watch() -> str:
    items = []
    errors = []
    for name, source_type, url, always_include in SOURCES:
        try:
            if source_type == "rss":
                items.extend(parse_rss(name, url))
            else:
                items.extend(parse_html(name, url, always_include))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")

    unique = {}
    for item in items:
        unique.setdefault(item["url"], item)

    timestamp = dt.datetime.now(dt.timezone(dt.timedelta(hours=7), "Asia/Jakarta")).strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        "# Laporan Pantauan CPNS/CASN",
        "",
        f"Dibuat: {timestamp}",
        "",
        f"Total item relevan: **{len(unique)}**",
        "",
        "## Temuan Resmi",
        "",
    ]
    for item in list(unique.values())[:40]:
        keywords = ", ".join(item["keywords"])
        lines.extend(
            [
                f"- **{item['title']}**",
                f"  Sumber: {item['source']} | Keyword: {keywords}",
                f"  Link: {item['url']}",
                "",
            ]
        )

    lines.extend(
        [
            "## Link Resmi",
            "",
            "- Portal SSCASN: https://sscasn.bkn.go.id/",
            "- Daftar formasi: https://sscasn.bkn.go.id/daftar-formasi/",
            "- FAQ SSCASN: https://sscasn.bkn.go.id/faq/",
            "- Berita BKN: https://www.bkn.go.id/category/publikasi/berita/",
            "- Pengumuman BKN: https://www.bkn.go.id/category/publikasi/pengumuman/",
            "",
            "## Catatan Anti-Hoaks",
            "",
            "Anggap belum resmi kalau informasi tidak muncul di BKN, SSCASN, atau KemenPANRB.",
        ]
    )

    if errors:
        lines.extend(["", "## Error Sumber", ""])
        lines.extend(f"- {error}" for error in errors)

    return "\n".join(lines)


with gr.Blocks(title="CPNS Watch Bot") as demo:
    gr.Markdown("# CPNS Watch Bot")
    gr.Markdown("Pantau info CPNS/CASN dari sumber resmi BKN, SSCASN, dan KemenPANRB.")
    run_button = gr.Button("Cek Sekarang", variant="primary")
    report = gr.Markdown(value=run_watch())
    run_button.click(run_watch, outputs=report)


if __name__ == "__main__":
    demo.launch()
