import secrets

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import User
from django.test import Client, TestCase


class AccountEntryTests(TestCase):
    def registration(self, **overrides):
        password = secrets.token_urlsafe(24)
        return {'username': 'paper_reader', 'first_name': '阅读者',
                'password1': password, 'password2': password, **overrides}

    def test_register_then_logout_and_login_with_password(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get('/register/?next=/upload/')
        self.assertContains(response, '注册并登录')
        self.assertContains(response, '匿名登录')
        data = self.registration(is_staff='true', is_superuser='true', next='/upload/')
        self.assertEqual(client.post('/register/', data).status_code, 403)
        self.assertFalse(User.objects.exists())
        data['csrfmiddlewaretoken'] = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post('/register/', data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/upload/')
        user = User.objects.get()
        self.assertTrue(user.check_password(data['password1']))
        self.assertNotEqual(user.password, data['password1'])
        self.assertEqual(user.first_name, '阅读者')
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(int(client.session[SESSION_KEY]), user.pk)
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        self.assertEqual(client.post('/logout/', {'csrfmiddlewaretoken': token}).status_code, 302)
        client.get('/login/')
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        failed = client.post('/login/', {'username': user.username, 'password': 'incorrect', 'csrfmiddlewaretoken': token})
        self.assertContains(failed, '登录名或密码不正确')
        self.assertNotIn(SESSION_KEY, client.session)
        response = client.post('/login/', {'username': user.username, 'password': data['password1'], 'csrfmiddlewaretoken': token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(client.session[SESSION_KEY]), user.pk)

    def test_registration_rejects_duplicates_reserved_names_and_invalid_passwords(self):
        User.objects.create_user('Existing', password=secrets.token_urlsafe(20))
        for data in [self.registration(username='existing'), self.registration(username='guest_custom'),
                     self.registration(username='GUEST_custom'), self.registration(username='invalid name'),
                     self.registration(password1='123', password2='123'),
                     self.registration(password2='not-the-same'), self.registration(username='')]:
            with self.subTest(username=data['username']):
                response = self.client.post('/register/', data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertNotIn(SESSION_KEY, self.client.session)
                self.assertEqual(User.objects.count(), 1)

    def test_regular_login_requires_password_and_does_not_create_guest(self):
        User.objects.create_user('known', password=secrets.token_urlsafe(20))
        response = self.client.post('/login/', {'username': 'known'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('password', response.context['form'].errors)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(User.objects.count(), 1)

    def test_registration_and_login_cannot_redirect_outside_or_back_to_auth(self):
        data = self.registration(next='https://outside.invalid/')
        self.assertEqual(self.client.post('/register/', data)['Location'], '/')
        self.client.post('/logout/')
        for destination in ['//outside.invalid/', '/login/', '/account/login/', '/register/', '/anonymous/']:
            response = self.client.post('/login/', {'username': data['username'], 'password': data['password1'], 'next': destination})
            self.assertEqual(response['Location'], '/')

    def test_registering_from_anonymous_keeps_previous_identity_available(self):
        self.client.post('/anonymous/', {'action': 'new'})
        previous = self.client.session[SESSION_KEY]
        response = self.client.post('/register/', self.registration())
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(previous, self.client.session[SESSION_KEY])
        self.client.post('/logout/')
        self.assertEqual(self.client.post('/anonymous/', {'action': 'resume'}).status_code, 302)
        self.assertEqual(self.client.session[SESSION_KEY], previous)

    def test_empty_nickname_and_inactive_account(self):
        data = self.registration(first_name='')
        self.client.post('/register/', data)
        self.assertContains(self.client.get('/'), data['username'])
        self.client.post('/logout/')
        user = User.objects.get(username=data['username'])
        user.is_active = False
        user.save(update_fields=['is_active'])
        response = self.client.post('/login/', {'username': data['username'], 'password': data['password1']})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)
