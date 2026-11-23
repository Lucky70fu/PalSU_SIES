from django.shortcuts import redirect
class ForcePasswordChangeMiddleware:
    EXEMPT_PATHS = {"/accounts/password/change/", "/accounts/password/change/done/", "/accounts/logout/"}
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and request.path_info not in self.EXEMPT_PATHS:
            from .models import Student
            if Student.objects.filter(user=user, must_change_password=True).exists():
                return redirect("password_change")
        return self.get_response(request)
