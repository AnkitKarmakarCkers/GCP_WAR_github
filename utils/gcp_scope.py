import logging

from google.cloud import resourcemanager_v3


def _list_projects(parent, credentials):
    """
    Returns ACTIVE projects directly under a parent.
    Parent can be:
        organizations/<id>
        folders/<id>
    """

    client = resourcemanager_v3.ProjectsClient(
        credentials=credentials
    )

    request = resourcemanager_v3.ListProjectsRequest(
        parent=parent
    )

    projects = []

    for project in client.list_projects(request=request):

        if project.state.name != "ACTIVE":
            continue

        projects.append(
            {
                "project_id": project.project_id,
                "project_number": project.name.split("/")[-1],
            }
        )

    return projects


def _list_child_folders(folder_id, credentials):
    """
    Returns child folders of a folder.
    """

    client = resourcemanager_v3.FoldersClient(
        credentials=credentials
    )

    request = resourcemanager_v3.ListFoldersRequest(
        parent=f"folders/{folder_id}"
    )

    return list(client.list_folders(request=request))


def _collect_folder_projects(folder_id, credentials):
    """
    Recursively collects projects from a folder and all descendants.
    """

    projects = []

    projects.extend(
        _list_projects(
            f"folders/{folder_id}",
            credentials,
        )
    )

    child_folders = _list_child_folders(
        folder_id,
        credentials,
    )

    for folder in child_folders:

        child_id = folder.name.split("/")[-1]

        projects.extend(
            _collect_folder_projects(
                child_id,
                credentials,
            )
        )

    return projects


def get_projects_by_scope(
    credentials,
    run_mode,
    organization_id=None,
    folder_ids=None,
    project_ids=None,
):
    """
    Returns project list according to execution scope.
    """

    run_mode = run_mode.lower()

    if run_mode == "org":

        if not organization_id:
            raise ValueError(
                "ORGANIZATION_ID is required."
            )

        projects = _list_projects(
            f"organizations/{organization_id}",
            credentials,
        )

    
    elif run_mode == "folder":

        if not folder_ids:
            raise ValueError(
                "FOLDER_IDS cannot be empty when RUN_MODE=folder."
            )

        projects = []

        for folder_id in folder_ids:
            projects.extend(
                _collect_folder_projects(
                    folder_id,
                    credentials,
                )
            )

        # Remove duplicates in case folders overlap
        unique = {}

        for project in projects:
            unique[project["project_id"]] = project

        projects = list(unique.values())

    elif run_mode == "projects":

        if not project_ids:
            raise ValueError(
                "PROJECT_IDS cannot be empty."
            )

        projects = [
            {
                "project_id": p.strip(),
                "project_number": None,
            }
            for p in project_ids
            if p.strip()
        ]

    else:

        raise ValueError(
            "RUN_MODE must be org, folder or projects."
        )

    logging.info(
        f"Found {len(projects)} project(s)."
    )

    return projects