import ipaddress
import re
import ipaddress


def is_ipv4(value: str):
    try:
        ipaddress.IPv4Address(value)
        return True
    except:
        return False

def is_ipv6(value: str):
    try:
        ipaddress.IPv6Address(value)
        return True
    except:
        return False

def parse_network(value: str):
    try:
        return ipaddress.ip_network(value, strict=False)
    except:
        return None

def ipv4_to_ipv6_mapped(v4: str) -> str:
    ip4 = ipaddress.IPv4Address(v4)
    return str(ipaddress.IPv6Address('::ffff:' + str(ip4)))

def ipv4_to_6to4(v4: str) -> str:
    ip4 = ipaddress.IPv4Address(v4)
    hexstr = f"{int(ip4):08x}"
    # 2002:WWXX:YYZZ::/48 where WWXXYYZZ = IPv4 in hex
    return f"2002:{hexstr[0:4]}:{hexstr[4:8]}::/48"

def ipv6_mapped_to_ipv4(v6: str):
    ip6 = ipaddress.IPv6Address(v6)
    if ip6.ipv4_mapped:
        return str(ip6.ipv4_mapped)
    return None

def expand_ipv6(v6: str) -> str:
    return str(ipaddress.IPv6Address(v6).exploded)

def compress_ipv6(v6: str) -> str:
    return str(ipaddress.IPv6Address(v6).compressed)

def subnet_info(cidr: str) -> dict:
    net = ipaddress.ip_network(cidr, strict=False)
    data = {
        "version": net.version,
        "network": str(net.network_address),
        "broadcast": str(net.broadcast_address) if net.version == 4 else None,
        "netmask": str(net.netmask) if net.version == 4 else str(net.prefixlen),
        "hostmask": str(net.hostmask) if net.version == 4 else None,
        "prefixlen": net.prefixlen,
        "num_addresses": net.num_addresses,
        "first_usable": None,
        "last_usable": None,
        "is_private": net.is_private,
        "is_multicast": net.is_multicast,
        "is_reserved": net.is_reserved,
        "is_link_local": net.is_link_local,
        "is_loopback": net.is_loopback,
        "sample_hosts": [],
    }
    if net.version == 4 and net.num_addresses >= 4:
        first = int(net.network_address) + 1
        last = int(net.broadcast_address) - 1
        data["first_usable"] = str(ipaddress.IPv4Address(first))
        data["last_usable"] = str(ipaddress.IPv4Address(last))
    if net.num_addresses >= 4:
        # give a couple of sample hosts for large nets
        step = max(net.num_addresses // 10, 1)
        samples = []
        for i in range(1, min(5, net.num_addresses-1)):
            try:
                samples.append(str(net[i*step]))
            except IndexError:
                break
        data["sample_hosts"] = samples
    return data

def reverse_dns(value: str) -> str:
    if is_ipv4(value):
        parts = value.split(".")[::-1]
        return ".".join(parts) + ".in-addr.arpa."
    elif is_ipv6(value):
        # ip6.arpa nibble format
        full = ipaddress.IPv6Address(value).exploded.replace(":", "")
        nibbles = ".".join(full[::-1])
        return nibbles + ".ip6.arpa."
    raise ValueError("Not a valid IPv4/IPv6 address")

def mac_to_eui64_interface_id(mac: str) -> str:
    # Normalize
    mac_hex = re.sub(r'[^0-9A-Fa-f]', '', mac)
    if len(mac_hex) != 12:
        raise ValueError("MAC must be 48-bit (6 bytes)")
    # Split into bytes
    b = [int(mac_hex[i:i+2], 16) for i in range(0, 12, 2)]
    # Flip U/L bit
    b[0] ^= 0x02
    # Insert FF:FE in the middle
    eui = b[:3] + [0xFF, 0xFE] + b[3:]
    # Format as interface ID (64 bits)
    return f"{eui[0]:02x}{eui[1]:02x}:{eui[2]:02x}{eui[3]:02x}:{eui[4]:02x}{eui[5]:02x}:{eui[6]:02x}{eui[7]:02x}"

def build_eui64_address(prefix64: str, mac: str) -> str:
    net = ipaddress.ip_network(prefix64, strict=False)
    if net.version != 6 or net.prefixlen != 64:
        raise ValueError("Prefix must be IPv6 /64")
    iid = mac_to_eui64_interface_id(mac)
    # Combine network + IID
    return str(ipaddress.IPv6Address(int(net.network_address) | int(ipaddress.IPv6Address(iid))))


def _chunk(s: str, n: int):
    return [s[i:i+n] for i in range(0, len(s), n)]

def _ipv4_bin(addr: ipaddress.IPv4Address) -> str:
    b = f"{int(addr):032b}"
    # group by 8 (octets) like 11111111.00000000.00000000.00000001
    return ".".join(_chunk(b, 8))

def _ipv6_bin(addr: ipaddress.IPv6Address) -> str:
    b = f"{int(addr):0128b}"
    # group by 16 (hextets) for readability
    return ":".join(_chunk(b, 16))

def _mask_bin(mask_addr, version: int) -> str:
    if version == 4:
        return _ipv4_bin(mask_addr)
    else:
        return _ipv6_bin(mask_addr)

def ip_bin_hex_view(value: str) -> dict:
    """
    Accepts either a single IP (v4/v6) or a CIDR network.
    Returns a dict with normalized, binary and hex views.
    """
    # Try network first (handles '192.0.2.0/24' and '2001:db8::/32')
    net = None
    try:
        net = ipaddress.ip_network(value, strict=False)
    except Exception:
        net = None

    if net:
        data = {
            "kind": "network",
            "version": net.version,
            "input": value,
            "network": str(net.network_address),
            "broadcast": str(net.broadcast_address) if net.version == 4 else None,
            "prefixlen": net.prefixlen,
            "netmask": str(net.netmask) if net.version == 4 else str(net.prefixlen),
            "hostmask": str(net.hostmask) if net.version == 4 else None,
            "network_bin": _ipv4_bin(net.network_address) if net.version == 4 else _ipv6_bin(net.network_address),
            "netmask_bin": _mask_bin(net.netmask, 4) if net.version == 4 else ":".join(_chunk("1"*net.prefixlen + "0"*(128-net.prefixlen), 16)),
            "network_hex": f"0x{int(net.network_address):X}",
        }
        if net.version == 4:
            data["netmask_hex"] = f"0x{int(net.netmask):X}"
        else:
            # For IPv6, show the prefix mask hex (derived from prefixlen)
            mask_int = (2**128 - 1) ^ (2**(128 - net.prefixlen) - 1)
            data["prefix_mask_hex"] = f"0x{mask_int:X}"
        return data

    # Otherwise, treat as a single IP address
    addr = ipaddress.ip_address(value)
    info = {
        "kind": "address",
        "version": addr.version,
        "input": value,
        "normalized": str(addr),
        "binary": _ipv4_bin(addr) if addr.version == 4 else _ipv6_bin(addr),
        "hex": f"0x{int(addr):X}",
        "int": int(addr),
        "is_private": addr.is_private,
        "is_loopback": addr.is_loopback,
        "is_link_local": addr.is_link_local,
        "reverse_dns": addr.reverse_pointer,
    }
    if addr.version == 6:
        info["compressed"] = addr.compressed
        info["expanded"] = addr.exploded
        if addr.ipv4_mapped:
            info["ipv4_mapped"] = str(addr.ipv4_mapped)
    return info

