from django.http import JsonResponse
from django.db import OperationalError

class BoundaryMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        request.get_host()
        response = self.get_response(request)
        response.setdefault('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        response['Referrer-Policy'] = 'same-origin'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cache-Control'] = 'private, no-store'
        response['X-Paper-Library'] = 'v3'
        return response
    def process_exception(self, request, exception):
        if isinstance(exception, OperationalError) and 'locked' in str(exception).lower():
            return JsonResponse({'error': '数据库暂忙，未保存。请稍后重试。'}, status=503)
