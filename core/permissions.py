from django.contrib.auth.decorators import user_passes_test

ROLE_GROUPS = {
    "Administrator": {"dashboard","students","academics","enrollment","billing","schedules","grades","reports"},
    "Registrar": {"dashboard","students","enrollment","academics","schedules","reports"},
    "Cashier": {"dashboard","billing","reports"},
    "Instructor": {"dashboard","grades","schedules"},
    "Student": {"dashboard","students","enrollment","billing","schedules","grades"},
}
def role_required(*allowed):
    def check(user):
        return user.is_authenticated and (user.is_superuser or user.groups.filter(name__in=allowed).exists())
    return user_passes_test(check)
def can_access(user, module):
    if user.is_superuser: return True
    groups = set(user.groups.values_list("name", flat=True))
    return any(module in ROLE_GROUPS.get(g, set()) for g in groups)
