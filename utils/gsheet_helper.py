# utils/gsheet_helper.py
import os
import json
import math
import logging
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load .env to get SHEET_ID
load_dotenv()
SPREADSHEET_ID = os.getenv("SHEET_ID")

def get_sheets_service(credentials):
    """Return Sheets API client using impersonated credentials."""
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)

def _normalize_value(v):
    if v is None:
        return ""
    if isinstance(v, (list, dict)):
        try:
            return json.dumps(v, ensure_ascii=False)
        except Exception:
            return str(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return ""
    return str(v)

def ensure_sheet_exists(service, spreadsheet_id, sheet_name):
    """Create sheet if it doesn't exist."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == sheet_name:
            return
    body = {"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]}
    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()

def clear_sheet(service, spreadsheet_id, sheet_name):
    """Clear all data in a sheet."""
    try:
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'"
        ).execute()
    except Exception:
        pass

def write_to_sheet(credentials, sheet_name, rows, headers=None):
    """Write list of dicts to Google Sheet tab."""
    if not SPREADSHEET_ID:
        raise ValueError("❌ SHEET_ID not found in .env file")

    if not rows:
        logging.info(f"[INFO] No data to write for {sheet_name}")
        return

    service = get_sheets_service(credentials)
    ensure_sheet_exists(service, SPREADSHEET_ID, sheet_name)
    clear_sheet(service, SPREADSHEET_ID, sheet_name)

    if headers is None:
        headers = list(rows[0].keys())

    data = [headers]
    for r in rows:
        data.append([_normalize_value(r.get(h, "")) for h in headers])

    body = {"values": data}
    try:
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!A1",
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()
        logging.info(f"[INFO] ✅ Wrote {len(rows)} rows to '{sheet_name}' in Google Sheet.")
    except HttpError as e:
        logging.error(f"[ERROR] Failed writing to sheet {sheet_name}: {e}")
