from google.cloud import resourcemanager_v3
import logging

def get_all_active_projects(credentials, org_id):
    client = resourcemanager_v3.ProjectsClient(credentials=credentials)
    request = resourcemanager_v3.ListProjectsRequest(parent=f"organizations/{org_id}")
    projects = []
    for p in client.list_projects(request=request):
        if p.state.name == "ACTIVE":
            projects.append({"project_id": p.project_id, "project_number": p.name.split("/")[-1]})
    logging.info(f"[INFO] Found {len(projects)} active projects.")
    return projects
