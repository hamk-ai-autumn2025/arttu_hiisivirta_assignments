from django import forms

class IPToolForm(forms.Form):
    ACTIONS = [
        ('auto', 'Auto Detect & Do The Right Thing'),
        ('v4_to_v6_mapped', 'IPv4 → IPv6 (mapped ::ffff)'),
        ('v4_to_6to4', 'IPv4 → IPv6 (6to4 2002::/16)'),
        ('v6_mapped_to_v4', 'IPv6 (mapped) → IPv4'),
        ('expand_v6', 'Expand IPv6'),
        ('compress_v6', 'Compress IPv6'),
        ('subnet_info', 'Subnet Info (enter CIDR)'),
        ('reverse_dns', 'Reverse DNS name'),
        ('eui64', 'Build EUI-64 from MAC + /64'),
        ('bin_hex', 'Binary/Hex view (IP or CIDR)'),
    ]
    action = forms.ChoiceField(choices=ACTIONS, initial='auto')
    input_text = forms.CharField(
        label="IP / CIDR / MAC",
        widget=forms.TextInput(attrs={"placeholder": "e.g. 192.0.2.1 or 2001:db8::1 or 192.0.2.0/24 or 00:11:22:33:44:55"}),
    )
    extra = forms.CharField(
        label="Extra (optional)",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "For EUI-64: IPv6 /64 prefix (e.g. 2001:db8::/64)"}),
    )

class SaveSubnetForm(forms.Form):
    name = forms.CharField(max_length=100)
    cidr = forms.CharField(max_length=100)
    note = forms.CharField(widget=forms.Textarea, required=False)

