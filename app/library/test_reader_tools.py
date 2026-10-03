import tempfile
from pathlib import Path

from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from .article import load_article
from .storage import write_bundle
from .revisions import ensure_revision
from .tests import MINI, make_paper


class ReaderToolsTests(TestCase):
    def test_toolbar_controls_and_selection_search_render_without_external_resources(self):
        self.client.force_login(User.objects.create_user('reader_interface_fixture'))
        paper = make_paper('Interface fixture')
        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=Path(directory)):
            write_bundle(Path(directory) / 'papers' / str(paper.pk), load_article(MINI.encode()), MINI.encode())
            ensure_revision(paper)
            response = self.client.get(f'/papers/{paper.pk}/')
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')
        for identifier in ['theme', 'font-size', 'source-toggle', 'google-button']:
            matches = soup.select('#' + identifier)
            self.assertEqual(len(matches), 1)
            self.assertIsNotNone(matches[0].find_parent('header', class_='readerbar'))
            self.assertIsNone(matches[0].find_parent('dialog'))
        self.assertIsNone(soup.select_one('[data-panel=settings]'))
        self.assertTrue(soup.select_one('#selection-tools').has_attr('hidden'))
        self.assertFalse(soup.select_one('#google-dialog').has_attr('open'))
        self.assertIsNone(soup.select_one('iframe'))
        self.assertTrue(all(not tag['src'].startswith('http') for tag in soup.select('script[src], img[src]')))
        self.assertIn("default-src 'none'", response['Content-Security-Policy'])
        self.assertIn("connect-src 'self'", response['Content-Security-Policy'])
        # A synthetic, isolated fixture for DOM logic tests. No live site is accessed.
        for tag in soup.select('[data-csrf]'):
            tag['data-csrf'] = 'offline-test-only'
        for tag in soup.select('input[name=csrfmiddlewaretoken]'):
            tag['value'] = 'offline-test-only'
        evidence = settings.ROOT / 'evidence'
        evidence.mkdir(exist_ok=True)
        (evidence / 'reader-tools-fixture.html').write_text(str(soup), encoding='utf-8')
