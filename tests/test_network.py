import socket
from types import SimpleNamespace

import pytest

from interactive_surface import network


def addr(ip):
    return SimpleNamespace(family=socket.AF_INET, address=ip)


def test_prefer_real_wifi_over_vpn_and_docker(monkeypatch):
    monkeypatch.setattr(network.psutil, "net_if_addrs", lambda: {
        "lo": [addr("127.0.0.1")],
        "docker0": [addr("172.17.0.1")],
        "wg0": [addr("10.10.0.2")],
        "wlp4s0": [addr("192.168.1.42")],
        "enp5s0": [addr("192.168.2.25")],
    })
    monkeypatch.setattr(network.psutil, "net_if_stats", lambda: {
        name: SimpleNamespace(isup=True)
        for name in ("lo", "docker0", "wg0", "wlp4s0", "enp5s0")
    })
    monkeypatch.setattr(network, "_default_route_interfaces", lambda: {"wlp4s0"})
    monkeypatch.setattr(network, "_outbound_ip", lambda: "10.10.0.2")
    ip, candidates = network.choose_lan_ip()
    assert ip == "192.168.1.42"
    assert {c.ip for c in candidates} == {"192.168.1.42", "192.168.2.25"}


def test_do_not_block_real_172_16_lan(monkeypatch):
    monkeypatch.setattr(network.psutil, "net_if_addrs", lambda: {
        "enp2s0": [addr("172.18.10.50")]
    })
    monkeypatch.setattr(network.psutil, "net_if_stats", lambda: {
        "enp2s0": SimpleNamespace(isup=True)
    })
    monkeypatch.setattr(network, "_default_route_interfaces", lambda: {"enp2s0"})
    monkeypatch.setattr(network, "_outbound_ip", lambda: "172.18.10.50")
    assert network.choose_lan_ip()[0] == "172.18.10.50"


def test_no_real_lan_returns_none(monkeypatch):
    monkeypatch.setattr(network.psutil, "net_if_addrs", lambda: {
        "lo": [addr("127.0.0.1")], "docker0": [addr("172.17.0.1")]
    })
    monkeypatch.setattr(network.psutil, "net_if_stats", lambda: {
        "lo": SimpleNamespace(isup=True), "docker0": SimpleNamespace(isup=True)
    })
    monkeypatch.setattr(network, "_default_route_interfaces", lambda: set())
    monkeypatch.setattr(network, "_outbound_ip", lambda: "172.17.0.1")
    assert network.choose_lan_ip() == (None, [])


def test_manual_override_must_be_local_ip(monkeypatch):
    monkeypatch.setattr(network.psutil, "net_if_addrs", lambda: {
        "enp2s0": [addr("192.168.1.5")]
    })
    monkeypatch.setattr(network.psutil, "net_if_stats", lambda: {
        "enp2s0": SimpleNamespace(isup=True)
    })
    monkeypatch.setattr(network, "_default_route_interfaces", lambda: set())
    monkeypatch.setattr(network, "_outbound_ip", lambda: None)
    assert network.choose_lan_ip("192.168.1.5")[0] == "192.168.1.5"
    with pytest.raises(ValueError):
        network.choose_lan_ip("127.0.0.1")
    with pytest.raises(ValueError):
        network.choose_lan_ip("192.168.1.99")
