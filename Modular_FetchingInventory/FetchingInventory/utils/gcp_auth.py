import os
from google.auth import impersonated_credentials
from google.oauth2 import service_account

def get_credentials():
    source_sa_file = os.getenv("SOURCE_SA_FILE")
    target_sa = os.getenv("TARGET_SERVICE_ACCOUNT")
    if not source_sa_file or not target_sa:
        raise ValueError("Missing service account details in .env")
    base_creds = service_account.Credentials.from_service_account_file(
        source_sa_file,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    target_creds = impersonated_credentials.Credentials(
        source_credentials=base_creds,
        target_principal=target_sa,
        target_scopes=["https://www.googleapis.com/auth/cloud-platform" ,"https://www.googleapis.com/auth/spreadsheets"],
        lifetime=3600
    )
    return target_creds
