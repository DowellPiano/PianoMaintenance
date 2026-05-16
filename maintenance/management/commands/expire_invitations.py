from django.core.management.base import BaseCommand
from django.utils import timezone

from maintenance.models import CompanyInvitation


class Command(BaseCommand):
    help = "Expire pending company invitations whose expiration time has passed."

    def handle(self, *args, **options):
        now = timezone.now()
        expired = CompanyInvitation.objects.filter(
            status=CompanyInvitation.Status.PENDING,
            expires_at__lte=now,
        )
        count = expired.update(status=CompanyInvitation.Status.EXPIRED)
        self.stdout.write(self.style.SUCCESS(f"Expired {count} invitation(s)."))
