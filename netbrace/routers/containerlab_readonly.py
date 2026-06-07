"""Read-only subprocess wrappers for live FRR routers in the clab-frrsq lab.

These are for eyeball-verification of oracle outputs against the live network.
EVERY function here is READ ONLY — no config-write functions exist.
"""

from __future__ import annotations

import subprocess


_TOPOLOGY = "frrsq"


def _vtysh(node: str, command: str) -> str:
    """Run a vtysh -c command on the named clab node. Returns stdout."""
    container = f"clab-{_TOPOLOGY}-{node}"
    result = subprocess.run(
        ["docker", "exec", container, "vtysh", "-c", command],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def show_bgp_summary(node: str) -> str:
    """Return `show ip bgp summary` output for a node."""
    return _vtysh(node, "show ip bgp summary")


def show_ip_route(node: str) -> str:
    """Return `show ip route` output for a node."""
    return _vtysh(node, "show ip route")


def show_running_config(node: str) -> str:
    """Return `show running-config` output for a node (read-only)."""
    return _vtysh(node, "show running-config")


def show_bgp_neighbors(node: str) -> str:
    """Return detailed BGP neighbor state for a node."""
    return _vtysh(node, "show ip bgp neighbors")
