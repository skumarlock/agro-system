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
    edit_operation,
    delete_operation,
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
    toggle_agronomist_permission,
    create_season,
    create_field_crop,
    edit_field_crop,
    delete_field_crop,
    edit_season,
    delete_season,
    chat_view,
    delete_chat_message,
    delete_chat_thread,
    inventory_view,
    recommendations_view,
    review_recommendation,
    fields_map_view,
    devices_view,
    add_device_data,
    delete_device,
    register_view,
)

urlpatterns = [
    # Auth
    path("register/", register_view, name="register"),

    # Home / redirect
    path("", home_redirect, name="home"),

    # Owner dashboard
    path("dashboard/", dashboard_view, name="dashboard"),

    # Fields — new primary entry point
    path("fields/", field_list_view, name="fields-list"),
    path("fields/map/", fields_map_view, name="fields-map"),
    path("fields/<int:pk>/", field_detail_view, name="field-detail"),

    # Field crops (legacy / detailed reports)
    path("field-crops/", field_crop_list_view, name="field-crops"),
    path("field-crops/<int:pk>/", field_crop_detail_view, name="field-crop-detail"),
    path("field-crops/<int:pk>/edit/", edit_field_crop, name="edit-field-crop"),
    path("field-crops/<int:pk>/delete/", delete_field_crop, name="delete-field-crop"),

    # Seasons
    path("seasons/<int:pk>/report/", season_report_view, name="season-report"),
    path("seasons/create/", create_season, name="create-season"),
    path("seasons/<int:pk>/edit/", edit_season, name="edit-season"),
    path("seasons/<int:pk>/delete/", delete_season, name="delete-season"),
    path("field-crops/create/", create_field_crop, name="create-field-crop"),

    # Operations
    path("my-operations/", my_operations_view, name="my-operations"),
    path("operations/<int:pk>/toggle/", toggle_operation_status, name="toggle-operation"),
    path("operations/<int:pk>/edit/", edit_operation, name="edit-operation"),
    path("operations/<int:pk>/delete/", delete_operation, name="delete-operation"),
    path("operations/create/", create_operation, name="create-operation"),

    # Collaboration / stock / planning
    path("chat/", chat_view, name="chat"),
    path("chat/<int:thread_id>/", chat_view, name="chat-thread"),
    path("chat/<int:thread_id>/delete/", delete_chat_thread, name="delete-chat-thread"),
    path("chat/messages/<int:message_id>/delete/", delete_chat_message, name="delete-chat-message"),
    path("inventory/", inventory_view, name="inventory"),
    path("recommendations/", recommendations_view, name="recommendations"),
    path("recommendations/<int:pk>/<slug:status>/", review_recommendation, name="review-recommendation"),
    path("devices/", devices_view, name="devices"),
    path("devices/<int:pk>/data/", add_device_data, name="add-device-data"),
    path("devices/<int:pk>/delete/", delete_device, name="delete-device"),

    # Workers / team
    path("workers/create/", create_worker, name="create-worker"),
    path("update-rate/", update_rate_view, name="update-rate"),

    # Agronomist management
    path("agronomists/invite/", invite_agronomist, name="invite-agronomist"),
    path("agronomists/", my_agronomists, name="my-agronomists"),
    path("agronomists/<int:pk>/remove/", remove_agronomist, name="remove-agronomist"),
    path("agronomists/<int:pk>/toggle-finance/", toggle_finance_access, name="toggle-finance-access"),
    path("agronomists/<int:pk>/toggle-permission/<slug:permission_name>/", toggle_agronomist_permission, name="toggle-agronomist-permission"),

    # Agronomist portal
    path("agronomist/", agronomist_dashboard, name="agronomist-dashboard"),
    path("agronomist/owner/<int:owner_id>/", agronomist_owner_detail, name="agronomist-owner-detail"),
    path("agronomist/field-crops/<int:pk>/operations/", agronomist_field_operations, name="agronomist-field-operations"),
]
