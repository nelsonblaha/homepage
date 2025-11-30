# CI Run Times - Homepage Project

**Last Updated:** 2025-11-30

This file tracks typical CI run durations for the homepage project to help Claude determine appropriate wait times before checking CI status.

## Typical Run Times

### Full Pipeline (Tests + Deploy)
- **Average:** ~2m 30s - 3m 30s
- **Range:** 2m 27s - 4m 51s
- **Jobs:** pytest, cypress-unit, cypress-e2e, deploy

### Quick Runs (Deploy Only)
- **Average:** ~2m 30s
- **Example:** Trigger deploy (147s / 2m 27s)

## Job Breakdown

Individual job times (approximate):
- **pytest (unit tests):** ~30-45s
- **cypress-unit:** ~1m - 1m 30s
- **cypress-e2e:** ~1m 30s - 2m
- **deploy:** ~30-45s

## Recommended Sleep Times

When waiting for CI after a push:
- First check: `sleep 30` (wait 30s to let jobs start)
- Subsequent checks: `sleep 60-90` (check every 1-1.5 minutes)
- Full pipeline expected completion: ~3 minutes after push

## Notes

- Times based on self-hosted GitHub runners on NELNET
- Runners are on the same machine, so times are consistent
- Deploy step only runs after all tests pass
- E2E tests can vary based on container startup times

## Update History

- 2025-11-30: Initial file created based on recent CI runs
