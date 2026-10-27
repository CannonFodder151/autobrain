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
    # AUT-5567: on 504 (proxy gave up), retry once after 5s; on second 504 return [].
    for attempt in (1, 2):
        try:
            r = requests.get(f"{API_URL}/api/companies/{COMPANY_ID}/issues", headers=HEADERS, params=params or {}, timeout=90)
            if r.status_code == 504:
                if attempt == 1:
                    time.sleep(5); continue
                return []
            r.raise_for_status()
            data = r.json()
            return data.get('issues', data) if isinstance(data, dict) else data
        except requests.exceptions.RequestException:
            if attempt == 1:
                time.sleep(5); continue
            return []
    return []

def get_issue(iid):
    for attempt in (1, 2):
        try:
            r = requests.get(f"{API_URL}/api/issues/{iid}", headers=HEADERS, timeout=90)
            if r.status_code == 504:
                if attempt == 1:
                    time.sleep(5); continue
                return None
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException:
            if attempt == 1:
                time.sleep(5); continue
            return None
    return None

def patch_issue(iid, payload):
    # AUT-5567: on 504, verify by GET first; retry once only if change absent; stop after double 504.
    for attempt in (1, 2):
        try:
            r = requests.patch(f"{API_URL}/api/issues/{iid}", headers=HEADERS, json=payload, timeout=90)
            if r.status_code == 504:
                # verify whether it committed
                cur = get_issue(iid)
                if cur is not None and all(cur.get(k) == v for k, v in payload.items()):
                    return 200, 'committed-after-504'
                if attempt == 1:
                    time.sleep(5); continue
                return 504, 'double-504-stop'
            r.raise_for_status()
            return r.status_code, r.text
        except requests.exceptions.RequestException:
            if attempt == 1:
                time.sleep(5); continue
            return 504, 'exception'
    return 504, 'exhausted'

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
