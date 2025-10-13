from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils.html import format_html, escape
from .forms import IPToolForm, SaveSubnetForm
from .models import ConversionRecord, SavedSubnet
from . import utils
import ipaddress
import json

def client_ip_from_request(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')

def home(request):
    form = IPToolForm(request.POST or None)
    save_form = SaveSubnetForm()
    result = None
    details = None

    if request.method == "POST" and form.is_valid():
        action = form.cleaned_data['action']
        input_text = form.cleaned_data['input_text'].strip()
        extra = form.cleaned_data.get('extra', '').strip()
        try:
            if action == 'auto':
                # Auto: detect and pick a sensible default
                if utils.is_ipv4(input_text):
                    result = {
                        "IPv4 → IPv6 (mapped)": utils.ipv4_to_ipv6_mapped(input_text),
                        "IPv4 → IPv6 (6to4)": utils.ipv4_to_6to4(input_text),
                        "Reverse DNS": utils.reverse_dns(input_text),
                        "Private?": str(ipaddress.ip_address(input_text).is_private),
                    }
                elif utils.is_ipv6(input_text):
                    mapped = utils.ipv6_mapped_to_ipv4(input_text)
                    result = {
                        "Compressed": utils.compress_ipv6(input_text),
                        "Expanded": utils.expand_ipv6(input_text),
                        "IPv6 (mapped) → IPv4": mapped or "N/A",
                        "Reverse DNS": utils.reverse_dns(input_text),
                    }
                elif utils.parse_network(input_text):
                    details = utils.subnet_info(input_text)
                    result = {"Subnet Info": details}
                else:
                    raise ValueError("Could not detect IPv4/IPv6/CIDR")
            elif action == 'v4_to_v6_mapped':
                result = utils.ipv4_to_ipv6_mapped(input_text)
            elif action == 'v4_to_6to4':
                result = utils.ipv4_to_6to4(input_text)
            elif action == 'v6_mapped_to_v4':
                out = utils.ipv6_mapped_to_ipv4(input_text)
                if not out:
                    raise ValueError("Not an IPv4-mapped IPv6 address (::ffff:0:0/96)")
                result = out
            elif action == 'expand_v6':
                result = utils.expand_ipv6(input_text)
            elif action == 'compress_v6':
                result = utils.compress_ipv6(input_text)
            elif action == 'subnet_info':
                details = utils.subnet_info(input_text)
                result = details
            elif action == 'reverse_dns':
                result = utils.reverse_dns(input_text)
            elif action == 'eui64':
                if not extra:
                    raise ValueError("Provide the IPv6 /64 prefix in Extra.")
                result = utils.build_eui64_address(extra, input_text)
            elif action == 'bin_hex':
                result = utils.ip_bin_hex_view(input_text)

            if isinstance(result, (dict, list)):
                result_text = json.dumps(result, indent=2, sort_keys=True)
            else:
                result_text = str(result)

            rec = ConversionRecord.objects.create(
                action=action,
                input_text=input_text if not extra else f"{input_text} | {extra}",
                result_text=result_text,
                client_ip=client_ip_from_request(request),
                user=request.user if request.user.is_authenticated else None,
            )
            messages.success(request, "Done!")
        except Exception as e:
            messages.error(request, f"Error: {escape(str(e))}")

    history = ConversionRecord.objects.all()[:20]
    subnets = SavedSubnet.objects.all()[:20]
    return render(request, "iphelpertool/index.html", {
        "form": form,
        "save_form": save_form,
        "result": result,
        "details": details,
        "history": history,
        "subnets": subnets,
    })

def save_subnet(request):
    if request.method == "POST":
        form = SaveSubnetForm(request.POST)
        if form.is_valid():
            SavedSubnet.objects.create(**form.cleaned_data)
            messages.success(request, "Subnet saved.")
    return redirect("iphelpertool:home")

