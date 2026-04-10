# PyCashFlow iOS App

SwiftUI client for PyCashFlow backed by `/api/v1` endpoints.

## Architecture
- `Core/Networking`: `APIClient`, endpoint construction, envelope decoding.
- `Core/Auth`: session/token state and persistence.
- `Core/Models`: DTOs aligned to backend response shapes.
- `Features/*`: screen-level view models and views.

The app uses real backend APIs only; no mock-only business flows are implemented.
