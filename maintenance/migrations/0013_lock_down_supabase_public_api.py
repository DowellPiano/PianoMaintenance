from django.db import migrations


LOCK_DOWN_PUBLIC_SCHEMA_SQL = """
DO $$
DECLARE
    table_record record;
BEGIN
    -- Supabase exposes tables in the public schema through PostgREST when the
    -- anon/authenticated roles have grants. Django uses a direct database
    -- connection, so these API roles should not have table access by default.
    REVOKE USAGE ON SCHEMA public FROM anon, authenticated;
    REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
    REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
    REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;

    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        REVOKE ALL ON TABLES FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        REVOKE ALL ON SEQUENCES FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        REVOKE ALL ON FUNCTIONS FROM anon, authenticated;

    FOR table_record IN
        SELECT schemaname, tablename
        FROM pg_tables
        WHERE schemaname = 'public'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',
            table_record.schemaname,
            table_record.tablename
        );
    END LOOP;
END $$;
"""


def lock_down_supabase_public_api(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(LOCK_DOWN_PUBLIC_SCHEMA_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("maintenance", "0012_technician_roles"),
    ]

    operations = [
        migrations.RunPython(
            lock_down_supabase_public_api,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
