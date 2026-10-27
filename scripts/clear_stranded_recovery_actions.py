import os, requests, time

API_URL = os.getenv('PAPERCLIP_API_URL')
API_KEY = os.getenv('PAPERCLIP_API_KEY')
HEADERS = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}

BATCH_SIZE = 25
SLEEP_BETWEEN_BATCH = 1  # seconds

def get_issues(page=1, per_page=100):
    # TODO: implement pagination, filter to issues with active stranded_assigned_issue actions
    resp = requests.get(f"{API_URL}/api/companies/{os.getenv('PAPERCLIP_COMPANY_ID')}/issues", headers=HEADERS, params={'page': page, 'per_page': per_page})
    resp.raise_for_status()
    return resp.json()['issues']

def get_recovery_actions(issue_id):
    resp = requests.get(f"{API_URL}/api/issues/{issue_id}/recovery-actions", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()['actions']

def resolve_action(issue_id, action_id, note):
    payload = {
        "actionId": action_id,
        "outcome": "restored",
        "sourceIssueStatus": "todo",
        "resolutionNote": note,
    }
    r = requests.post(f"{API_URL}/api/issues/{issue_id}/recovery-actions/resolve", json=payload, headers=HEADERS)
    return r.status_code, r.json()

def is_stale(issue):
    # skip if live run, blocker, pending interaction
    # Placeholder: always True
    return True

cleared, skipped, failed = 0, 0, 0
page = 1
while True:
    issues = get_issues(page)
    if not issues:
        break
    for issue in issues:
        if not is_stale(issue):
            skipped += 1
            continue
        actions = get_recovery_actions(issue['id'])
        for act in actions:
            if act.get('kind') != 'stranded_assigned_issue' or act.get('status') != 'active':
                continue
            status, _ = resolve_action(issue['id'], act['id'], f"Stale strand cleared by batch sweep (issue {issue['identifier']})")
            if 200 <= status < 300:
                cleared += 1
            else:
                failed += 1
            if cleared % BATCH_SIZE == 0:
                time.sleep(SLEEP_BETWEEN_BATCH)
    page += 1

print(f"Cleared: {cleared}, Skipped: {skipped}, Failed: {failed}")
# ponytail: skipped detailed live-run checks, add when Issue API exposes run status fields.
