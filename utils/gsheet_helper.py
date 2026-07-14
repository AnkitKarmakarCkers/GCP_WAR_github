import json
import logging
import math
import os

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

SPREADSHEET_ID = os.getenv("SHEET_ID")


def get_sheets_service(credentials):
    """
    Returns an authenticated Google Sheets API client.
    """
    return build(
        "sheets",
        "v4",
        credentials=credentials,
        cache_discovery=False,
    )


def _normalize_value(value):
    """
    Converts Python objects into values suitable for Google Sheets.
    """

    if value is None:
        return ""

    if isinstance(value, (list, dict)):
        try:
            return json.dumps(
                value,
                ensure_ascii=False,
            )
        except Exception:
            return str(value)

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""

    return str(value)


def ensure_sheet_exists(
    service,
    spreadsheet_id,
    sheet_name,
):
    """
    Creates the sheet if it does not already exist.
    """

    metadata = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id
    ).execute()

    for sheet in metadata.get("sheets", []):

        if sheet["properties"]["title"] == sheet_name:
            return

    body = {
        "requests": [
            {
                "addSheet": {
                    "properties": {
                        "title": sheet_name,
                    }
                }
            }
        ]
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=body,
    ).execute()

    logging.info(
        f"Created sheet '{sheet_name}'."
    )


def clear_sheet(
    service,
    spreadsheet_id,
    sheet_name,
):
    """
    Removes all values from a sheet.
    """

    try:

        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'",
        ).execute()

    except HttpError:
        pass


def read_sheet(
    credentials,
    sheet_name,
):
    """
    Reads an entire sheet and returns a list of dictionaries.
    """

    if not SPREADSHEET_ID:
        raise ValueError(
            "SHEET_ID not found in .env"
        )

    service = get_sheets_service(credentials)

    try:

        result = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=SPREADSHEET_ID,
                range=f"'{sheet_name}'",
            )
            .execute()
        )

        values = result.get("values", [])

        if not values:

            logging.info(
                f"Sheet '{sheet_name}' is empty."
            )

            return []

        headers = values[0]

        rows = []

        for row in values[1:]:

            row += [""] * (len(headers) - len(row))

            rows.append(
                dict(zip(headers, row))
            )

        logging.info(
            f"Read {len(rows)} rows from '{sheet_name}'."
        )

        return rows

    except HttpError as error:

        logging.error(
            f"Failed reading sheet '{sheet_name}': {error}"
        )

        return []


def write_to_sheet(
    credentials,
    sheet_name,
    rows,
    headers=None,
):
    """
    Completely overwrites a Google Sheet with supplied rows.
    """

    if not SPREADSHEET_ID:
        raise ValueError(
            "SHEET_ID not found in .env"
        )

    if not rows:

        logging.info(
            f"No data to write for '{sheet_name}'."
        )

        return

    service = get_sheets_service(credentials)

    ensure_sheet_exists(
        service,
        SPREADSHEET_ID,
        sheet_name,
    )

    clear_sheet(
        service,
        SPREADSHEET_ID,
        sheet_name,
    )

    if headers is None:
        headers = list(rows[0].keys())

    values = [headers]

    for row in rows:

        values.append(
            [
                _normalize_value(
                    row.get(header, "")
                )
                for header in headers
            ]
        )

    body = {
        "values": values
    }

    try:

        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!A1",
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()

        logging.info(
            f"Wrote {len(rows)} rows to '{sheet_name}'."
        )

    except HttpError as error:

        logging.error(
            f"Failed writing '{sheet_name}': {error}"
        )


def append_columns(
    rows,
    columns,
    default_value="",
):
    """
    Ensures every row contains the supplied columns.

    Example:
        append_columns(
            rows,
            [
                "Operational Excellence",
                "Reliability",
                "Security",
                "Cost",
            ],
            "No Recommendation",
        )
    """

    for row in rows:

        for column in columns:

            if column not in row:

                row[column] = default_value

    return rows