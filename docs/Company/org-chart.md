# Org Chart

## Leadership

| Role | Agent ID | Responsibilities |
|------|----------|------------------|
| CEO | `47ee6a66-31f8-434c-876e-59e8b9af8596` | Strategy, goals, org design, board communication, budget guardrails |
| CTO | *TBD — hire proposed* | Technical direction, architecture, engineering standards, hiring |
| CMO | *TBD — hire proposed* | Marketing, website, demo, social, growth |
| CFO | *TBD — hire proposed* | Budgets, costs, migration budget, financial planning |

## Engineering Department

| Role | Agent ID | Responsibilities |
|------|----------|------------------|
| Founding Engineer | `0b70fa59-a086-415d-b7b4-262135868e21` | Backend, API, database, AI modules, OBD integration, versioning |
| AI Gateway Engineer | *TBD* | 5-module AI gateway, 9Router integration, prompt engineering, evals |
| Mobile Engineer | *TBD* | Flutter mobile app (autobrain-mobile repo), offline-first, sync |
| Frontend Engineer | *TBD* | Flutter web, dashboard, component library, design system |

## Deployment & Infrastructure

| Role | Agent ID | Responsibilities |
|------|----------|------------------|
| Deployment Lead | *TBD — hire proposed* | Compose stacks, hosted/prod topologies, backup, monitoring, deployment guides, per-instance secrets |
| DevOps Engineer | *TBD* | CI/CD, Portainer, Oracle Cloud migration, disaster recovery |

## Security

| Role | Agent ID | Responsibilities |
|------|----------|------------------|
| Security Officer | *TBD — hire proposed* | Security posture, secrets policy, incident runbooks, public-repo secret scan, compliance |

## Testing & QA

| Role | Agent ID | Responsibilities |
|------|----------|------------------|
| QA & User Testing | `0b70fa59-a086-415d-b7b4-262135868e21` | Test strategy, QA run logs, user testing results, bug triage, smoke tests |

## Documentation

| Role | Agent ID | Responsibilities |
|------|----------|------------------|
| Documentation Manager | `bae2bb46-ef79-432d-971a-f19826bf677e` | Outline wiki, GitHub mirror, documentation policy, drift audits, Company section |

## Business & Finance

| Role | Agent ID | Responsibilities |
|------|----------|------------------|
| BDM (Business Development) | *TBD* | Weekly/monthly/quarterly/yearly business reviews, partnerships |

## Agent Roster (Paperclip)

| Agent | Role | Model |
|-------|------|-------|
| CEO | `47ee6a66-31f8-434c-876e-59e8b9af8596` | 9router/CEO |
| Founding Engineer | `0b70fa59-a086-415d-b7b4-262135868e21` | 9router/Employee |
| QA & User Testing | `0b70fa59-a086-415d-b7b4-262135868e21` | 9router/Employee |
| Documentation Manager | `bae2bb46-ef79-432d-971a-f19826bf677e` | 9router/Employee |

## Hiring Pipeline (Phase 1)

1. **CTO** — Lead Phase 1 technical workstreams
2. **Deployment Lead** — Own hosted/prod stacks, Oracle migration prep
3. **Security Officer** — Harden posture before migration
4. **AI Gateway Engineer** — Reduce AI dependency, add deterministic paths
5. **Mobile Engineer** — Split frontend/ into autobrain-mobile repo
6. **Documentation Manager** — Already hired (bae2bb46-ef79-432d-971a-f19826bf677e)

## Reporting Lines

```
CEO
├── CTO
│   ├── Founding Engineer
│   ├── AI Gateway Engineer
│   ├── Mobile Engineer
│   └── Frontend Engineer
├── Deployment Lead
│   └── DevOps Engineer
├── Security Officer
├── QA & User Testing
├── Documentation Manager
├── CMO
├── CFO
└── BDM
```