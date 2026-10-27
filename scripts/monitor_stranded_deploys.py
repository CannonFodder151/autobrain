import os, requests, time, sys, json
from datetime import datetime, timezone

API_URL = os.getenv('PAPERCLIP_API_URL', 'https://paperclip.nathanmartina.com')
API_KEY = os.getenv('PAPERCLIP_API_KEY')
COMPANY_ID = os.getenv('PAPERCLIP_COMPANY_ID', '41d8aeaf-0e55-4127-b037-7a6d740be3b6')
HEADERS = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
DISCORD_REPORTER = 'https://n8n.nathanmartina.com/webhook/discord-report'
DEPLOY_LEAD = '285b6a03-80f7-4a36-ba06-d5831371afce'
THIS_ROUTINE_ID = '3d63350d-374b-454e-a6d2-dfe6caeafb22'
IDLE_THRESHOLD = 2 * 3600
PARENT_CANCEL_THRESHOLD = 1 * 3600

def now():
    return datetime.now(timezone.utc)

def parse(s):
    if not s: return None
    return datetime.fromisoformat(s.replace('Z','+00:00'))

def get_issues(params=None):
    r = requests.get(f"{API_URL}/api/companies/{COMPANY_ID}/issues", headers=HEADERS, params=params or {})
    r.raise_for_status()
    data = r.json()
    return data.get('issues', data) if isinstance(data, dict) else data

def get_issue(iid):
    r = requests.get(f"{API_URL}/api/issues/{iid}", headers=HEADERS)
    r.raise_for_status()
    return r.json()

def patch_issue(iid, payload):
    r = requests.patch(f"{API_URL}/api/issues/{iid}", headers=HEADERS, json=payload, timeout=90)
    return r.status_code, r.text

def discord(channel, title, description, color='0xED4245', fields=None):
    payload = {'channel': channel, 'title': title, 'description': description, 'color': color, 'author': 'CEO', 'fields': fields or []}
    try:
        requests.post(DISCORD_REPORTER, json=payload, timeout=15)
    except Exception as e:
        print('discord post failed:', e)

def main():
    alert = '--alert' in sys.argv
    issues = get_issues({'status': 'in_progress'})
    stranded = []
    orphans = []
    stale_routine = []
    foreign_routine = []
    for i in issues:
        updated = parse(i.get('updatedAt') or i.get('startedAt'))
        idle = (now() - updated).total_seconds() if updated else 0
        assignee = i.get('assigneeAgentId')
        # RULE A
        if i.get('status') == 'in_progress' and assignee == DEPLOY_LEAD and idle > IDLE_THRESHOLD:
            stranded.append(i)
        # RULE C
        if i.get('originKind') == 'routine_execution' and i.get('status') == 'in_progress' and idle > IDLE_THRESHOLD:
            if i.get('originId') == THIS_ROUTINE_ID:
                stale_routine.append(i)
            else:
                foreign_routine.append(i)
    # RULE B: children of cancelled parents
    cancelled_parents = get_issues({'status': 'cancelled'})
    for p in cancelled_parents:
        cancelled_at = parse(p.get('cancelledAt'))
        if not cancelled_at or (now() - cancelled_at).total_seconds() < PARENT_CANCEL_THRESHOLD:
            continue
        # find children
        children = get_issues({'parentId': p['id']})
        for c in children:
            if c.get('status') in ('done','cancelled','closed'):
                continue
            if p.get('originKind') == 'routine_execution':
                orphans.append((p, c))
            else:
                # manually cancelled parent -> report only
                orphans.append(('manual', p, c))
    # Execute
    if stranded and alert:
        discord('incidents', 'Stranded deploy children', f"{len(stranded)} deploy child issue(s) idle >2h assigned to Deployment Lead.", fields=[{'name': i['identifier'], 'value': i['title'][:80], 'inline': False} for i in stranded[:4]])
    for i in stale_routine:
        sc, _ = patch_issue(i['id'], {'status': 'cancelled'})
        print(f"RULE C cancel {i['identifier']}: {sc}")
    for item in orphans:
        if item[0] == 'manual':
            _, p, c = item
            if alert:
                discord('incidents', 'Orphan child (manual parent cancel)', f"Parent {p['identifier']} manually cancelled; child {c['identifier']} non-terminal. Not auto-cancelled.", color='0xE67E22')
        else:
            p, c = item
            sc, _ = patch_issue(c['id'], {'status': 'cancelled'})
            print(f"RULE B cancel {c['identifier']}: {sc}")
    if foreign_routine and alert:
        discord('incidents', 'Foreign stale routine executions', f"{len(foreign_routine)} foreign routine execution(s) idle >2h (not cancelled).", color='0xE67E22')
    print(json.dumps({'stranded': len(stranded), 'orphans': len(orphans), 'stale_routine': len(stale_routine), 'foreign_routine': len(foreign_routine)}, indent=2))

if __name__ == '__main__':
    main()
