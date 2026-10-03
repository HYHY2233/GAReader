"""Remember anonymous identities in this browser without accepting names as credentials."""
import secrets
import uuid

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.signing import BadSignature
from django.db import transaction
from django.utils.crypto import constant_time_compare


MOODS = ('打盹的', '软乎乎的', '抱着星星的', '追月亮的', '晒太阳的', '捧着奶茶的',
         '戴围巾的', '爱看书的', '慢悠悠的', '吃布丁的', '听雨的', '数云朵的')
ANIMALS = ('小海獭', '小熊猫', '小兔子', '小猫咪', '小企鹅', '小刺猬',
           '小松鼠', '小绵羊', '小狐狸', '小水豚', '小海豹', '小仓鼠')


def is_anonymous_reader(user):
    return (user.is_authenticated and user.is_active and not user.is_staff and not user.is_superuser
            and user.username.startswith('guest_')
            and not user.has_usable_password())


def reader_identity(request):
    return {'anonymous_reader': is_anonymous_reader(request.user)}


COOKIE_SALT = 'paper-library.anonymous-identity.v1'


def saved_anonymous_reader(request):
    """A signed browser token can resume only an active, unprivileged guest."""
    try:
        token = request.get_signed_cookie(settings.ANONYMOUS_COOKIE_NAME, salt=COOKIE_SALT,
                                          max_age=settings.ANONYMOUS_COOKIE_AGE)
        user_id, auth_hash = token.split(':', 1)
        user = get_user_model().objects.filter(pk=int(user_id)).first()
        if (user and is_anonymous_reader(user)
                and constant_time_compare(auth_hash, user.get_session_auth_hash())):
            return user
    except (KeyError, BadSignature, ValueError, OverflowError):
        pass
    return None


def last_anonymous_reader(request):
    # Also preserves the anonymous session created before browser memory was added.
    return request.user if is_anonymous_reader(request.user) else saved_anonymous_reader(request)


def remember_anonymous_reader(response, user):
    response.set_signed_cookie(
        settings.ANONYMOUS_COOKIE_NAME, f'{user.pk}:{user.get_session_auth_hash()}',
        salt=COOKIE_SALT, max_age=settings.ANONYMOUS_COOKIE_AGE, httponly=True,
        secure=settings.SESSION_COOKIE_SECURE, samesite='Strict', path='/',
    )


class RememberAnonymousIdentityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        previous = request.user if is_anonymous_reader(request.user) else None
        response = self.get_response(request)
        guest = request.user if is_anonymous_reader(request.user) else previous
        if guest and response.status_code < 500 and settings.ANONYMOUS_COOKIE_NAME not in response.cookies:
            saved = saved_anonymous_reader(request)
            if saved is None or saved.pk != guest.pk:
                remember_anonymous_reader(response, guest)
        return response


@transaction.atomic
def create_anonymous_reader():
    user = get_user_model().objects.create_user(username='guest_' + uuid.uuid4().hex)
    # The small number distinguishes identical random word combinations.
    user.first_name = f'{secrets.choice(MOODS)}{secrets.choice(ANIMALS)} · {user.pk:04d}'
    user.save(update_fields=['first_name'])
    return user
