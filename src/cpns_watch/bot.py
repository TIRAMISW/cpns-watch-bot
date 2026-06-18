from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import smtplib
import sys
import textwrap
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup


DEFAULT_CONFIG = Path("config/sources.json")
DEFAULT_SEEN = Path("data/seen.json")
DEFAULT_REPORT = Path("reports/latest.md")
USER_AGENT = "cpns-watch-bot/1.0 (+https://sscasn.bkn.go.id/)"
IGNORED_LINK_TITLES = {
    "skip to main content",
    "profil",
    "publikasi",
    "berita",
    "siaran pers",
    "pengumuman",
    "ppid bkn",
    "informasi berkala",
    "informasi setiap saat",
    "informasi serta merta",
    "informasi yang dikecualikan",
    "daftar informasi publik",
    "akuntabilitas kinerja",
    "reformasi birokrasi",
    "search",
}


@dataclass(frozen=True)
class Item:
    source: str
    title: str
    url: str
    published: str
    snippet: str
    official: bool
    keywords: tuple[str, ...]
    is_new: bool = False

    @property
    def key(self) -> str:
        raw = f"{self.source}|{self.url}|{self.title}".encode("utf-8", "ignore")
        return hashlib.sha256(raw).hexdigest()[:16]


def now_jakarta() -> dt.datetime:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=7), "Asia/Jakarta"))


def load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize_space(value: str) -> str:
    value = html.unescape(value or "")
    return re.sub(r"\s+", " ", value).strip()


def clean_markup(value: str) -> str:
    soup = BeautifulSoup(value or "", "html.parser")
    return normalize_space(soup.get_text(" "))


def short_snippet(text: str, limit: int = 360) -> str:
    text = normalize_space(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def absolute_url(base_url: str, url: str) -> str:
    return urllib.parse.urljoin(base_url, url)


def fetch(url: str, timeout: int = 25) -> requests.Response:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response


def matched_keywords(
    text: str,
    keywords: Iterable[str],
    context_keywords: Iterable[str] = (),
) -> tuple[str, ...]:
    high_signal_hits = [keyword for keyword in keywords if contains_keyword(text, keyword)]
    if not high_signal_hits:
        return ()
    context_hits = [keyword for keyword in context_keywords if contains_keyword(text, keyword)]
    return tuple(dict.fromkeys([*high_signal_hits, *context_hits]))


def contains_keyword(text: str, keyword: str) -> bool:
    escaped = re.escape(keyword.casefold()).replace(r"\ ", r"\s+")
    pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    return re.search(pattern, text.casefold()) is not None


def parse_rss(source: dict, keywords: list[str], context_keywords: list[str]) -> list[Item]:
    response = fetch(source["url"])
    root = ET.fromstring(response.content)
    items: list[Item] = []

    for node in root.findall(".//item")[:30]:
        title = normalize_space(node.findtext("title") or "")
        url = normalize_space(node.findtext("link") or source["url"])
        published = normalize_space(node.findtext("pubDate") or "")
        description = clean_markup(node.findtext("description") or "")
        hits = matched_keywords(f"{title} {description} {url}", keywords, context_keywords)
        if not hits and not source.get("always_include"):
            continue
        items.append(
            Item(
                source=source["name"],
                title=title or source["name"],
                url=url,
                published=published,
                snippet=short_snippet(description),
                official=bool(source.get("official")),
                keywords=hits,
            )
        )
    return items


def parse_html(source: dict, keywords: list[str], context_keywords: list[str]) -> list[Item]:
    response = fetch(source["url"])
    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    candidates: list[Item] = []
    seen_urls: set[str] = set()

    selectors = "article a, h1 a, h2 a, h3 a, .item-title a, .entry-title a, a"
    for anchor in soup.select(selectors):
        title = normalize_space(anchor.get_text(" "))
        href = anchor.get("href")
        if not title or not href:
            continue
        if title.casefold() in IGNORED_LINK_TITLES:
            continue
        url = absolute_url(source["url"], href)
        parsed_url = urllib.parse.urlparse(url)
        if (
            url in seen_urls
            or not url.startswith(("http://", "https://"))
            or parsed_url.fragment
            or parsed_url.netloc.endswith("kpk.go.id")
            or parsed_url.path.startswith("/tag/")
            or parsed_url.path.startswith("/page/")
            or title.startswith("#")
            or re.fullmatch(r"page\s+\d+", title, flags=re.IGNORECASE)
        ):
            continue
        seen_urls.add(url)

        nearby = normalize_space(anchor.find_parent().get_text(" ") if anchor.find_parent() else title)
        hits = matched_keywords(f"{title} {url}", keywords, context_keywords)
        if not hits and not source.get("always_include"):
            continue
        candidates.append(
            Item(
                source=source["name"],
                title=title,
                url=url,
                published=extract_date(nearby),
                snippet=short_snippet(nearby),
                official=bool(source.get("official")),
                keywords=hits,
            )
        )

    page_text = normalize_space(soup.get_text(" "))
    page_hits = matched_keywords(page_text, keywords, context_keywords)
    if source.get("always_include"):
        candidates.insert(
            0,
            Item(
                source=source["name"],
                title=source["name"],
                url=source["url"],
                published=extract_date(page_text),
                snippet=short_snippet(page_text),
                official=bool(source.get("official")),
                keywords=page_hits,
            ),
        )

    return candidates[:25]


def extract_date(text: str) -> str:
    patterns = [
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b\d{1,2}\s+(Jan|Feb|Mar|Apr|Mei|Jun|Jul|Agu|Sep|Okt|Nov|Des)[a-z]*\s+\d{4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return ""


def collect_items(config: dict) -> tuple[list[Item], list[str]]:
    keywords = config.get("keywords", [])
    context_keywords = config.get("context_keywords", [])
    all_items: list[Item] = []
    errors: list[str] = []

    for source in config.get("sources", []):
        try:
            if source.get("type") == "rss":
                all_items.extend(parse_rss(source, keywords, context_keywords))
            else:
                all_items.extend(parse_html(source, keywords, context_keywords))
        except Exception as exc:  # noqa: BLE001 - report all source failures cleanly
            errors.append(f"{source.get('name', source.get('url'))}: {exc}")

    unique: dict[str, Item] = {}
    for item in all_items:
        if item.url not in unique:
            unique[item.url] = item
    return list(unique.values()), errors


def mark_new(items: list[Item], seen_path: Path) -> tuple[list[Item], dict]:
    seen = load_json(seen_path, {"items": {}, "last_run": None})
    old_items = seen.get("items", {})
    updated: dict[str, dict] = {}
    marked: list[Item] = []

    for item in items:
        is_new = item.key not in old_items
        marked.append(
            Item(
                source=item.source,
                title=item.title,
                url=item.url,
                published=item.published,
                snippet=item.snippet,
                official=item.official,
                keywords=item.keywords,
                is_new=is_new,
            )
        )
        updated[item.key] = {
            "title": item.title,
            "url": item.url,
            "source": item.source,
            "first_seen": old_items.get(item.key, {}).get("first_seen") or now_jakarta().isoformat(),
            "last_seen": now_jakarta().isoformat(),
        }

    seen = {"last_run": now_jakarta().isoformat(), "items": updated}
    save_json(seen_path, seen)
    return marked, seen


def render_report(items: list[Item], errors: list[str]) -> str:
    timestamp = now_jakarta().strftime("%Y-%m-%d %H:%M:%S %Z")
    new_items = [item for item in items if item.is_new]
    official_items = [item for item in items if item.official]

    lines = [
        "# Laporan Pantauan CPNS/CASN",
        "",
        f"Dibuat: {timestamp}",
        "",
        f"Temuan baru: **{len(new_items)}**",
        f"Total item relevan: **{len(items)}**",
        "",
        "## Ringkasan",
        "",
    ]

    if new_items:
        for item in new_items[:15]:
            lines.extend(format_item(item))
    else:
        lines.append("Belum ada item baru sejak run terakhir.")
        lines.append("")

    lines.extend(
        [
            "## Semua Sumber Resmi Terdeteksi",
            "",
        ]
    )
    for item in official_items[:40]:
        lines.extend(format_item(item, compact=True))

    lines.extend(
        [
            "## Link Apply dan Rujukan Resmi",
            "",
            "- Portal SSCASN: https://sscasn.bkn.go.id/",
            "- Daftar formasi: https://sscasn.bkn.go.id/daftar-formasi/",
            "- FAQ SSCASN: https://sscasn.bkn.go.id/faq/",
            "- Buku petunjuk SSCASN: https://sscasn.bkn.go.id/buku-petunjuk/",
            "- Berita BKN: https://www.bkn.go.id/category/publikasi/berita/",
            "- Pengumuman BKN: https://www.bkn.go.id/category/publikasi/pengumuman/",
            "- KemenPANRB CPNS: https://www.menpan.go.id/site/berita-terkini/cpns",
            "",
            "## Catatan Anti-Hoaks",
            "",
            "Anggap belum resmi kalau informasi tidak muncul di BKN, SSCASN, atau KemenPANRB. Jangan bayar oknum dan jangan masukkan data pribadi ke link selain portal resmi.",
            "",
        ]
    )

    if errors:
        lines.extend(["## Error Sumber", ""])
        for error in errors:
            lines.append(f"- {error}")
        lines.append("")

    return "\n".join(lines)


def format_item(item: Item, compact: bool = False) -> list[str]:
    prefix = "BARU - " if item.is_new else ""
    tags = ", ".join(item.keywords) if item.keywords else "monitor"
    lines = [
        f"- **{prefix}{item.title}**",
        f"  Sumber: {item.source} | Keyword: {tags}",
        f"  Link: {item.url}",
    ]
    if item.published:
        lines.append(f"  Tanggal: {item.published}")
    if item.snippet and not compact:
        lines.append(f"  Cuplikan: {item.snippet}")
    lines.append("")
    return lines


def write_report(report_path: Path, text: str) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")


def notify(report: str) -> None:
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    message = trim_notification(report)
    if telegram_token and telegram_chat_id:
        send_telegram(telegram_token, telegram_chat_id, message)
    if discord_webhook_url:
        send_discord(discord_webhook_url, message)
    if os.getenv("EMAIL_TO"):
        send_email(report)


def trim_notification(report: str) -> str:
    lines = report.splitlines()
    selected: list[str] = []
    for line in lines:
        selected.append(line)
        if len("\n".join(selected)) > 3000:
            selected.append("")
            selected.append("Laporan penuh ada di reports/latest.md")
            break
    return "\n".join(selected)


def send_telegram(token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout=25,
    )
    response.raise_for_status()


def send_discord(webhook_url: str, message: str) -> None:
    chunks = textwrap.wrap(message, width=1900, replace_whitespace=False, drop_whitespace=False)
    if not chunks:
        chunks = [message]
    for chunk in chunks[:3]:
        response = requests.post(webhook_url, json={"content": chunk}, timeout=25)
        response.raise_for_status()


def send_email(report: str) -> None:
    host = os.environ["EMAIL_HOST"]
    port = int(os.getenv("EMAIL_PORT", "587"))
    username = os.getenv("EMAIL_USERNAME")
    password = os.getenv("EMAIL_PASSWORD")
    sender = os.getenv("EMAIL_FROM") or username or os.environ["EMAIL_TO"]
    recipients = [email.strip() for email in os.environ["EMAIL_TO"].split(",") if email.strip()]
    use_tls = os.getenv("EMAIL_USE_TLS", "true").casefold() not in {"0", "false", "no"}

    message = EmailMessage()
    message["Subject"] = "Laporan Pantauan CPNS/CASN"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(report)

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pantau berita dan pengumuman CPNS/CASN dari sumber resmi.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path config JSON.")
    parser.add_argument("--seen", default=str(DEFAULT_SEEN), help="Path database item yang sudah pernah dilihat.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Path output laporan Markdown.")
    parser.add_argument("--notify", action="store_true", help="Kirim notifikasi jika env token tersedia.")
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    seen_path = Path(args.seen)
    report_path = Path(args.report)

    config = load_json(config_path, {"keywords": [], "sources": []})
    items, errors = collect_items(config)
    marked, _seen = mark_new(items, seen_path)
    report = render_report(marked, errors)
    write_report(report_path, report)

    if args.notify:
        notify(report)

    sys.stdout.write(report)
    sys.stdout.write("\n")
    return 0 if not errors else 2
