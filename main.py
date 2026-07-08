import os
import importlib
import logging

from dotenv import load_dotenv

from utils.gcp_auth import get_credentials
from utils.gcp_projects import get_all_active_projects
from utils.logger_setup import setup_logger


EXECUTION_ORDER = [
    "inventory",
    "recommendation",
    "pricing",
]


def parse_env_list(value):
    """Convert comma-separated env variable into a set."""
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def run_all_modules(base_folder, credentials, org_id, projects):
    """
    Folder structure:

    module/
        compute_engine/
            inventory.py
            recommendation.py
            pricing.py

        cloud_tasks/
            inventory.py
            recommendation.py

        cloud_sql/
            inventory.py
    """

    selected_modules = parse_env_list(os.getenv("MODULES"))
    selected_components = parse_env_list(os.getenv("COMPONENTS"))

    if selected_modules:
        logging.info(f"Selected modules: {sorted(selected_modules)}")
    else:
        logging.info("Running all modules")

    if selected_components:
        logging.info(f"Selected components: {sorted(selected_components)}")
    else:
        logging.info("Running all components")

    for service in sorted(os.listdir(base_folder)):
        service_path = os.path.join(base_folder, service)

        if not os.path.isdir(service_path):
            continue

        if selected_modules and service not in selected_modules:
            logging.info(f"Skipping module: {service}")
            continue

        logging.info("=" * 80)
        logging.info(f"Processing module: {service}")
        logging.info("=" * 80)

        for component in EXECUTION_ORDER:

            if selected_components and component not in selected_components:
                continue

            script_path = os.path.join(service_path, f"{component}.py")

            if not os.path.exists(script_path):
                continue

            module_name = script_path.replace(os.sep, ".").replace(".py", "")

            try:
                logging.info(f"▶ Running {module_name}")

                module = importlib.import_module(module_name)

                if not hasattr(module, "main"):
                    logging.warning(f"{module_name} does not define main(). Skipping.")
                    continue

                try:
                    module.main(credentials, org_id, projects)
                except TypeError:
                    try:
                        module.main(credentials, org_id)
                    except TypeError:
                        module.main(credentials)

                logging.info(f"✔ Completed {module_name}")

            except Exception:
                logging.exception(f"Failed to execute {module_name}")


def main():
    setup_logger()
    load_dotenv()

    logging.info("Starting CloudKeeper GCP WAR")

    credentials = get_credentials()

    org_id = os.getenv("ORGANIZATION_ID")
    run_mode = os.getenv("RUN_MODE", "org").lower()

    if run_mode != "org":
        logging.error("Currently only 'org' mode is supported.")
        return

    projects = get_all_active_projects(credentials, org_id)

    run_all_modules(
        base_folder="module",
        credentials=credentials,
        org_id=org_id,
        projects=projects,
    )

    logging.info("WAR execution completed successfully.")


if __name__ == "__main__":
    main()