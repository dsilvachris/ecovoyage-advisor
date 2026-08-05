"""
admin_api.py — backend for the admin console (served at /admin behind the
same nginx instance as the chatbot, HTTP Basic Auth enforced at the nginx
layer via deploy/nginx.conf).

STATUS: scaffold only. Not part of the assignment brief's minimum
requirements — a bonus feature layered on top of the same NeonDB tables the
chatbot reads from.

Planned endpoints:
- GET  /admin/api/trips              — list trip sessions
- GET  /admin/api/handovers          — list handover requests (pending/resolved)
- PATCH /admin/api/handovers/<id>    — mark a handover resolved
- CRUD /admin/api/hotels             — manage eco-hotel records
- CRUD /admin/api/experiences        — manage experience records
- CRUD /admin/api/offsets            — manage carbon-offset records
"""
