#!/usr/bin/env python3
"""
Auto-triage pipeline: CI fail/deploy fail/store rejection -> issue + logs + owner + wake + postmortem template.
Tracks MTTR/lead time. Can be triggered via GitHub webhook or scheduled polling.
"""

import os
import sys
import json
import time
import subprocess
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import requests

REPO = "CannonFodder151/autobrain"
MOBILE_REPO = "CannonFodder151/autobrain-mobile"
PAPERCLIP_API = "https://paperclip2.nathanmartina.com/api"
PAPERCLIP_API_KEY = os.getenv("PAPERCLIP_API_KEY")
GH_TOKEN = os.getenv("GH_PAT") or os.getenv("GH_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {PAPERCLIP_API_KEY}",
    "Content-Type": "application/json"
}
GH_HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github+json"
}

MTTR_FILE = Path(__file__).parent.parent / ".github" / "mttr-tracking.json"
POSTMORTEM_TEMPLATE = Path(__file__).parent.parent / "docs" / "Engineering" / "postmortem-template.md"


def gh_api(path: str, params: dict = None) -> dict:
    """Call GitHub API."""
    url = f"https://api.github.com{path}"
    r = requests.get(url, headers=GH_HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def gh_api_paginated(path: str, params: dict = None, max_pages: int = 10) -> list:
    """Call paginated GitHub API."""
    results = []
    for page in range(1, max_pages + 1):
        p = params.copy() if params else {}
        p["page"] = page
        p["per_page"] = 100
        data = gh_api(path, p)
        if not data:
            break
        results.extend(data)
        if len(data) < 100:
            break
    return results


def get_failed_workflow_runs(repo: str, since: datetime) -> list:
    """Get failed workflow runs since a given time."""
    runs = gh_api_paginated(
        f"/repos/{repo}/actions/runs",
        {
            "status": "completed",
            "conclusion": "failure",
            "created": f">{since.isoformat()}",
        }
    )
    return runs


def get_run_logs(repo: str, run_id: int) -> str:
    """Get logs for a failed run."""
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs"
    r = requests.get(url, headers=GH_HEADERS, timeout=60)
    if r.status_code == 200:
        return r.text[:50000]  # Truncate to 50KB
    return f"Failed to fetch logs: {r.status_code}"


def get_run_jobs(repo: str, run_id: int) -> list:
    """Get jobs for a run."""
    return gh_api_paginated(f"/repos/{repo}/actions/runs/{run_id}/jobs")


def determine_owner(repo: str, run: dict, jobs: list) -> tuple:
    """Determine the owner agent based on workflow name and failed jobs."""
    workflow_name = run.get("name", "").lower()
    
    # Map workflow names to agents
    if "backend" in workflow_name or "pytest" in workflow_name:
        return "d98f790f-a1f8-4cd6-b69c-f174f1df6df0", "Backend Engineer"
    elif "frontend" in workflow_name or "flutter" in workflow_name:
        return "cb213090-e7da-42b8-8e6c-98b1cc958296", "Frontend Engineer"
    elif "mobile" in workflow_name or "android" in workflow_name or "ios" in workflow_name:
        return "94fa93b9-0f26-44a2-bd87-4595acbed593", "Mobile Release Engineer"
    elif "deploy" in workflow_name or "upgrade" in workflow_name or "sync" in workflow_name:
        return "ed65484d-9f28-44f7-93e9-564d52d8536a", "Platform Engineer"
    elif "security" in workflow_name:
        return "8724e44a-dbe4-4c8b-88a0-cc869ec5d245", "Security Officer"
    elif "code-review" in workflow_name:
        return "96ffe367-8c47-47ac-9283-f12d36a7a2ba", "Code Reviewer"
    elif "docker" in workflow_name or "build" in workflow_name or "publish" in workflow_name:
        return "6764b91c-3ed1-4a04-89b1-0395f72dd31a", "DevOps Engineer"
    elif "release" in workflow_name and repo == MOBILE_REPO:
        return "94fa93b9-0f26-44a2-bd87-4595acbed593", "Mobile Release Engineer"
    else:
        return "6764b91c-3ed1-4a04-89b1-0395f72dd31a", "DevOps Engineer"


def load_mttr_data() -> dict:
    """Load MTTR tracking data."""
    if MTTR_FILE.exists():
        with open(MTTR_FILE) as f:
            return json.load(f)
    return {"incidents": [], "summary": {}}


def save_mttr_data(data: dict):
    """Save MTTR tracking data."""
    MTTR_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MTTR_FILE, "w") as f:
        json.dump(data, f, indent=2)


def record_incident(repo: str, run: dict, issue_id: str, owner_agent: str, detected_at: datetime):
    """Record incident for MTTR tracking."""
    data = load_mttr_data()
    incident = {
        "repo": repo,
        "run_id": run["id"],
        "workflow": run.get("name"),
        "conclusion": run.get("conclusion"),
        "created_at": run.get("created_at"),
        "detected_at": detected_at.isoformat(),
        "issue_id": issue_id,
        "owner_agent": owner_agent,
        "resolved_at": None,
        "mttr_minutes": None,
        "lead_time_minutes": None,
    }
    data["incidents"].append(incident)
    save_mttr_data(data)


def create_paperclip_issue(title: str, description: str, assignee: str, labels: list = None) -> dict:
    """Create a Paperclip issue."""
    payload = {
        "title": title,
        "description": description,
        "assigneeAgentId": assignee,
        "priority": "high",
        "status": "todo",
    }
    if labels:
        payload["labels"] = labels
    
    r = requests.post(
        f"{PAPERCLIP_API}/companies/df33b840-b692-45ba-9a95-62d2341c95e6/issues",
        headers=HEADERS,
        json=payload,
        timeout=30
    )
    r.raise_for_status()
    return r.json()


def get_postmortem_template() -> str:
    """Get postmortem template content."""
    if POSTMORTEM_TEMPLATE.exists():
        with open(POSTMORTEM_TEMPLATE) as f:
            return f.read()
    return """# Postmortem Template

## Incident Summary
- **What happened**: 
- **Impact**: 
- **Duration**: 
- **Severity**: 

## Timeline
- **Detected**: 
- **Investigated**: 
- **Mitigated**: 
- **Resolved**: 

## Root Cause
- **Primary cause**: 
- **Contributing factors**: 

## Resolution
- **What was done**: 
- **Why it worked**: 

## Action Items
- [ ] Prevent recurrence
- [ ] Improve detection
- [ ] Update runbooks

## Lessons Learned
"""


def process_failure(repo: str, run: dict, detected_at: datetime) -> Optional[str]:
    """Process a single failed workflow run."""
    run_id = run["id"]
    workflow_name = run.get("name", "Unknown")
    run_url = f"https://github.com/{repo}/actions/runs/{run_id}"
    
    # Get logs
    logs = get_run_logs(repo, run_id)
    jobs = get_run_jobs(repo, run_id)
    
    # Determine owner
    owner_agent_id, owner_name = determine_owner(repo, run, jobs)
    
    # Build description
    desc = f"""**Failed Workflow**: {workflow_name}
**Repository**: {repo}
**Run**: #{run_id} ([link]({run_url}))
**Branch**: {run.get('head_branch', 'unknown')}
**Commit**: {run.get('head_sha', 'unknown')[:8]}
**Triggered by**: {run.get('actor', {}).get('login', 'unknown')}
**Failed at**: {run.get('updated_at', 'unknown')}

## Failed Jobs
"""
    for job in jobs:
        if job.get("conclusion") == "failure":
            desc += f"- **{job['name']}** ([logs]({job.get('html_url', '#')}))\n"
    
    desc += f"\n## Logs (truncated)\n```\n{logs}\n```\n\n---\n\n"
    desc += get_postmortem_template()
    
    # Create issue
    issue = create_paperclip_issue(
        title=f"CI Failure: {repo} / {workflow_name} (#{run_id})",
        description=desc,
        assignee=owner_agent_id,
        labels=["ci-failure", "auto-triage", repo.split("/")[-1]]
    )
    
    issue_id = issue.get("id")
    print(f"Created issue {issue_id} for run {run_id}, assigned to {owner_name}")
    
    # Record for MTTR
    record_incident(repo, run, issue_id, owner_agent_id, detected_at)
    
    return issue_id


def poll_mode(hours_back: int = 24):
    """Poll for failures in the last N hours across both repos."""
    since = datetime.utcnow() - timedelta(hours=hours_back)
    print(f"Polling for failures since {since.isoformat()}...")
    
    detected_at = datetime.utcnow()
    
    for repo in [REPO, MOBILE_REPO]:
        runs = get_failed_workflow_runs(repo, since)
        print(f"[{repo}] Found {len(runs)} failed runs")
        
        for run in runs:
            # Skip if already has an issue (check MTTR file)
            data = load_mttr_data()
            existing = next((i for i in data["incidents"] 
                           if i["repo"] == repo and i["run_id"] == run["id"]), None)
            if existing:
                print(f"  Run {run['id']} already tracked, skipping")
                continue
            
            try:
                process_failure(repo, run, detected_at)
            except Exception as e:
                print(f"  Error processing run {run['id']}: {e}")


def webhook_mode(payload: dict):
    """Process a webhook payload from GitHub."""
    # GitHub workflow_run webhook payload
    if "workflow_run" in payload:
        run = payload["workflow_run"]
        if run.get("conclusion") == "failure":
            repo = payload.get("repository", {}).get("full_name", REPO)
            detected_at = datetime.utcnow()
            process_failure(repo, run, detected_at)
    else:
        print("Unknown webhook payload format")


def update_mttr_on_resolution(issue_id: str):
    """Update MTTR when an issue is resolved."""
    data = load_mttr_data()
    for incident in data["incidents"]:
        if incident["issue_id"] == issue_id and incident["resolved_at"] is None:
            resolved_at = datetime.utcnow()
            incident["resolved_at"] = resolved_at.isoformat()
            detected_at = datetime.fromisoformat(incident["detected_at"])
            incident["mttr_minutes"] = (resolved_at - detected_at).total_seconds() / 60
            created_at = datetime.fromisoformat(incident["created_at"])
            incident["lead_time_minutes"] = (detected_at - created_at).total_seconds() / 60
            print(f"Updated MTTR for issue {issue_id}: {incident['mttr_minutes']:.1f} min")
    save_mttr_data(data)


def main():
    parser = argparse.ArgumentParser(description="Auto-triage pipeline")
    parser.add_argument("--poll", type=int, help="Poll for failures in last N hours")
    parser.add_argument("--webhook", action="store_true", help="Process stdin as webhook payload")
    parser.add_argument("--resolve", help="Mark issue as resolved (issue ID)")
    
    args = parser.parse_args()
    
    if args.resolve:
        update_mttr_on_resolution(args.resolve)
        return
    
    if args.webhook:
        payload = json.load(sys.stdin)
        webhook_mode(payload)
    elif args.poll:
        poll_mode(args.poll)
    else:
        poll_mode(24)


if __name__ == "__main__":
    main()
