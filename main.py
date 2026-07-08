import importlib
import logging
import os

from dotenv import load_dotenv

from utils.gcp_auth import get_credentials
from utils.gcp_scope import get_projects_by_scope
from utils.logger_setup import setup_logger


EXECUTION_ORDER = [
    "inventory",
    "recommendation",
    "pricing",
]


def parse_list(value):

    if not value:
        return set()

    return {
        item.strip()
        for item in value.split(",")
        if item.strip()
    }


def run_modules(
    credentials,
    org_id,
    projects,
):

    services = parse_list(
        os.getenv("SERVICES")
    )

    components = parse_list(
        os.getenv("COMPONENTS")
    )

    base = "module"

    for service in sorted(os.listdir(base)):

        service_path = os.path.join(
            base,
            service,
        )

        if not os.path.isdir(service_path):
            continue

        if services and service not in services:
            continue

        logging.info("=" * 80)
        logging.info(
            f"Service : {service}"
        )
        logging.info("=" * 80)

        for component in EXECUTION_ORDER:

            if (
                components
                and component not in components
            ):
                continue

            file = os.path.join(
                service_path,
                f"{component}.py",
            )

            if not os.path.exists(file):
                continue

            module_name = (
                file.replace(os.sep, ".")
                .replace(".py", "")
            )

            logging.info(
                f"Running {module_name}"
            )

            try:

                module = importlib.import_module(
                    module_name
                )

                if not hasattr(
                    module,
                    "main",
                ):
                    logging.warning(
                        f"{module_name} has no main()."
                    )
                    continue

                module.main(
                    credentials=credentials,
                    org_id=org_id,
                    projects=projects,
                )

                logging.info(
                    f"Completed {module_name}"
                )

            except Exception:

                logging.exception(
                    f"Failed : {module_name}"
                )


def main():

    setup_logger()

    load_dotenv()

    credentials = get_credentials()

    run_mode = os.getenv(
        "RUN_MODE",
        "org",
    )

    organization_id = os.getenv(
        "ORGANIZATION_ID"
    )

    folder_ids = parse_list(os.getenv("FOLDER_IDS"))

    project_ids = parse_list(
        os.getenv("PROJECT_IDS")
    )

    projects = get_projects_by_scope(
        credentials=credentials,
        run_mode=run_mode,
        organization_id=organization_id,
        folder_id=folder_ids,
        project_ids=project_ids,
    )

    run_modules(
        credentials=credentials,
        org_id=organization_id,
        projects=projects,
    )

    logging.info(
        "WAR execution completed."
    )


if __name__ == "__main__":
    main()