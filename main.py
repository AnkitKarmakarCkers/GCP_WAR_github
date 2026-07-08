import os
import importlib
import logging
from dotenv import load_dotenv
from utils.gcp_auth import get_credentials
from utils.gcp_projects import get_all_active_projects
from utils.logger_setup import setup_logger

def run_all_scripts(folder, credentials, org_id, projects):
    py_files = [f for f in os.listdir(folder) if f.endswith('.py') and not f.startswith('__')]
    for file in py_files:
        module_name = f"{folder.replace('/', '.')}.{file[:-3]}"
        try:
            logging.info(f"▶ Running {module_name} ...")
            module = importlib.import_module(module_name)
            if hasattr(module, 'main'):
                try:
                    module.main(credentials, org_id, projects)
                except TypeError:
                    try:
                        module.main(credentials, org_id)
                    except TypeError:
                        module.main(credentials)
            else:
                logging.warning(f"⚠️ Skipping {file} — no main() found.")
        except Exception as e:
            logging.error(f"❌ Error in {file}: {e}")

def main():
    setup_logger()
    load_dotenv()
    logging.info("🚀 Starting CloudKeeper GCP Inventory Fetch")
    credentials = get_credentials()
    org_id = os.getenv("ORGANIZATION_ID")
    run_mode = os.getenv("RUN_MODE", "org").lower()
    if run_mode == "org":
        projects = get_all_active_projects(credentials, org_id)
        run_all_scripts("modules", credentials, org_id, projects)
    else:
        logging.error("Currently only 'org' mode is supported.")

if __name__ == "__main__":
    main()
