from django.core.management.base import BaseCommand, CommandError

from maintenance.tenant_integrity import run_tenant_integrity_checks


class Command(BaseCommand):
    help = "Check tenant-owned relationships for cross-company inconsistencies."

    def handle(self, *args, **options):
        results = run_tenant_integrity_checks()
        total_violations = sum(result.violations for result in results)

        self.stdout.write("Tenant integrity checks")
        for result in results:
            message = f"{result.name}: {result.violations}"
            if result.violations:
                self.stdout.write(self.style.ERROR(f"[FAIL] {message}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"[OK] {message}"))

        if total_violations:
            raise CommandError(
                f"Tenant integrity check failed with {total_violations} violation(s)."
            )

        self.stdout.write(self.style.SUCCESS("All tenant integrity checks passed."))
