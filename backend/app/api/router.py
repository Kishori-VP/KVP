from fastapi import APIRouter

from app.api.routes import (
    audit_logs,
    auth,
    cases,
    config,
    contacts,
    dashboard,
    delivery,
    events,
    field,
    girls,
    health,
    master,
    media,
    notifications,
    report_templates,
    reports,
    targets,
    users,
    volunteers,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(volunteers.router)
api_router.include_router(master.router)
api_router.include_router(contacts.router)
api_router.include_router(girls.router)
api_router.include_router(cases.router)
api_router.include_router(field.router)
api_router.include_router(events.router)
api_router.include_router(media.router)
api_router.include_router(targets.router)
api_router.include_router(dashboard.router)
api_router.include_router(report_templates.router)  # before reports: /reports/{report_type} is a catch-all
api_router.include_router(reports.router)
api_router.include_router(notifications.router)
api_router.include_router(delivery.router)
api_router.include_router(config.router)
api_router.include_router(audit_logs.router)
