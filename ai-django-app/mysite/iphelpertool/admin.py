from django.contrib import admin
from .models import ConversionRecord, SavedSubnet

@admin.register(ConversionRecord)
class ConversionRecordAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "input_text", "client_ip")
    list_filter = ("action", "created_at")
    search_fields = ("input_text", "result_text")

@admin.register(SavedSubnet)
class SavedSubnetAdmin(admin.ModelAdmin):
    list_display = ("name", "cidr", "created_at")
    search_fields = ("name", "cidr", "note")
