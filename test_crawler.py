import json
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup
from crawler import BASE, crawl_story, normalize, parse_chapter, chapter_links


class CrawlerTests(unittest.TestCase):
    def test_chapter_content_and_next(self):
        soup = BeautifulSoup('<div class="chapter-title">Chương 1</div>'
            '<div id="chapter-content">Đoạn một<br>Đoạn hai<script>ads()</script></div>'
            '<a id="next_chap" href="/demo/chuong-2">Tiếp</a>'
            '<a href="/other/chuong-3">Đề xuất</a>', 'html.parser')
        result = parse_chapter(soup, BASE + '/demo/chuong-1', 'demo')
        self.assertEqual(result['content'], 'Đoạn một\nĐoạn hai')
        self.assertEqual(result['next_url'], BASE + '/demo/chuong-2')
        self.assertEqual(chapter_links(soup, BASE, 'demo'), [BASE + '/demo/chuong-2'])

    def test_missing_content(self):
        with self.assertRaises(ValueError):
            parse_chapter(BeautifulSoup('<p>Đăng nhập</p>', 'html.parser'), BASE, 'demo')

    def test_external_url_rejected(self):
        with self.assertRaises(ValueError):
            normalize('https://example.com/demo')

    def test_resume_follows_saved_next_link(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def soup(self, url):
                self.calls.append(url)
                if url.endswith('.html'):
                    html = '<h1>Demo</h1><section class="limit-desc">Mô tả</section>'
                elif url.endswith('chuong-1'):
                    html = '<div id="chapter-content">Một</div><a id="next_chap" href="/demo/chuong-2">Tiếp</a>'
                else:
                    html = '<div id="chapter-content">Hai</div>'
                return BeautifulSoup(html, 'html.parser')

        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            output = Path(directory)
            self.assertFalse(crawl_story(client, BASE + '/demo.html', output, 1))
            client.calls.clear()
            self.assertFalse(crawl_story(client, BASE + '/demo.html', output, 0))
            self.assertNotIn(BASE + '/demo/chuong-1', client.calls)
            result = json.loads((output / 'demo/story.json').read_text())
            self.assertEqual(len(result['chapters']), 2)
            self.assertFalse(result['limit_reached'])


if __name__ == '__main__':
    unittest.main()
