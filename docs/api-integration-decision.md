# API integration decisions

STATUS: rationale locked in; implementation details to be added during Task 4.

| API | Purpose | Why chosen | Fallback if unavailable |
|---|---|---|---|
| Climatiq | Live carbon-emission factors | Named explicitly in the brief; free tier (~500 calls/month) | Stored emission factors in NeonDB |
| OpenRouteService | Road-routed distance (train/coach/car) | Named explicitly in the brief; free tier (2,000 req/day) | Haversine (great-circle) distance |
| OpenCage | Reverse geocoding / GPS label | Named explicitly in the brief; free tier (2,500 req/day) | Nearest-supported-city match without a friendly label |
| Aviationstack | Sample flight number/airline | Amadeus for Developers sandbox is being decommissioned (2026-07-17); Aviationstack has a working free tier and covers the one thing we need (a sample flight) | Transport card omits the live-flight line |
| NeonDB | Primary structured data store | Chosen over local JSON: online storage rather than local files, generous free tier (0.5 GB storage, 100 CU-hours/month, scale-to-zero, no card required) | None — this is the primary store; see docs/deployment.md for what happens if it's briefly unreachable |

## Notes

- All four external APIs are optional at the code level — every custom action
  degrades gracefully (timeout/error/missing key -> stored value / no live
  line), matching the brief's "error-handling for failed API responses"
  requirement.
- Unlike the reference implementation we reviewed (which used NeonDB as a
  fallback tier behind local JSON), we're using NeonDB as the sole primary
  store — a deliberate scope decision given more available time and a
  preference for online rather than local data.
