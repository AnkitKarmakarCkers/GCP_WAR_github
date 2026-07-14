import datetime as dt
import logging
import os

from croniter import croniter

from utils.gsheet_helper import (
    read_sheet,
    write_to_sheet,
)

SHEET_NAME = "Cloud Scheduler Inventory"

STALE_DAYS = int(os.getenv("SCHEDULER_STALE_DAYS", "30"))

HIGH_FREQUENCY_THRESHOLD = 96


def parse_datetime(value):
    """
    Converts ISO timestamp from sheet into datetime.
    """

    if not value:
        return None

    try:
        value = value.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(value)
    except Exception:
        return None


def estimate_daily_runs(cron_expression):
    """
    Estimate executions/day using croniter.
    """

    if not cron_expression:
        return 0

    try:

        base = dt.datetime(2026, 1, 1)
        end = base + dt.timedelta(days=1)

        itr = croniter(cron_expression, base)

        count = 0

        while True:

            nxt = itr.get_next(dt.datetime)

            if nxt >= end:
                break

            count += 1

        return count

    except Exception:

        return 0


def add_recommendation(bucket, text):
    """
    Avoid duplicate recommendations.
    """

    if text not in bucket:
        bucket.append(text)


def evaluate_row(row):

    operational = []
    reliability = []
    security = []
    cost = []

    state = row.get("State", "").strip()

    status = row.get(
        "Status of last execution",
        "",
    ).strip()

    retry_enabled = row.get(
        "Retry Enabled",
        "",
    ).strip()

    retry_attempts = row.get(
        "Max retry attempts",
        "0",
    ).strip()

    retry_duration = row.get(
        "Max retry duration",
        "",
    ).strip()

    service_account = row.get(
        "Service Account",
        "",
    ).strip()

    cron_schedule = row.get(
        "Cron Schedule",
        "",
    ).strip()

    last_run = parse_datetime(
        row.get("Last Run", "")
    )

    #
    # Operational Excellence
    #

    if state == "DISABLED":

        add_recommendation(
            operational,
            "Disabled Scheduler Job",
        )

    if (
        state == "ENABLED"
        and last_run
    ):

        now = dt.datetime.now(
            dt.timezone.utc
        )

        if last_run.tzinfo is None:
            last_run = last_run.replace(
                tzinfo=dt.timezone.utc
            )

        age = (
            now - last_run
        ).days

        if age > STALE_DAYS:

            add_recommendation(
                operational,
                "Stale Scheduler Job",
            )

    #
    # Reliability
    #

    if (
        status
        and status != "Success"
        and status != "Has not run yet"
    ):

        add_recommendation(
            reliability,
            "Failed Last Execution",
        )

    if (
        retry_enabled == "No"
        or retry_attempts in (
            "",
            "0",
        )
    ):

        add_recommendation(
            reliability,
            "No Retry Policy Configured",
        )

    if (
        retry_duration == ""
        or retry_duration == "0s"
    ):

        add_recommendation(
            reliability,
            "Unlimited Retry Duration",
        )

    #
    # Security
    #

    if not service_account:

        add_recommendation(
            security,
            "Missing Service Account",
        )

    #
    # Cost
    #

    executions = estimate_daily_runs(
        cron_schedule
    )

    if executions > HIGH_FREQUENCY_THRESHOLD:

        add_recommendation(
            cost,
            "High Frequency Schedule",
        )

    row["Operational Excellence"] = (
        "\n".join(operational)
        if operational
        else "No Recommendation"
    )

    row["Reliability"] = (
        "\n".join(reliability)
        if reliability
        else "No Recommendation"
    )

    row["Security"] = (
        "\n".join(security)
        if security
        else "No Recommendation"
    )

    row["Cost"] = (
        "\n".join(cost)
        if cost
        else "No Recommendation"
    )

    return row

def main(credentials, org_id, projects):
    """
    Reads the Cloud Scheduler Inventory sheet, evaluates recommendations,
    appends recommendation columns, and writes the updated sheet back.
    """

    logging.info("Reading Cloud Scheduler Inventory...")

    rows = read_sheet(
        credentials=credentials,
        sheet_name=SHEET_NAME,
    )

    if not rows:
        logging.info("No inventory found.")
        return

    #
    # Preserve original column order
    #
    headers = list(rows[0].keys())

    recommendation_columns = [
        "Operational Excellence",
        "Reliability",
        "Security",
        "Cost",
    ]

    #
    # Add recommendation columns if they don't exist
    #
    for column in recommendation_columns:

        if column not in headers:
            headers.append(column)

    updated_rows = []

    total_findings = 0

    for row in rows:

        updated_row = evaluate_row(row)

        updated_rows.append(updated_row)

        #
        # Count findings
        #
        for pillar in recommendation_columns:

            if (
                updated_row[pillar]
                != "No Recommendation"
            ):

                total_findings += len(
                    updated_row[pillar].split("\n")
                )

    write_to_sheet(
        credentials=credentials,
        sheet_name=SHEET_NAME,
        rows=updated_rows,
        headers=headers,
    )

    logging.info(
        f"Cloud Scheduler recommendation completed. "
        f"{len(updated_rows)} jobs evaluated, "
        f"{total_findings} recommendation(s) generated."
    )