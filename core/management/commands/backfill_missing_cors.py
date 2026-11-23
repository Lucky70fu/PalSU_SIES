from django.core.management.base import BaseCommand
from core.models import Enrollment
from core.services import ensure_cor_for_enrolled


class Command(BaseCommand):
    help = "Issue a missing initial COR for existing ENROLLED records without duplicating existing CORs."

    def handle(self, *args, **options):
        created = 0
        skipped = 0
        queryset = Enrollment.objects.filter(status__in=["APPROVED", "ENROLLED"])
        for enrollment in queryset.iterator():
            before = enrollment.cor_versions.exists()
            cor = ensure_cor_for_enrolled(enrollment)
            if not before and cor is not None:
                created += 1
            elif cor is None:
                skipped += 1
        self.stdout.write(self.style.SUCCESS(
            f"COR backfill complete: {created} created, {skipped} skipped, existing CORs preserved."
        ))
