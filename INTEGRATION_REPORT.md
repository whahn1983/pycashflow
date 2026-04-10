# Integration Report

## Issues Found
- Mobile surface lacked mutation APIs for schedules, scenarios, holds/skips, and balances.
- API auth lacked 2FA continuation and token refresh capabilities.
- List pagination contract existed in docs but was not wired in handlers.
- Dashboard had mixed risk typing and no explicit deprecation path.
- No iOS app scaffold existed in-repo.

## Fixes Applied
- Added auth expansion endpoints: `/auth/login/2fa`, `/auth/refresh`, `/auth/password`.
- Added backend CRUD/mutation APIs for schedules, scenarios, holds, skips, and balance updates/history.
- Added settings and AI insight endpoints: `/settings`, `/insights`, `/insights/refresh`.
- Wired optional `limit` / `offset` parsing for list endpoints and included `meta.limit`/`meta.offset`.
- Added `risk_v2` payload on dashboard while retaining legacy `risk` with deprecation flag.
- Added guest write protection (`403`) across mutation endpoints.
- Added SwiftUI app scaffold under `/ios-app` with API client, session manager, models, and feature views.

## Remaining Risks
- iOS scaffold is functional but minimal; additional UI/UX polish and feature-complete view models are still needed.
- 2FA challenge is signed/TTL-based and stateless; if strict server-side revocation tracking is needed, add persistent challenge storage.
- SQLAlchemy `Query.get()` deprecation warnings still exist outside this change set.
