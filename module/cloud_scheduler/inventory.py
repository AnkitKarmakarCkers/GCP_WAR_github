"""
Cloud Scheduler inventory.

Lists every Cloud Scheduler job in every in-scope project/location and
writes the result to the "Cloud Scheduler Inventory" tab of the WAR sheet.

Required IAM permissions on each in-scope project:
    - cloudscheduler.jobs.list
    - cloudscheduler.locations.list
    - resourcemanager.projects.getIamPolicy   (only needed for the
      "Logging Enabled" column, see _check_logging_enabled())

Notes on a few columns:

- "Target" summarizes whichever target type (HTTP, App Engine, Pub/Sub)
  is configured on the job.
- "Service Account" is only populated for HTTP targets that use an
  OAuth or OIDC token (App Engine targets run as the App Engine default
  service account, Pub/Sub targets don't use one).
- "Logging Enabled" is a best-effort signal, not a literal API field:
  Cloud Scheduler has no per-job logging toggle. Admin Activity logs
  for job create/update/delete are always on and can't be disabled.
  What CAN vary per project is whether Data Access audit logs (which
  additionally capture read-type calls) have been turned on for
  cloudscheduler.googleapis.com. That's what this column reports.
"""

import logging

from google.api_core import exceptions as gax_exceptions
from google.cloud import resourcemanager_v3
from google.cloud import scheduler_v1
from google.iam.v1 import policy_pb2

from utils.gsheet_helper import write_to_sheet


SHEET_NAME = "Cloud Scheduler Inventory"

HEADERS = [
    "Project ID",
    "Job Name",
    "Region",
    "Description",
    "State",
    "Cron Schedule",
    "Timezone",
    "Target",
    "Last Run",
    "Next run",
    "Status of last execution",
    "Service Account",
    "Retry Enabled",
    "Max retry attempts",
    "Max retry duration",
    "Min backoff duration",
    "Max backoff duration",
    "Max doublings",
    "Attempt deadline config",
    "Logging Enabled",
]


def _fmt_timestamp(value):
    """
    Formats a Job timestamp field (already converted by proto-plus to a
    datetime, or None if unset) into an ISO-8601 string.
    """

    if not value:
        return ""

    return value.isoformat()


def _fmt_duration(value):
    """
    Formats a Job duration field (already converted by proto-plus to a
    datetime.timedelta) into a simple "<seconds>s" string.
    A timedelta of 0 means the field was never explicitly set.
    """

    if not value:
        return ""

    total_seconds = value.total_seconds()

    if total_seconds == int(total_seconds):
        return f"{int(total_seconds)}s"

    return f"{total_seconds}s"


def _get_target_info(job):
    """
    Returns (target_description, service_account) for a job, covering
    HTTP, App Engine and Pub/Sub targets.
    """

    target_type = job._pb.WhichOneof("target")

    if target_type == "http_target":

        http_target = job.http_target

        service_account = (
            http_target.oidc_token.service_account_email
            or http_target.oauth_token.service_account_email
        )

        target = f"HTTP [{http_target.http_method.name}] {http_target.uri}"

        return target, service_account

    if target_type == "app_engine_http_target":

        ae_target = job.app_engine_http_target
        routing = ae_target.app_engine_routing

        target = (
            f"App Engine [{ae_target.http_method.name}] "
            f"service={routing.service or 'default'} "
            f"uri={ae_target.relative_uri}"
        )

        return target, ""

    if target_type == "pubsub_target":

        target = f"Pub/Sub topic={job.pubsub_target.topic_name}"

        return target, ""

    return "", ""


def _get_last_execution_status(job):
    """
    Returns the last execution's status using the same three labels
    shown in the Cloud Scheduler console: "Success", "Failed", or
    "Has not run yet". job.status is a google.rpc.Status; code 0 with
    no last_attempt_time is indistinguishable from an explicit success,
    so a job that has never run is checked for and reported separately.
    """

    if not job.last_attempt_time:
        return "Has not run yet"

    if job.status.code == 0:
        return "Success"

    return "Failed"


def _list_locations(client, project_id):
    """
    Returns the list of Cloud Scheduler location IDs for a project.

    Unlike list_jobs(), list_locations() is a plain unary call that
    returns one ListLocationsResponse (locations + next_page_token)
    rather than an auto-paginating Pager, so pages are walked manually.
    """

    locations = []
    page_token = ""

    try:

        while True:

            response = client.list_locations(
                request={
                    "name": f"projects/{project_id}",
                    "page_token": page_token,
                }
            )

            locations.extend(
                location.location_id for location in response.locations
            )

            page_token = response.next_page_token

            if not page_token:
                break

    except gax_exceptions.GoogleAPICallError as error:

        logging.warning(
            f"[{project_id}] Could not list Scheduler locations: {error}"
        )

    return locations


def _check_logging_enabled(iam_client, project_id):
    """
    Best-effort check (see module docstring): returns 'Yes' if Data
    Access audit logging has been explicitly enabled for
    cloudscheduler.googleapis.com (or allServices) on the project,
    otherwise 'Default (Admin Activity only)'.
    """

    try:

        policy = iam_client.get_iam_policy(
            request={"resource": f"projects/{project_id}"}
        )

    except gax_exceptions.GoogleAPICallError as error:

        logging.warning(
            f"[{project_id}] Could not read IAM policy: {error}"
        )

        return "Unknown"

    data_log_types = (
        policy_pb2.AuditLogConfig.DATA_WRITE,
        policy_pb2.AuditLogConfig.DATA_READ,
    )

    for audit_config in policy.audit_configs:

        if audit_config.service not in (
            "cloudscheduler.googleapis.com",
            "allServices",
        ):
            continue

        for log_config in audit_config.audit_log_configs:

            if log_config.log_type in data_log_types:
                return "Yes"

    return "Default (Admin Activity only)"


def _build_row(project_id, location, job, logging_enabled):
    """Builds a single sheet row (dict) for one Cloud Scheduler job."""

    target, service_account = _get_target_info(job)

    retry_config = job.retry_config

    return {
        "Project ID": project_id,
        "Job Name": job.name.split("/")[-1],
        "Region": location,
        "Description": job.description,
        "State": job.state.name,
        "Cron Schedule": job.schedule,
        "Timezone": job.time_zone,
        "Target": target,
        "Last Run": _fmt_timestamp(job.last_attempt_time),
        "Next run": _fmt_timestamp(job.schedule_time),
        "Status of last execution": _get_last_execution_status(job),
        "Service Account": service_account,
        "Retry Enabled": "Yes" if retry_config.retry_count else "No",
        "Max retry attempts": retry_config.retry_count,
        "Max retry duration": _fmt_duration(retry_config.max_retry_duration),
        "Min backoff duration": _fmt_duration(retry_config.min_backoff_duration),
        "Max backoff duration": _fmt_duration(retry_config.max_backoff_duration),
        "Max doublings": retry_config.max_doublings,
        "Attempt deadline config": _fmt_duration(job.attempt_deadline),
        "Logging Enabled": logging_enabled,
    }


def iter_project_jobs(scheduler_client, project_id):
    """
    Yields (location, job) for every Cloud Scheduler job in a project,
    across all of its Scheduler locations. Shared by inventory.py and
    recommendation.py so both pull jobs the same way.
    """

    locations = _list_locations(scheduler_client, project_id)

    if not locations:
        logging.info(
            f"[{project_id}] No Cloud Scheduler locations found, skipping."
        )
        return

    for location in locations:

        parent = scheduler_client.common_location_path(
            project_id, location
        )

        try:

            jobs = scheduler_client.list_jobs(
                request={"parent": parent}
            )

        except gax_exceptions.GoogleAPICallError as error:

            logging.warning(
                f"[{project_id}/{location}] Could not list jobs: {error}"
            )
            continue

        for job in jobs:
            yield location, job


def main(credentials, org_id, projects):

    scheduler_client = scheduler_v1.CloudSchedulerClient(
        credentials=credentials
    )

    iam_client = resourcemanager_v3.ProjectsClient(
        credentials=credentials
    )

    rows = []

    for project in projects:

        project_id = project["project_id"]
        logging_enabled = None
        project_job_count = 0

        for location, job in iter_project_jobs(scheduler_client, project_id):

            if logging_enabled is None:
                logging_enabled = _check_logging_enabled(
                    iam_client, project_id
                )

            rows.append(
                _build_row(
                    project_id,
                    location,
                    job,
                    logging_enabled,
                )
            )

            project_job_count += 1

        if project_job_count:
            logging.info(
                f"[{project_id}] Found {project_job_count} Cloud Scheduler job(s)."
            )

    write_to_sheet(
        credentials=credentials,
        sheet_name=SHEET_NAME,
        rows=rows,
        headers=HEADERS,
    )

    logging.info(
        f"Cloud Scheduler inventory complete — {len(rows)} job(s) total."
    )