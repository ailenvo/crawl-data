"""Download public Royal Road fiction metadata and chapters (Python 3.10+)."""

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import math
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from crawler import save_json, text

BASE = "https://www.royalroad.com"
AGENT = "RoyalRoadReader/1.0"
LOG = logging.getLogger("royalroad")


class AccessBlocked(ValueError):
    """Stop the entire run when the server denies automated access."""


def normalize(url):
    parts = urlsplit(urljoin(BASE + "/", url))
    if parts.scheme != "https" or parts.netloc not in {"royalroad.com", "www.royalroad.com"}:
        raise ValueError(f"URL phải thuộc {BASE}: {url}")
    return urlunsplit(("https", "www.royalroad.com", parts.path or "/", parts.query, ""))


def fiction_id(url):
    match = re.fullmatch(r"/fiction/(\d+)(?:/[^/]+)?/?", urlsplit(normalize(url)).path)
    if not match:
        raise ValueError("Cần URL truyện dạng https://www.royalroad.com/fiction/12345/ten-truyen")
    return match[1]


def chapter_id(url):
    match = re.fullmatch(r"/fiction/(?:\d+/[^/]+/)?chapter/(\d+)(?:/[^/]+)?/?",
                         urlsplit(normalize(url)).path)
    if not match:
        raise ValueError(f"URL chương không hợp lệ: {url}")
    return match[1]


def parse_fiction(soup, url):
    title = soup.select_one(".fic-title h1, h1.font-white, h1")
    description = soup.select_one(".description .hidden-content, .description")
    if not title or not description:
        raise ValueError("Không tìm thấy metadata truyện; HTML có thể đã thay đổi")
    author = soup.select_one('.fic-title a[href*="/profile/"], a[property="author"]')
    cover = soup.select_one('.fiction-cover img, meta[property="og:image"]')
    status = next((text(n) for n in soup.select(".fiction-info .label, .fic-title .label")
                   if text(n).upper() in {"ONGOING", "COMPLETED", "HIATUS", "DROPPED", "STUB"}), "")
    meta = {"id": fiction_id(url), "url": normalize(url), "title": text(title),
            "author": text(author), "description": description.get_text("\n", strip=True),
            "tags": list(dict.fromkeys(text(n) for n in soup.select(".fiction-tags a"))),
            "status": status,
            "cover_url": urljoin(url, cover.get("src", cover.get("content", ""))) if cover else ""}
    chapters, seen = [], set()
    # Scope to the TOC: recommendation links must never become chapters.
    for row in soup.select("#chapters tbody tr, table.chapters tbody tr"):
        anchor = row.select_one('a[href*="/chapter/"]')
        if not anchor:
            continue
        target = normalize(urljoin(url, anchor["href"]))
        identity = chapter_id(target)
        if identity in seen:
            continue
        seen.add(identity)
        published = row.select_one("time")
        chapters.append({"id": identity, "url": target, "title": text(anchor),
                         "published_at": published.get("datetime") if published else None})
    if not chapters:
        raise ValueError("Không tìm thấy chương trong bảng mục lục; truyện có thể đã gỡ chương hoặc đổi cấu trúc")
    return meta, chapters


def parse_chapter(soup, entry):
    content = soup.select_one(".chapter-content")
    if content is None:
        raise ValueError("Không có .chapter-content: chương đã gỡ, bị khóa hoặc HTML thay đổi")
    # Remove elements explicitly hidden by markup or simple display:none rules.
    for style in soup.select("style"):
        for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", style.get_text()):
            if re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", declarations, re.I):
                try:
                    for node in content.select(selectors.strip()):
                        node.decompose()
                except Exception:
                    # Unsupported CSS must not prevent extracting readable content.
                    pass
    for node in list(content.select("script, style, [hidden], .hidden, [style]")):
        if node.parent is None:
            continue
        if node.name in {"script", "style"} or node.has_attr("hidden") or "hidden" in node.get("class", []) or re.search(
                r"display\s*:\s*none|visibility\s*:\s*hidden", node.get("style", ""), re.I):
            node.decompose()
    for br in content.select("br"):
        br.replace_with("\n")
    for block in content.select("p, div, tr, h1, h2, h3, blockquote"):
        block.insert_after("\n\n")
    body = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", content.get_text()).strip()
    if not body:
        raise ValueError("Nội dung chương rỗng")
    return {**entry, "content": body, "fetched_at": datetime.now(timezone.utc).isoformat()}


class Client:
    def __init__(self, delay=3, timeout=30, retries=3):
        self.delay, self.timeout, self.retries = delay, timeout, retries
        self.last = 0.0
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": AGENT, "Accept": "text/html,text/plain"})
        self.robots = RobotFileParser()
        response = self.request(BASE + "/robots.txt", check_robots=False)
        if "user-agent:" not in response.text.lower():
            raise ValueError("robots.txt không hợp lệ; dừng crawl")
        self.robots.parse(response.text.splitlines())
        self.delay = max(delay, self.robots.crawl_delay(AGENT) or 0)

    def request(self, url, check_robots=True):
        current = normalize(url)
        for _ in range(6):
            if check_robots and not self.robots.can_fetch(AGENT, current):
                raise AccessBlocked(f"robots.txt không cho phép {current}")
            for attempt in range(self.retries + 1):
                time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
                self.last = time.monotonic()
                try:
                    response = self.session.get(current, timeout=self.timeout, allow_redirects=False)
                except requests.RequestException:
                    if attempt == self.retries:
                        raise
                    time.sleep(min(60, 2 ** (attempt + 1)))
                    continue
                if response.status_code in {401, 403}:
                    raise AccessBlocked(f"HTTP {response.status_code}: Royal Road chặn truy cập {current}. Không thử vượt chặn.")
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == self.retries:
                        response.raise_for_status()
                    wait = min(60, 2 ** (attempt + 1))
                    retry_after = response.headers.get("Retry-After", "")
                    if retry_after:
                        try:
                            wait = max(wait, float(retry_after))
                        except ValueError:
                            try:
                                wait = max(wait, (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
                            except (ValueError, TypeError):
                                pass
                    if not math.isfinite(wait) or wait > 300:
                        raise AccessBlocked("Server yêu cầu chờ lâu; hãy chạy lại sau")
                    LOG.warning("HTTP %s; chờ %.0fs", response.status_code, wait)
                    time.sleep(wait)
                    continue
                break
            if response.is_redirect:
                current = normalize(urljoin(current, response.headers["Location"]))
                continue
            response.raise_for_status()
            response.encoding = "utf-8"
            return response
        raise ValueError("Quá nhiều lần chuyển hướng")

    def soup(self, url):
        response = self.request(url)
        soup = BeautifulSoup(response.text, "html.parser")
        if soup.select_one("#challenge-running, #cf-challenge-running, .g-recaptcha"):
            raise AccessBlocked("Gặp CAPTCHA hoặc trang xác minh; dừng crawl")
        return soup


def crawl(client, url, output, limit=0, refresh=False):
    identity = fiction_id(url)
    folder = output / identity
    folder.mkdir(parents=True, exist_ok=True)
    meta, toc = parse_fiction(client.soup(url), url)
    save_json(folder / "metadata.json", meta)
    save_json(folder / "toc.json", toc)
    chapters, errors, interrupted = [], [], None
    selected = toc[:limit] if limit else toc
    try:
        for entry in selected:
            path = folder / f"chapter-{entry['id']}.json"
            try:
                cached = None
                if path.exists() and not refresh:
                    try:
                        cached = json.loads(path.read_text(encoding="utf-8"))
                    except (ValueError, OSError):
                        pass
                if isinstance(cached, dict) and cached.get("id") == entry["id"] and cached.get("content"):
                    chapter = {**cached, **entry}
                    LOG.info("Cache: %s", entry["title"])
                else:
                    chapter = parse_chapter(client.soup(entry["url"]), entry)
                    save_json(path, chapter)
                    LOG.info("Đã tải: %s", entry["title"])
                chapters.append(chapter)
            except AccessBlocked:
                raise
            except (requests.RequestException, ValueError) as exc:
                errors.append({"url": entry["url"], "error": str(exc)})
                LOG.error("%s: %s", entry["url"], exc)
            save_json(folder / "progress.json", {"saved": len(chapters), "selected": len(selected), "errors": errors})
    except (AccessBlocked, KeyboardInterrupt) as exc:
        interrupted = str(exc) or "Người dùng dừng bằng Ctrl+C"
    finally:
        result = {**meta, "chapters": chapters, "errors": errors, "interrupted": interrupted,
                  "available_chapters": len(toc), "selected_chapters": len(selected),
                  "complete": len(chapters) == len(toc) and not errors and not interrupted}
        save_json(folder / "story.json", result)
        save_json(folder / "progress.json", {k: result[k] for k in
                  ("available_chapters", "selected_chapters", "errors", "interrupted", "complete")} | {"saved": len(chapters)})
        (folder / "story.txt").write_text(meta["title"] + "\n\n" + "\n\n".join(
            c["title"] + "\n\n" + c["content"] for c in chapters), encoding="utf-8")
    if interrupted:
        LOG.error(interrupted)
    return bool(errors or interrupted)


def main():
    parser = argparse.ArgumentParser(description="Crawl truyện công khai trên Royal Road")
    parser.add_argument("url", help="URL trang /fiction/<id>/<slug>")
    parser.add_argument("--output", type=Path, default=Path("data/royalroad"))
    parser.add_argument("--max-chapters", type=int, default=0, help="0 = toàn bộ mục lục")
    parser.add_argument("--delay", type=float, default=3)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--refresh", action="store_true", help="Tải lại chương đã lưu")
    args = parser.parse_args()
    if (args.max_chapters < 0 or args.retries < 0 or not math.isfinite(args.delay)
            or args.delay < 0 or not math.isfinite(args.timeout) or args.timeout <= 0):
        parser.error("delay/max-chapters/retries phải >= 0; timeout phải > 0 và hữu hạn")
    fiction_id(args.url)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return int(crawl(Client(args.delay, args.timeout, args.retries), normalize(args.url),
                     args.output, args.max_chapters, args.refresh))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (requests.RequestException, ValueError, OSError) as exc:
        LOG.error("%s", exc)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
