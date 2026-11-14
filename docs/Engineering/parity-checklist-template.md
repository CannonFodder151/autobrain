# Mobile/Web parity checklist (AUT-137)

Add this checklist to every feature issue. A feature is not done until every
box is checked.

## Web (CannonFodder151/autobrain)

- [ ] Web feature merged to `main` (PR link)
- [ ] CHANGELOG entry added under `[Unreleased]`
- [ ] `dockerhub-publish.yml` image published

## Mobile (CannonFodder151/autobrain-mobile)

- [ ] `sync-mobile.yml` run mirrored lineage (run link)
- [ ] `flutter analyze` clean
- [ ] Mobile release promoted to demo
- [ ] Mobile release promoted to Default
- [ ] Mobile release promoted to hosted

## Sync

- [ ] Mobile version matches server `APP_VERSION`
- [ ] Discord notification posted at each stage
