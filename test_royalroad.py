import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
import requests

from royalroad import BASE, AccessBlocked, Client, crawl, fiction_id, normalize, parse_chapter, parse_fiction

FICTION = '''<div class="fic-title"><h1>Example Fiction</h1>
<a href="/profile/99">Author</a></div>
<div class="description"><div class="hidden-content">Summary</div></div>
<div class="fiction-tags"><a>Fantasy</a></div>
<div class="fiction-info"><span class="label">COMPLETED</span></div>
<table id="chapters"><tbody>
<tr><td><a href="/fiction/12/example/chapter/90/first">First</a></td><td><time datetime="2026-01-01"></time></td></tr>
<tr><td><a href="/fiction/12/example/chapter/3/second">Second</a></td></tr>
</tbody></table><a href="/fiction/55/other/chapter/1000/no">Recommendation</a>'''
URL = BASE + '/fiction/12/example'


def soup(html):
    return BeautifulSoup(html, 'html.parser')


class RoyalRoadTests(unittest.TestCase):
    def test_metadata_and_toc_order(self):
        meta, toc = parse_fiction(soup(FICTION), URL)
        self.assertEqual(meta['author'], 'Author')
        self.assertEqual(meta['status'], 'COMPLETED')
        self.assertEqual([c['id'] for c in toc], ['90', '3'])
        self.assertEqual(toc[0]['published_at'], '2026-01-01')

    def test_content_preserves_inline_text_and_excludes_hidden(self):
        entry = {'id': '90', 'title': 'First', 'url': URL + '/chapter/90/first'}
        page = soup('<style>.secret { display: none !important; }</style><h1>Title</h1>'
                    '<div class="chapter-content"><p>Hello <em>world</em>.</p>'
                    '<span class="secret">noise</span><span hidden>hidden</span>'
                    '<p>Second<br>line</p></div><div>Comment</div>')
        result = parse_chapter(page, entry)
        self.assertEqual(result['content'], 'Hello world.\n\nSecond\nline')

    def test_invalid_urls_and_missing_content(self):
        for url in ['https://evil.example/fiction/12/test', 'https://www.royalroad.com.evil.example/']:
            with self.assertRaises(ValueError):
                normalize(url)
        with self.assertRaises(ValueError):
            fiction_id(BASE + '/fictions/best-rated')
        with self.assertRaises(ValueError):
            parse_chapter(soup('<h1>Access denied</h1>'), {})

    def test_resume_and_retry_failed_chapter(self):
        client = Mock()
        client.soup.side_effect = [soup(FICTION), soup('<div class="chapter-content">One</div>'),
                                   requests.ConnectionError('offline')]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertTrue(crawl(client, URL, root))
            client.soup.reset_mock()
            client.soup.side_effect = [soup(FICTION), soup('<div class="chapter-content">Two</div>')]
            self.assertFalse(crawl(client, URL, root))
            self.assertEqual(client.soup.call_count, 2)
            result = json.loads((root / '12/story.json').read_text())
            self.assertTrue(result['complete'])
            self.assertEqual([c['content'] for c in result['chapters']], ['One', 'Two'])

    def test_block_stops_and_saves_partial_result(self):
        client = Mock()
        client.soup.side_effect = [soup(FICTION), AccessBlocked('403')]
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(crawl(client, URL, Path(directory)))
            result = json.loads((Path(directory) / '12/story.json').read_text())
            self.assertFalse(result['complete'])
            self.assertEqual(result['interrupted'], '403')
            self.assertEqual(client.soup.call_count, 2)

    @patch('royalroad.time.sleep')
    def test_http_403_is_not_retried(self, sleep):
        client = Client.__new__(Client)
        client.delay, client.timeout, client.retries, client.last = 0, 30, 3, 0
        client.robots = RobotFileParser()
        client.robots.parse(['User-agent: *', 'Allow: /'])
        client.session = Mock()
        client.session.get.return_value = Mock(status_code=403)
        with self.assertRaises(AccessBlocked):
            client.request(URL)
        self.assertEqual(client.session.get.call_count, 1)


if __name__ == '__main__':
    unittest.main()
