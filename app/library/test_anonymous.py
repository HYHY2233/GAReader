import json
import secrets
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from .article import load_article
from .identity import ANIMALS, MOODS, create_anonymous_reader, remember_anonymous_reader
from django.http import HttpResponse
from .models import Comment, Rating
from .storage import write_bundle
from .tests import MINI, make_paper


class AnonymousEntryTests(TestCase):
    def enter(self, client=None, action='new', **data):
        client = client or self.client
        response = client.post('/anonymous/', {'action': action, **data})
        self.assertEqual(response.status_code, 302)
        return User.objects.get(pk=client.session[SESSION_KEY])

    def test_login_registration_and_anonymous_options_share_entry_page(self):
        response = self.client.get('/login/?next=/')
        self.assertContains(response, '匿名登录')
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup.select_one('.account-entry-panel input[name=username]'))
        self.assertIsNotNone(soup.select_one('.account-entry-panel input[type=password]'))
        self.assertIsNotNone(soup.select_one('.auth-tabs a[href^="/register/"]'))
        self.assertIsNotNone(soup.select_one('.anonymous-entry-panel form[action="/anonymous/"]'))
        self.assertIsNone(soup.select_one('.anonymous-entry-panel input[name=username]'))
        self.assertNotContains(response, '不用注册')
        self.assertNotContains(response, '一起读篇论文吧')
        self.assertFalse(User.objects.exists())
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_real_csrf_entry_creates_unprivileged_identity_and_reuses_session(self):
        client = Client(enforce_csrf_checks=True)
        client.get('/login/')
        self.assertEqual(client.post('/anonymous/', {'action': 'new'}).status_code, 403)
        self.assertFalse(User.objects.exists())
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        user = self.enter(client, csrfmiddlewaretoken=token, username='admin', is_staff='true')
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(any(user.first_name.startswith(word) for word in MOODS))
        self.assertTrue(any(animal in user.first_name for animal in ANIMALS))
        self.assertTrue(user.first_name.endswith(f' · {user.pk:04d}'))
        self.assertFalse(client.session.get_expire_at_browser_close())
        cookie = client.cookies[settings.ANONYMOUS_COOKIE_NAME]
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Strict')
        self.assertEqual(cookie['max-age'], settings.ANONYMOUS_COOKIE_AGE)
        for _ in range(2):
            self.assertContains(client.get('/'), user.first_name)
        self.assertContains(client.get('/login/'), user.first_name)
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        self.enter(client, action='resume', csrfmiddlewaretoken=token)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(int(client.session[SESSION_KEY]), user.pk)
        self.assertNotContains(client.get('/'), '修改密码')

    def test_logout_and_new_visit_keep_history_and_separate_ownership(self):
        paper = make_paper()
        first = self.enter()
        base = f'/api/papers/{paper.pk}/'
        comment = self.client.post(base + 'comments/', json.dumps({
            'body': '匿名讨论测试', 'request_key': str(uuid.uuid4())}), content_type='application/json')
        self.assertEqual(comment.status_code, 201)
        self.assertEqual(comment.json()['author'], first.first_name)
        vote = self.client.put(base + 'ratings/interesting/', '{"value":5}', content_type='application/json')
        self.assertEqual(vote.status_code, 200)
        self.assertEqual(self.client.post('/logout/').status_code, 302)
        self.assertEqual(self.client.get(base + 'ratings/').status_code, 401)
        landing = self.client.get('/login/')
        self.assertContains(landing, first.first_name)
        self.assertContains(landing, '推荐沿用')
        soup = BeautifulSoup(landing.content, 'html.parser')
        self.assertEqual(soup.select_one('#anonymous-login form input[name=action]')['value'], 'resume')
        self.assertIsNone(soup.select_one('.guest-switch').get('open'))
        same = self.enter(action='resume')
        self.assertEqual(same.pk, first.pk)
        self.assertEqual(self.client.get(base + 'ratings/').json()['interesting']['mine'], 5)
        self.assertTrue(self.client.get(base + 'comments/').json()['comments'][0]['can_edit'])
        self.client.post('/logout/')
        second = self.enter()
        self.assertNotEqual(first.pk, second.pk)
        self.assertNotEqual(first.first_name, second.first_name)
        summary = self.client.get(base + 'ratings/').json()['interesting']
        self.assertEqual(summary, {'average': 5.0, 'count': 1, 'mine': None})
        old = self.client.get(base + 'comments/').json()['comments'][0]
        self.assertEqual(old['author'], first.first_name)
        self.assertFalse(old['can_edit'])
        response = self.client.patch(base + f'comments/{old["id"]}/', '{"body":"改写"}', content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Comment.objects.get().user_id, first.pk)
        self.assertEqual(Rating.objects.get().user_id, first.pk)

    def test_two_anonymous_readers_have_independent_scores_and_no_admin_access(self):
        paper = make_paper()
        a = self.enter()
        other = Client()
        b = self.enter(other)
        self.assertNotEqual(a.pk, b.pk)
        endpoint = f'/api/papers/{paper.pk}/ratings/importance/'
        for client, value in [(self.client, 2), (other, 4)]:
            self.assertEqual(client.put(endpoint, json.dumps({'value': value}), content_type='application/json').status_code, 200)
        result = other.get(f'/api/papers/{paper.pk}/ratings/').json()['importance']
        self.assertEqual(result, {'average': 3.0, 'count': 2, 'mine': 4})
        self.assertEqual(other.get('/admin/').status_code, 302)
        self.assertIn('/admin/login/', other.get('/admin/')['Location'])
        self.assertEqual(other.get('/password/').status_code, 403)
        self.assertEqual(other.post('/password/', {}).status_code, 403)
        b.refresh_from_db()
        self.assertFalse(b.has_usable_password())

    def test_entry_preserves_local_destination_and_rejects_external_or_loop_redirect(self):
        paper = make_paper()
        path = f'/papers/{paper.pk}/?view=read#p-introduction'
        self.assertEqual(self.client.post('/anonymous/', {'action': 'new', 'next': path})['Location'], path)
        for destination in ['https://outside.invalid/', '//outside.invalid/', '/login/', '/login/?next=/login/', '/logout/', '/account/login/', '/register/', '/anonymous/']:
            self.assertEqual(self.client.post('/anonymous/', {'action': 'resume', 'next': destination})['Location'], '/')

    def test_reader_shows_generated_identity_for_comments_and_scores(self):
        user = self.enter()
        paper = make_paper()
        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=Path(directory)):
            write_bundle(Path(directory) / 'papers' / str(paper.pk), load_article(MINI.encode()), MINI.encode())
            response = self.client.get(f'/papers/{paper.pk}/')
        self.assertContains(response, f'本次评分身份：{user.first_name}')
        self.assertContains(response, f'本次评论昵称：{user.first_name}')
        self.assertContains(self.client.get('/upload/'), '标准双语 HTML')

    def test_fixed_accounts_still_use_separate_password_login(self):
        password = secrets.token_urlsafe(20)
        user = User.objects.create_user('test_admin', password=password, is_staff=True, is_superuser=True)
        response = self.client.post('/account/login/', {'username': user.username, 'password': password})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session[SESSION_KEY]), user.pk)
        self.assertContains(self.client.get('/'), '修改密码')
        self.assertEqual(self.client.get('/password/').status_code, 200)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.assertEqual(self.client.get('/login/').status_code, 200)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(int(self.client.session[SESSION_KEY]), user.pk)

    def test_saved_identity_survives_session_loss_and_renews_long_lived_cookie(self):
        original = self.enter()
        returning = Client()
        returning.cookies[settings.ANONYMOUS_COOKIE_NAME] = self.client.cookies[settings.ANONYMOUS_COOKIE_NAME].value
        self.assertContains(returning.get('/login/'), original.first_name)
        self.assertNotIn(SESSION_KEY, returning.session)
        self.assertEqual(self.enter(returning, action='resume').pk, original.pk)
        self.assertEqual(returning.cookies[settings.ANONYMOUS_COOKIE_NAME]['max-age'], settings.ANONYMOUS_COOKIE_AGE)
        self.assertEqual(User.objects.count(), 1)

    def test_tampered_expired_or_disabled_guest_cannot_be_resumed(self):
        original = self.enter()
        token = self.client.cookies[settings.ANONYMOUS_COOKIE_NAME].value
        tampered = Client()
        tampered.cookies[settings.ANONYMOUS_COOKIE_NAME] = token + 'x'
        self.assertNotContains(tampered.get('/login/'), original.first_name)
        self.assertEqual(tampered.post('/anonymous/', {'action': 'resume', 'user_id': original.pk}).status_code, 400)
        expired = Client()
        with patch('django.core.signing.TimestampSigner.timestamp', return_value='1'):
            response = HttpResponse()
            remember_anonymous_reader(response, original)
        expired.cookies[settings.ANONYMOUS_COOKIE_NAME] = response.cookies[settings.ANONYMOUS_COOKIE_NAME].value
        self.assertEqual(expired.post('/anonymous/', {'action': 'resume'}).status_code, 400)
        original.is_active = False
        original.save(update_fields=['is_active'])
        disabled = Client()
        disabled.cookies[settings.ANONYMOUS_COOKIE_NAME] = token
        self.assertEqual(disabled.post('/anonymous/', {'action': 'resume'}).status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_saved_cookie_cannot_restore_regular_or_admin_accounts(self):
        for extra in [{}, {'is_staff': True, 'is_superuser': True}]:
            user = User.objects.create_user('fixed_' + uuid.uuid4().hex, password=secrets.token_urlsafe(20), **extra)
            # Even a correctly signed token must never act as a password bypass.
            response = HttpResponse()
            remember_anonymous_reader(response, user)
            client = Client()
            client.cookies[settings.ANONYMOUS_COOKIE_NAME] = response.cookies[settings.ANONYMOUS_COOKIE_NAME].value
            self.assertEqual(client.post('/anonymous/', {'action': 'resume'}).status_code, 400)
            self.assertNotIn(SESSION_KEY, client.session)

    def test_previous_version_active_guest_is_remembered_before_logout(self):
        previous = create_anonymous_reader()
        self.client.force_login(previous)
        self.assertNotIn(settings.ANONYMOUS_COOKIE_NAME, self.client.cookies)
        self.client.post('/logout/')
        self.assertIn(settings.ANONYMOUS_COOKIE_NAME, self.client.cookies)
        self.assertEqual(self.enter(action='resume').pk, previous.pk)

    def test_new_identity_replaces_remembered_one_without_touching_old_records(self):
        first = self.enter()
        first_token = self.client.cookies[settings.ANONYMOUS_COOKIE_NAME].value
        second = self.enter()
        second_token = self.client.cookies[settings.ANONYMOUS_COOKIE_NAME].value
        self.assertNotEqual(first_token, second_token)
        self.assertNotEqual(first.pk, second.pk)
        self.client.post('/logout/')
        page = self.client.get('/login/')
        self.assertContains(page, second.first_name)
        self.assertNotContains(page, first.first_name)
        self.assertEqual(self.enter(action='resume').pk, second.pk)
