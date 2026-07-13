from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run the independent daily backup and work-order generation jobs."

    def handle(self, *args, **options):
        failures = []
        for command_name in ("backup_to_b2", "generate_work_orders"):
            self.stdout.write(f"\n--- Running {command_name} ---")
            try:
                call_command(
                    command_name,
                    stdout=self.stdout,
                    stderr=self.stderr,
                )
            except Exception as exc:
                failures.append((command_name, exc))
                self.stderr.write(self.style.ERROR(
                    f"{command_name} failed: {exc}"
                ))

        if failures:
            failed_names = ", ".join(name for name, _exc in failures)
            raise CommandError(f"Daily operations failed: {failed_names}")

        self.stdout.write(self.style.SUCCESS("\nAll daily operations completed."))
