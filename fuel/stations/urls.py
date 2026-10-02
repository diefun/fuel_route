from django.urls import path
from stations import views

urlpatterns = [
    path("route/", views.route_plan),
    path("route/map/", views.route_map),
]
