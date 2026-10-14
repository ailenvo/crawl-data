"""Crawler for public TruyenTV HTML. Python 3.10+."""

import argparse
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

BASE = "https://www.tvtruyen.space"
LOG = logging.getLogger("tvtruyen")


def normalize(url):
    parts = urlsplit(urljoin(BASE + "/", url))
    if parts.scheme != "https" or parts.netloc != "www.tvtruyen.space":
        raise ValueError(f"URL phải thuộc {BASE}: {url}")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


def text(node):
    return node.get_text(" ", strip=True) if node else ""


def story_links(soup, url):
    return list(
        dict.fromkeys(
            normalize(urljoin(url, a["href"]))
            for a in soup.select("a[href]")
            if re.fullmatch(r"/[^/]+\.html", urlsplit(urljoin(url, a["href"])).path)
            and urlsplit(urljoin(url, a["href"])).netloc == "www.tvtruyen.space"
        )
    )


def chapter_links(soup, url, slug):
    result = []
    for a in soup.select("a[href]"):
        target = urljoin(url, a["href"])
        if urlsplit(target).netloc == "www.tvtruyen.space" and re.fullmatch(
            "/" + re.escape(slug) + r"/chuong-[^/]+", urlsplit(target).path
        ):
            target = normalize(target)
            if target not in result:
                result.append(target)
    return sorted(
        result,
        key=lambda u: tuple(int(n) for n in re.findall(r"\d+", u.rsplit("/", 1)[-1])),
    )


def metadata(soup, url):
    image = soup.select_one('meta[property="og:image"]')
    info = soup.select_one(".info-holder .info") or soup.select_one(".info")
    status = ""
    if info:
        for h in info.select("h3"):
            if "Trạng thái" in text(h):
                status = text(h.find_next_sibling())
    return {
        "url": url,
        "title": text(soup.select_one("h1")),
        "author": text(soup.select_one('[itemprop="author"]')),
        "genres": [text(a) for a in soup.select(".genres a")],
        "status": status,
        "cover_url": image.get("content", "") if image else "",
        "description": text(soup.select_one(".limit-desc")),
    }


def parse_chapter(soup, url, slug):
    content = soup.select_one("#chapter-content")
    if not content or not text(content):
        raise ValueError(
            "Không có nội dung công khai: chương khóa, trang lỗi hoặc cấu trúc đã thay đổi"
        )
    for node in content.select("script, style"):
        node.decompose()
    for br in content.select("br"):
        br.replace_with("\n")
    body = "\n".join(
        line.strip() for line in content.get_text("\n").splitlines() if line.strip()
    )
    next_node = soup.select_one("a#next_chap:not(.disabled)")
    next_url = None
    if next_node and next_node.get("href"):
        candidate = normalize(urljoin(url, next_node["href"]))
        if candidate in chapter_links(soup, url, slug) and candidate != url:
            next_url = candidate
    return {
        "url": url,
        "title": text(soup.select_one(".chapter-title")) or text(soup.select_one("h2")),
        "content": body,
        "next_url": next_url,
    }


def save_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class Client:
    def __init__(self, delay, timeout, retries):
        self.delay, self.timeout, self.retries = delay, timeout, retries
        self.last = 0.0
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "TVTruyenCrawler/1.0"
        self.robots = RobotFileParser()
        response = self.request(BASE + "/robots.txt")
        if response.status_code == 404:
            self.robots.parse(["User-agent: *", "Allow: /"])
        else:
            response.raise_for_status()
            if "user-agent:" not in response.text.lower():
                raise ValueError("robots.txt không hợp lệ; dừng crawl")
            self.robots.parse(response.text.splitlines())
        self.delay = max(delay, self.robots.crawl_delay("TVTruyenCrawler") or 0)

    def request(self, url):
        url = normalize(url)
        for attempt in range(self.retries + 1):
            time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                response = self.session.get(
                    url, timeout=self.timeout, allow_redirects=False
                )
                if 300 <= response.status_code < 400:
                    raise ValueError(
                        f"Website chuyển hướng: {url}; kiểm tra URL mới trước khi chạy"
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                response.encoding = "utf-8"
                return response
            except requests.RequestException:
                if attempt == self.retries:
                    raise
                time.sleep(min(60, 2 ** (attempt + 1)))

    def soup(self, url):
        if not self.robots.can_fetch("TVTruyenCrawler", normalize(url)):
            raise ValueError(f"robots.txt không cho phép: {url}")
        response = self.request(url)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")


def crawl_story(client, url, output, limit):
    url = normalize(url)
    slug = urlsplit(url).path.strip("/").removesuffix(".html")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", slug):
        raise ValueError("Cần URL trang truyện dạng /ten-truyen.html")
    folder = output / slug
    folder.mkdir(parents=True, exist_ok=True)
    soup = client.soup(url)
    meta = metadata(soup, url)
    if not meta["title"] or not soup.select_one(".limit-desc"):
        raise ValueError("Trang không có metadata truyện hợp lệ")
    save_json(folder / "metadata.json", meta)
    pending = chapter_links(soup, url, slug) or [BASE + "/" + slug + "/chuong-1"]
    seen, chapters, errors = set(), [], []
    while pending and (not limit or len(seen) < limit):
        target = pending.pop(0)
        if target in seen:
            continue
        seen.add(target)
        path = folder / (urlsplit(target).path.rsplit("/", 1)[-1] + ".json")
        try:
            if path.exists():
                chapter = json.loads(path.read_text(encoding="utf-8"))
                if chapter.get("url") != target or not chapter.get("content"):
                    raise ValueError(f"Cache không hợp lệ: {path}")
                LOG.info("Đã lưu: %s", target)
            else:
                chapter = parse_chapter(client.soup(target), target, slug)
                save_json(path, chapter)
                LOG.info("Đã tải: %s", target)
            chapters.append(chapter)
            if chapter.get("next_url") and chapter["next_url"] not in seen:
                pending.insert(0, chapter["next_url"])
        except (requests.RequestException, ValueError) as exc:
            errors.append({"url": target, "error": str(exc)})
            LOG.error("%s: %s", target, exc)
        save_json(
            folder / "progress.json",
            {"visited": len(seen), "saved": len(chapters), "errors": errors},
        )
    save_json(
        folder / "story.json",
        {
            **meta,
            "chapters": chapters,
            "errors": errors,
            "limit_reached": bool(pending),
        },
    )
    (folder / "story.txt").write_text(
        meta["title"]
        + "\n\n"
        + "\n\n".join(c["title"] + "\n\n" + c["content"] for c in chapters),
        encoding="utf-8",
    )
    return bool(errors)


def main():
    parser = argparse.ArgumentParser(
        description="Crawl truyện công khai từ tvtruyen.space"
    )
    parser.add_argument("url", help="URL truyện hoặc trang danh sách")
    parser.add_argument("--listing", action="store_true", help="URL là trang danh sách")
    parser.add_argument("--max-stories", type=int, default=5)
    parser.add_argument(
        "--max-pages", type=int, default=1, help="Số trang danh sách tối đa"
    )
    parser.add_argument(
        "--max-chapters", type=int, default=0, help="0 = toàn bộ chương tìm được"
    )
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--delay", type=float, default=2)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    if (
        args.delay < 0
        or args.timeout <= 0
        or args.retries < 0
        or args.max_chapters < 0
        or min(args.max_pages, args.max_stories) <= 0
    ):
        parser.error("Giới hạn phải dương; delay/retries/max-chapters phải >= 0")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = Client(args.delay, args.timeout, args.retries)
    urls = [normalize(args.url)]
    if args.listing:
        urls, page, visited = [], normalize(args.url), set()
        for _ in range(args.max_pages):
            if page in visited:
                break
            visited.add(page)
            soup = client.soup(page)
            urls = list(dict.fromkeys(urls + story_links(soup, page)))
            nxt = soup.select_one('.pagination a[rel="next"], a[rel="next"]')
            if not nxt or len(urls) >= args.max_stories:
                break
            page = normalize(urljoin(page, nxt["href"]))
        urls = urls[: args.max_stories]
        if not urls:
            raise ValueError("Không tìm thấy truyện trên trang danh sách")
    failed = False
    for url in urls:
        try:
            failed = crawl_story(client, url, args.output, args.max_chapters) or failed
        except (requests.RequestException, ValueError) as exc:
            LOG.error("%s: %s", url, exc)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (requests.RequestException, ValueError) as exc:
        LOG.error("%s", exc)
        raise SystemExit(1)
