from django.contrib import admin
from .models import FuelStation

# Register your models here.
@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "city", "state", "price")
    search_fields = ("name", "address", "city", "state")
    list_filter = ("state",)