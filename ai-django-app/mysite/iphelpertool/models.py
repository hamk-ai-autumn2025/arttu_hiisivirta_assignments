from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class ConversionRecord(models.Model):
    ACTIONS = [
        ('auto', 'Auto Detect'),
        ('v4_to_v6_mapped', 'IPv4 → IPv6 (mapped ::ffff)'),
        ('v4_to_6to4', 'IPv4 → IPv6 (6to4 2002::/16)'),
        ('v6_mapped_to_v4', 'IPv6 (mapped) → IPv4'),
        ('expand_v6', 'Expand IPv6'),
        ('compress_v6', 'Compress IPv6'),
        ('subnet_info', 'Subnet Info'),
        ('reverse_dns', 'Reverse DNS'),
        ('eui64', 'EUI-64 from MAC'),
        ('bin_hex', 'Binary/Hex view'),
    ]
    action = models.CharField(max_length=40, choices=ACTIONS, default='auto')
    input_text = models.CharField(max_length=255)
    result_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_action_display()}] {self.input_text}"

class SavedSubnet(models.Model):
    name = models.CharField(max_length=100)
    cidr = models.CharField(max_length=100, help_text="e.g. 192.168.1.0/24 or 2001:db8::/48")
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.cidr})"
