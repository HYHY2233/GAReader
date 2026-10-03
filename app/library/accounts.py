from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .forms import LoginForm, RegistrationForm
from .identity import (create_anonymous_reader, is_anonymous_reader, last_anonymous_reader,
                       remember_anonymous_reader)


def destination_after_login(request):
    destination = request.POST.get('next', request.GET.get('next', ''))
    if not url_has_allowed_host_and_scheme(destination, {request.get_host()},
                                          require_https=request.is_secure()):
        return '/'
    if urlsplit(destination).path.rstrip('/') in {
            '/login', '/logout', '/account/login', '/register', '/anonymous'}:
        return '/'
    return destination


def entry_context(request, **kwargs):
    return {'next': destination_after_login(request), 'last_guest': last_anonymous_reader(request), **kwargs}


class AccountLoginView(LoginView):
    template_name = 'registration/login.html'
    authentication_form = LoginForm

    def get_success_url(self):
        return destination_after_login(self.request)

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), **entry_context(self.request)}

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        return response


@sensitive_post_parameters('password1', 'password2')
@never_cache
@csrf_protect
@require_http_methods(['GET', 'POST'])
def register(request):
    form = RegistrationForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST':
        try:
            # Serialize duplicate-name checks and creation on SQLite.
            with transaction.atomic():
                if form.is_valid():
                    user = form.save()
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                    request.session.set_expiry(settings.SESSION_COOKIE_AGE)
                    return redirect(destination_after_login(request))
        except IntegrityError:
            form.add_error('username', '这个登录名已被使用，请换一个。')
    return render(request, 'registration/register.html', entry_context(request, form=form))


@never_cache
@csrf_protect
@require_http_methods(['GET', 'POST'])
def anonymous_login(request):
    destination = destination_after_login(request)
    if request.method == 'GET':
        return redirect('/login/?' + urlencode({'next': destination}) + '#anonymous-login')
    action = request.POST.get('action')
    remembered = last_anonymous_reader(request)
    if action not in {'resume', 'new'} or (action == 'resume' and remembered is None):
        return render(request, 'registration/login.html', entry_context(
            request, form=LoginForm(request), anonymous_error='上次身份已不可用，请选择新的匿名身份。'
        ), status=400)
    with transaction.atomic():
        user = remembered if action == 'resume' else create_anonymous_reader()
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        request.session.set_expiry(settings.SESSION_COOKIE_AGE)
    response = redirect(destination)
    remember_anonymous_reader(response, user)
    return response


@login_required
def password(request):
    if is_anonymous_reader(request.user):
        return HttpResponseForbidden('匿名身份不设置密码。')
    return PasswordChangeView.as_view(template_name='registration/password.html', success_url='/')(request)
