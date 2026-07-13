from contextlib import contextmanager
import logging

from django.utils import timezone

from .models import JobRun


logger = logging.getLogger(__name__)


@contextmanager
def tracked_job_run(job_name, *, company=None, metadata=None):
    job_run = JobRun.objects.create(
        job_name=job_name,
        company=company,
        metadata=metadata or {},
    )
    try:
        yield job_run
    except Exception as exc:
        job_run.status = JobRun.Status.FAILED
        job_run.finished_at = timezone.now()
        job_run.error_message = f"{type(exc).__name__}: {exc}"[:4000]
        job_run.save(update_fields=[
            "status",
            "finished_at",
            "error_message",
        ])
        logger.exception(
            "Tracked job failed",
            extra={
                "job_name": job_name,
                "job_run_id": job_run.pk,
                "company_id": job_run.company_id,
            },
        )
        raise
    else:
        job_run.status = JobRun.Status.SUCCESS
        job_run.finished_at = timezone.now()
        job_run.save(update_fields=[
            "status",
            "finished_at",
            "result",
        ])
        logger.info(
            "Tracked job completed",
            extra={
                "job_name": job_name,
                "job_run_id": job_run.pk,
                "company_id": job_run.company_id,
                "result": job_run.result,
            },
        )
