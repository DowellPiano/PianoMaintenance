from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from maintenance.models import Company, CompanyMembership, CompanySettings


class Command(BaseCommand):
    help = "Bootstrap a company, company settings, and an initial admin membership for a fresh SaaS environment."

    def add_arguments(self, parser):
        parser.add_argument("--company-name", required=True, help="Display name for the company.")
        parser.add_argument("--slug", help="Optional company slug. Defaults to a slugified company name.")
        parser.add_argument("--admin-username", required=True, help="Username for the initial admin account.")
        parser.add_argument("--admin-password", required=True, help="Password for the initial admin account.")
        parser.add_argument("--admin-email", default="", help="Email for the initial admin account.")
        parser.add_argument("--first-name", default="", help="Admin first name.")
        parser.add_argument("--last-name", default="", help="Admin last name.")

    def handle(self, *args, **options):
        company_name = options["company_name"].strip()
        slug = (options.get("slug") or slugify(company_name)).strip()
        if not slug:
            raise CommandError("Unable to derive a valid company slug. Provide --slug explicitly.")

        User = get_user_model()

        company, company_created = Company.objects.get_or_create(
            slug=slug,
            defaults={"name": company_name},
        )
        if not company_created and company.name != company_name:
            company.name = company_name
            company.save(update_fields=["name"])

        user, user_created = User.objects.get_or_create(
            username=options["admin_username"],
            defaults={
                "email": options["admin_email"],
                "first_name": options["first_name"],
                "last_name": options["last_name"],
                "is_active": True,
                "is_staff": True,
                "is_superuser": False,
                "role_admin": False,
                "role_technician": False,
            },
        )
        if user_created:
            user.set_password(options["admin_password"])
            user.save()
        else:
            user.email = options["admin_email"] or user.email
            user.first_name = options["first_name"] or user.first_name
            user.last_name = options["last_name"] or user.last_name
            user.is_active = True
            user.is_staff = True
            user.set_password(options["admin_password"])
            user.save(update_fields=[
                "email", "first_name", "last_name",
                "is_active", "is_staff", "password",
            ])

        membership, membership_created = CompanyMembership.objects.update_or_create(
            company=company,
            user=user,
            defaults={
                "role_admin": True,
                "role_technician": True,
                "is_active": True,
            },
        )

        settings_obj, settings_created = CompanySettings.objects.get_or_create(
            company=company,
            defaults={"company_name": company.name},
        )
        if not settings_obj.company_name:
            settings_obj.company_name = company.name
            settings_obj.save(update_fields=["company_name"])

        self.stdout.write(
            self.style.SUCCESS(
                "Bootstrap complete for {company} ({slug}). Company created: {company_created}. "
                "Admin user created: {user_created}. Membership created: {membership_created}. "
                "Settings created: {settings_created}.".format(
                    company=company.name,
                    slug=company.slug,
                    company_created=company_created,
                    user_created=user_created,
                    membership_created=membership_created,
                    settings_created=settings_created,
                )
            )
        )
