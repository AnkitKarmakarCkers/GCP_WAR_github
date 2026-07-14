# """
# Cloud Scheduler recommendations.

# Re-fetches every Cloud Scheduler job in every in-scope project (reusing
# inventory.py's job-fetching logic) and evaluates each job against a
# fixed set of WAR rules. Every rule a job triggers becomes one row in
# the "Cloud Scheduler Recommendations" tab of the WAR sheet.

# Configuration (optional environment variables):
#     SCHEDULER_STALE_DAYS   Days since last successful/attempted run
#                            before an ENABLED job is flagged "stale".
#                            Default: 30.

# Notes on rule interpretation (spec was intentionally literal; a few
# rules needed a concrete decision to avoid false positives):

# - "Failed Last Execution" is scoped to Status == "Failed" specifically,
#   not "Status != Success" literally, so jobs that have simply never
#   run yet aren't mislabeled as "failed".
# - "Missing Service Account" only evaluates HTTP-target jobs. App
#   Engine targets run as the App Engine default service account and
#   Pub/Sub targets have no per-job service account concept at all, so
#   flagging every non-HTTP job would be noise, not a real finding.
# - "Stale Scheduler Job" only evaluates jobs that have run at least
#   once (Last Run is set). A job that's ENABLED but has literally
#   never executed is a different problem than staleness.
# - "High Frequency Schedule" estimates executions/day by walking the
#   cron schedule with croniter over a 24h window (exact, not a regex
#   guess) rather than assuming a specific cron dialect by hand.
#   Requires the 'croniter' package: pip install croniter
# """

# import datetime as dt
# import logging
# import os

# from croniter import croniter
# from google.cloud import scheduler_v1

# from module.cloud_scheduler.inventory import (
#     _fmt_duration,
#     _fmt_timestamp,
#     _get_last_execution_status,
#     _get_target_info,
#     iter_project_jobs,
# )
# from utils.gsheet_helper import write_to_sheet


# SHEET_NAME = "Cloud Scheduler Recommendations"

# HEADERS = [
#     "Project ID",
#     "Region",
#     "Job Name",
#     "Service",
#     "Recommendation Title",
#     "Pillar",
#     "Recommendation",
#     "Columns Evaluated",
#     "Condition",
#     "Observed Value",
# ]

# SERVICE_NAME = "Cloud Scheduler"

# HIGH_FREQUENCY_THRESHOLD_PER_DAY = 96

# STALE_DAYS_THRESHOLD = int(os.getenv("SCHEDULER_STALE_DAYS", "30"))


# def _estimate_daily_executions(cron_expr, cap=100000):
#     """
#     Returns the number of times a cron schedule fires in a 24h window,
#     computed exactly with croniter rather than guessed from the string
#     shape. Returns None if the schedule can't be parsed (e.g. it's an
#     App Engine legacy "every N minutes" string instead of unix-cron).
#     """

#     try:

#         base = dt.datetime(2026, 1, 1)
#         start = base - dt.timedelta(seconds=1)
#         end = base + dt.timedelta(days=1)

#         itr = croniter(cron_expr, start)
#         count = 0

#         while count < cap:

#             nxt = itr.get_next(dt.datetime)

#             if nxt >= end:
#                 break

#             count += 1

#         return count

#     except (ValueError, KeyError):

#         return None


# def _extract_job_facts(job):
#     """
#     Pulls the specific fields the rules below need out of a raw Job
#     proto, matching the same derivations inventory.py uses so the two
#     sheets stay consistent with each other.
#     """

#     target_type = job._pb.WhichOneof("target")
#     _, service_account = _get_target_info(job)

#     retry_config = job.retry_config

#     return {
#         "job_name": job.name.split("/")[-1],
#         "state": job.state.name,
#         "status": _get_last_execution_status(job),
#         "last_run": job.last_attempt_time,
#         "cron_schedule": job.schedule,
#         "target_type": target_type,
#         "service_account": service_account,
#         "retry_enabled": bool(retry_config.retry_count),
#         "max_retry_attempts": retry_config.retry_count,
#         "max_retry_duration": retry_config.max_retry_duration,
#     }


# # --- Individual rule checks -------------------------------------------
# # Each returns an "observed value" string when the job trips the rule,
# # or None when it doesn't.

# def _rule_disabled_job(facts):

#     if facts["state"] == "DISABLED":
#         return f"State = {facts['state']}"

#     return None


# def _rule_failed_last_execution(facts):

#     if facts["status"] == "Failed":
#         return f"Status of Last Execution = {facts['status']}"

#     return None


# def _rule_no_retry_policy(facts):

#     if not facts["retry_enabled"] or facts["max_retry_attempts"] == 0:
#         return (
#             f"Retry Enabled = {'Yes' if facts['retry_enabled'] else 'No'}, "
#             f"Max Retry Attempts = {facts['max_retry_attempts']}"
#         )

#     return None


# def _rule_unlimited_retry_duration(facts):

#     if not facts["max_retry_duration"]:
#         return "Max Retry Duration = 0s"

#     return None


# def _rule_missing_service_account(facts):

#     if facts["target_type"] != "http_target":
#         return None

#     if not facts["service_account"]:
#         return "Service Account = (empty)"

#     return None


# def _rule_stale_job(facts):

#     if facts["state"] != "ENABLED":
#         return None

#     if not facts["last_run"]:
#         return None

#     last_run = facts["last_run"]

#     if last_run.tzinfo is None:
#         last_run = last_run.replace(tzinfo=dt.timezone.utc)

#     now = dt.datetime.now(dt.timezone.utc)
#     age_days = (now - last_run).days

#     if age_days > STALE_DAYS_THRESHOLD:
#         return (
#             f"State = ENABLED, Last Run = {_fmt_timestamp(facts['last_run'])} "
#             f"({age_days} days ago)"
#         )

#     return None


# def _rule_high_frequency(facts):

#     daily_count = _estimate_daily_executions(facts["cron_schedule"])

#     if daily_count is None:
#         return None

#     if daily_count > HIGH_FREQUENCY_THRESHOLD_PER_DAY:
#         return (
#             f"Cron Schedule = '{facts['cron_schedule']}' "
#             f"(~{daily_count} executions/day)"
#         )

#     return None


# RULES = [
#     {
#         "title": "Disabled Scheduler Job",
#         "pillar": "Operational Excellence",
#         "recommendation": "Remove Disabled Scheduler Jobs",
#         "columns": "State",
#         "condition": "State = DISABLED",
#         "check": _rule_disabled_job,
#     },
#     {
#         "title": "Failed Last Execution",
#         "pillar": "Reliability",
#         "recommendation": "Review job as the most recent execution failed",
#         "columns": "Status of Last Execution",
#         "condition": "Status != Success",
#         "check": _rule_failed_last_execution,
#     },
#     {
#         "title": "No Retry Policy Configured",
#         "pillar": "Reliability",
#         "recommendation": "Configure retries for critical workloads",
#         "columns": "Retry Enabled, Max Retry Attempts",
#         "condition": "Retry Enabled = No OR Max Retry Attempts = 0",
#         "check": _rule_no_retry_policy,
#     },
#     {
#         "title": "Unlimited Retry Duration",
#         "pillar": "Reliability",
#         "recommendation": (
#             "Review: job configured with unlimited retry duration to "
#             "avoid excessive retries"
#         ),
#         "columns": "Max Retry Duration",
#         "condition": "Max Retry Duration = 0s",
#         "check": _rule_unlimited_retry_duration,
#     },
#     {
#         "title": "Missing Service Account",
#         "pillar": "Security",
#         "recommendation": (
#             "Configure a dedicated service account for job authentication."
#         ),
#         "columns": "Service Account",
#         "condition": "Service Account is NULL or Empty",
#         "check": _rule_missing_service_account,
#     },
#     {
#         "title": "Stale Scheduler Job",
#         "pillar": "Operational Excellence",
#         "recommendation": "Remove Stale jobs",
#         "columns": "State, Last Run",
#         "condition": (
#             f"State = ENABLED and Last Run older than "
#             f"{STALE_DAYS_THRESHOLD} days"
#         ),
#         "check": _rule_stale_job,
#     },
#     {
#         "title": "High Frequency Schedule",
#         "pillar": "Cost",
#         "recommendation": "Job configured with very high frequency",
#         "columns": "Cron Schedule",
#         "condition": (
#             f"Estimated executions per day > "
#             f"{HIGH_FREQUENCY_THRESHOLD_PER_DAY}"
#         ),
#         "check": _rule_high_frequency,
#     },
# ]


# def _evaluate_job(project_id, location, job):
#     """Runs every rule against one job, returning one row per hit."""

#     facts = _extract_job_facts(job)

#     rows = []

#     for rule in RULES:

#         observed_value = rule["check"](facts)

#         if observed_value is None:
#             continue

#         rows.append(
#             {
#                 "Project ID": project_id,
#                 "Region": location,
#                 "Job Name": facts["job_name"],
#                 "Service": SERVICE_NAME,
#                 "Recommendation Title": rule["title"],
#                 "Pillar": rule["pillar"],
#                 "Recommendation": rule["recommendation"],
#                 "Columns Evaluated": rule["columns"],
#                 "Condition": rule["condition"],
#                 "Observed Value": observed_value,
#             }
#         )

#     return rows


# def main(credentials, org_id, projects):

#     scheduler_client = scheduler_v1.CloudSchedulerClient(
#         credentials=credentials
#     )

#     rows = []

#     for project in projects:

#         project_id = project["project_id"]
#         project_job_count = 0
#         project_finding_count = 0

#         for location, job in iter_project_jobs(scheduler_client, project_id):

#             project_job_count += 1

#             job_rows = _evaluate_job(project_id, location, job)

#             rows.extend(job_rows)
#             project_finding_count += len(job_rows)

#         if project_job_count:
#             logging.info(
#                 f"[{project_id}] Evaluated {project_job_count} job(s), "
#                 f"{project_finding_count} finding(s)."
#             )

#     write_to_sheet(
#         credentials=credentials,
#         sheet_name=SHEET_NAME,
#         rows=rows,
#         headers=HEADERS,
#     )

#     logging.info(
#         f"Cloud Scheduler recommendations complete — {len(rows)} finding(s) total."
#     )