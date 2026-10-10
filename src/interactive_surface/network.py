"""Find a reachable IPv4 LAN address without advertising VPN/container IPs."""

from __future__ import annotations

import ipaddress
import json
import shutil
import socket
import subprocess
from dataclasses import dataclass

import psutil


PRIVATE_LANS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
VIRTUAL_PREFIXES = (
    "lo", "docker", "br-", "veth", "virbr", "vmnet", "vboxnet",
    "zt", "tailscale", "wg", "tun", "tap", "ppp", "nordlynx",
    "proton", "utun", "awdl", "llw", "bridge", "podman", "cni",
    "kube", "flannel", "waydroid", "anbox", "ham", "warp",
)


@dataclass(frozen=True)
class LanAddress:
    interface: str
    ip: str
    score: int


def _is_lan(ip: str) -> bool:
    try:
        address = ipaddress.IPv4Address(ip)
    except ipaddress.AddressValueError:
        return False
    return any(address in network for network in PRIVATE_LANS)


def _is_physical_interface(interface: str) -> bool:
    name = interface.lower()
    return not name.startswith(VIRTUAL_PREFIXES) and "virtual" not in name


def _default_route_interfaces() -> set[str]:
    if not shutil.which("ip"):
        return set()
    try:
        result = subprocess.run(
            ["ip", "-json", "-4", "route", "show", "default"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        if result.returncode:
            return set()
        routes = json.loads(result.stdout)
        physical = [
            route for route in routes
            if route.get("dev") and _is_physical_interface(route["dev"])
        ]
        if not physical:
            return set()
        best_metric = min(int(route.get("metric", 0)) for route in physical)
        return {
            route["dev"] for route in physical
            if int(route.get("metric", 0)) == best_metric
        }
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return set()


def _outbound_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))
            return sock.getsockname()[0]
    except OSError:
        return None


def lan_candidates() -> list[LanAddress]:
    """Rank active, private, non-virtual LAN adapters; never include loopback."""
    default_interfaces = _default_route_interfaces()
    outbound = _outbound_ip()
    stats = psutil.net_if_stats()
    found: list[LanAddress] = []
    for name, addrs in psutil.net_if_addrs().items():
        if not _is_physical_interface(name) or not stats.get(name) or not stats[name].isup:
            continue
        label = name.lower()
        for addr in addrs:
            if addr.family != socket.AF_INET or not _is_lan(addr.address):
                continue
            score = 0
            if name in default_interfaces:
                score += 100
            if addr.address == outbound:
                score += 70
            if label.startswith(("wlan", "wlp", "wlx", "wifi", "wi-fi", "wireless")):
                score += 30
            elif label.startswith(("en", "eth", "lan")):
                score += 20
            found.append(LanAddress(name, addr.address, score))
    return sorted(found, key=lambda item: (-item.score, item.interface, item.ip))


def choose_lan_ip(override: str | None = None) -> tuple[str | None, list[LanAddress]]:
    """Allow explicitly selecting a local RFC1918 IP when auto-selection is wrong."""
    candidates = lan_candidates()
    if override:
        if not _is_lan(override):
            raise ValueError("--lan-ip must be an IPv4 address on a private local network")
        assigned = {
            addr.address
            for addresses in psutil.net_if_addrs().values()
            for addr in addresses
            if addr.family == socket.AF_INET
        }
        if override not in assigned:
            raise ValueError(f"--lan-ip {override} is not assigned to this computer")
        return override, candidates
    return (candidates[0].ip if candidates else None), candidates
