from django.urls import path
from core.views_ui import (
    dashboard_view,
    field_crop_list_view,
    field_crop_detail_view,
    field_list_view,
    field_detail_view,
    season_report_view,
    update_rate_view,
    my_operations_view,
    toggle_operation_status,
    create_operation,
    home_redirect,
    create_worker,
    invite_agronomist,
    my_agronomists,
    remove_agronomist,
    agronomist_dashboard,
    agronomist_owner_detail,
    agronomist_field_operations,
    toggle_finance_access,
    create_season,
)

urlpatterns = [
    # Home / redirect
    path("", home_redirect, name="home"),

    # Owner dashboard
    path("dashboard/", dashboard_view, name="dashboard"),

    # Fields — new primary entry point
    path("fields/", field_list_view, name="fields-list"),
    path("fields/<int:pk>/", field_detail_view, name="field-detail"),

    # Field crops (legacy / detailed reports)
    path("field-crops/", field_crop_list_view, name="field-crops"),
    path("field-crops/<int:pk>/", field_crop_detail_view, name="field-crop-detail"),

    # Seasons
    path("seasons/<int:pk>/report/", season_report_view, name="season-report"),
    path("seasons/create/", create_season, name="create-season"),

    # Operations
    path("my-operations/", my_operations_view, name="my-operations"),
    path("operations/<int:pk>/toggle/", toggle_operation_status, name="toggle-operation"),
    path("operations/create/", create_operation, name="create-operation"),

    # Workers / team
    path("workers/create/", create_worker, name="create-worker"),
    path("update-rate/", update_rate_view, name="update-rate"),

    # Agronomist management
    path("agronomists/invite/", invite_agronomist, name="invite-agronomist"),
    path("agronomists/", my_agronomists, name="my-agronomists"),
    path("agronomists/<int:pk>/remove/", remove_agronomist, name="remove-agronomist"),
    path("agronomists/<int:pk>/toggle-finance/", toggle_finance_access, name="toggle-finance-access"),

    # Agronomist portal
    path("agronomist/", agronomist_dashboard, name="agronomist-dashboard"),
    path("agronomist/owner/<int:owner_id>/", agronomist_owner_detail, name="agronomist-owner-detail"),
    path("agronomist/field-crops/<int:pk>/operations/", agronomist_field_operations, name="agronomist-field-operations"),
]
