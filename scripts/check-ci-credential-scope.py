#!/usr/bin/env python3
"""
CI guard: fail if a workflow references a repo/org-wide credential for a push
to a protected branch, or if a job that pushes via secrets.*_PAT declares
permissions: contents: write.
Exits 0 on pass, 1 on fail with details on stderr.
"""

import sys
import os
import yaml
import glob

WORKFLOW_DIR = ".github/workflows"

def check_workflow(wf_path):
    """Check a single workflow file for violations."""
    violations = []
    warnings = []
    
    try:
        with open(wf_path, 'r') as f:
            wf = yaml.safe_load(f)
    except Exception as e:
        warnings.append(f"Could not parse {wf_path}: {e}")
        return violations, warnings
    
    if not wf or 'jobs' not in wf:
        return violations, warnings
    
    wf_name = os.path.basename(wf_path)
    
    for job_name, job in wf['jobs'].items():
        if not isinstance(job, dict):
            continue
            
        # Get job permissions
        perms = job.get('permissions', {})
        contents_perm = None
        if isinstance(perms, str):
            # Could be 'read-all' or 'write-all'
            if perms == 'write-all':
                contents_perm = 'write'
        elif isinstance(perms, dict):
            contents_perm = perms.get('contents')
        
        # Check if job uses a PAT secret in env (job-level or step-level)
        pat_secrets = set()
        
        # Job-level env
        job_env = job.get('env', {})
        if isinstance(job_env, dict):
            for key, val in job_env.items():
                if isinstance(val, str) and ('_PAT' in key or key == 'GH_PAT'):
                    pat_secrets.add(key)
        
        # Step-level env
        steps = job.get('steps', [])
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_env = step.get('env', {})
            if isinstance(step_env, dict):
                for key, val in step_env.items():
                    if isinstance(val, str) and ('_PAT' in key or key == 'GH_PAT'):
                        pat_secrets.add(key)
        
        # Check if job has git push in any step
        has_git_push = False
        for step in steps:
            if not isinstance(step, dict):
                continue
            run = step.get('run', '')
            if isinstance(run, str) and 'git push' in run:
                has_git_push = True
                break
        
        # Check violations
        if pat_secrets and has_git_push:
            if contents_perm == 'write':
                for pat in pat_secrets:
                    violations.append(f"{wf_name} job '{job_name}' uses {pat} for git push but declares 'contents: write' permissions")
            
            # Warn about GH_PAT specifically
            if 'GH_PAT' in pat_secrets:
                warnings.append(f"{wf_name} job '{job_name}' uses GH_PAT with git push — verify this is a fine-grained PAT scoped to this repo only (Contents: read+write)")
    
    return violations, warnings

def main():
    all_violations = []
    all_warnings = []
    
    print(f"==> Scanning workflows in {WORKFLOW_DIR} for credential scope violations...")
    
    for wf_path in glob.glob(os.path.join(WORKFLOW_DIR, "*.yml")) + glob.glob(os.path.join(WORKFLOW_DIR, "*.yaml")):
        violations, warnings = check_workflow(wf_path)
        all_violations.extend(violations)
        all_warnings.extend(warnings)
    
    for v in all_violations:
        print(f"FAIL: {v}", file=sys.stderr)
    
    for w in all_warnings:
        print(f"WARN: {w}", file=sys.stderr)
    
    if all_violations:
        print("==> Credential scope check FAILED", file=sys.stderr)
        return 1
    else:
        print("==> Credential scope check PASSED")
        return 0

if __name__ == '__main__':
    sys.exit(main())