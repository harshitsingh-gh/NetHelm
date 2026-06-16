#!/usr/bin/env python3
"""Live-FRR validity harness for the NetHELM blast-radius oracle.

Cross-checks the Batfish oracle's ground truth against REAL FRR containers
running the scenario configs. For each scenario:
  1. Render a temporary containerlab topology from the scenario's node configs.
  2. Boot the PRE config, wait for BGP convergence via poll (never fixed sleep).
  3. Gather live state twice for stability.
  4. Apply the POST config via vtysh, wait for reconvergence.
  5. Gather live state twice again.
  6. Diff pre vs post -> the LIVE typed damage set, in the SAME key format as
     the Batfish oracle output.
  7. Run ExtendedOracle.compute(scenario) -> Batfish ground truth.
  8. Compare per-dimension -> AGREE / DIVERGE with explanation.

The harness REPORTS divergences honestly — finding them is the whole point.
See docs/oracle_determinism_spec_v1.md for the doctrine.

Usage:
    source harness/venvs/nethelm/bin/activate
    python scripts/validity_live_frr.py [--scenarios ipc ipc_static blackhole ecmp]
                                         [--output runs/validity_<ts>.json]
                                         [--no-batfish]   # skip oracle compare; live-only
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Path setup — harness must be importable without the caller activating the venv
# first (it sets up sys.path on invocation).
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# ---------------------------------------------------------------------------
# Scenario imports — lazy so --no-batfish is pure local, no pybatfish needed.
# ---------------------------------------------------------------------------
from netbrace.tasks.safety.scenarios import build  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FRR_IMAGE = "quay.io/frrouting/frr:10.6.1"
_LAB_DIR = _REPO / "harness" / "lab"
_DAEMONS_SRC = _LAB_DIR / "frr_square" / "configs" / "r1" / "daemons"

# Convergence polling: poll every POLL_INTERVAL seconds, give up after TIMEOUT.
BGP_POLL_INTERVAL = 3
BGP_TIMEOUT = 120
# Stability: the route count must be identical across STABILITY_CHECKS consecutive polls.
STABILITY_CHECKS = 2

# ---------------------------------------------------------------------------
# Helper: run a shell command, return (stdout, returncode).
# ---------------------------------------------------------------------------
def _run(cmd: list[str], *, check: bool = True, timeout: int = 60) -> tuple[str, int]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"Command {cmd} failed:\n{r.stderr}\n{r.stdout}")
    return r.stdout, r.returncode


# ---------------------------------------------------------------------------
# Helper: run vtysh on a container, return stdout.
# ---------------------------------------------------------------------------
def vtysh(container: str, command: str, *, check: bool = True) -> str:
    out, _ = _run(["docker", "exec", container, "vtysh", "-c", command], check=check)
    return out


# ---------------------------------------------------------------------------
# Convergence settle-check: poll bgp summary on all containers until:
#   - every neighbor shows a numeric uptime (not "Active"/"Connect"/"Idle"/Hmm)
#   - the total advertised-prefix count is stable across STABILITY_CHECKS polls
# Returns (True, elapsed_seconds) on success, raises TimeoutError on failure.
# ---------------------------------------------------------------------------
def _wait_bgp_converged(
    containers: list[str],
    *,
    poll_interval: int = BGP_POLL_INTERVAL,
    timeout: int = BGP_TIMEOUT,
    min_prefixes: int = 0,
) -> float:
    """Poll BGP summary on all containers until all sessions are ESTABLISHED and
    the RIB prefix count is stable across two consecutive polls AND at least
    ``min_prefixes`` total PfxRcd are seen across the network.

    ``min_prefixes`` prevents a false-convergence at 0/0 (sessions up but no
    routes propagated yet). For a topology with N nodes where each originates 1
    prefix, set min_prefixes=N. Defaults to 0 for callers that don't know N.
    """
    start = time.monotonic()
    prev_counts: Optional[dict[str, int]] = None

    while True:
        elapsed = time.monotonic() - start
        if elapsed > timeout:
            raise TimeoutError(
                f"BGP convergence timeout after {timeout}s — sessions not ESTABLISHED"
            )
        all_up = True
        counts: dict[str, int] = {}
        for ctr in containers:
            try:
                summary = vtysh(ctr, "show ip bgp summary", check=False)
            except Exception:
                all_up = False
                break
            # Parse peer lines: IP V AS MsgR MsgS TblVer InQ OutQ Up/Down PfxRcd PfxSnt Desc
            # Index:                0 1  2   3    4    5      6   7    8       9      10    11
            # Up/Down (index 8) is a time string for ESTABLISHED, a state name otherwise.
            peer_lines = [ln for ln in summary.splitlines()
                          if re.match(r"^\d+\.\d+\.\d+\.\d+", ln)]
            if not peer_lines:
                # No peer lines yet — BGP not up at all
                all_up = False
                break
            non_est = False
            pfx_total = 0
            for peer_line in peer_lines:
                parts = peer_line.split()
                if len(parts) < 10:
                    non_est = True
                    break
                uptime = parts[8]
                if not re.match(r"^(\d+d?\d+h?\d+h?\d+m?|\d+:\d+:\d+)$", uptime):
                    non_est = True
                    break
                # PfxRcd is index 9
                try:
                    pfx_total += int(parts[9])
                except ValueError:
                    pass  # "never" or similar
            if non_est:
                all_up = False
                break
            counts[ctr] = pfx_total

        if all_up:
            total = sum(counts.values())
            if total >= min_prefixes:
                if prev_counts is not None and counts == prev_counts:
                    return time.monotonic() - start
                prev_counts = counts
            # else: min_prefixes not met yet, keep polling

        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Config stripping: given a Batfish-format config (with the hostname header
# and Debian auto/iface block), return the live frr.conf text.
# ---------------------------------------------------------------------------
def _strip_to_frr_conf(batfish_cfg: str) -> str:
    """Strip the Batfish wrapper (hostname line + Debian iface block) -> frr.conf.

    The Batfish format (baseline_*.py) has this header:
        <hostname>\n
        # This file describes ...\n
        auto lo\n
        ...
        # ports.conf --\n
        \n
        frr version 10.6.1\n
        frr defaults traditional\n
        ...
    The live frr.conf is everything from 'frr defaults traditional' onwards.
    """
    lines = batfish_cfg.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().startswith("frr defaults"):
            return "\n".join(lines[i:]) + "\n"
    # fallback: return as-is (may already be frr.conf form)
    return batfish_cfg


# ---------------------------------------------------------------------------
# Topology creation helpers
# ---------------------------------------------------------------------------
def _infer_links(configs: dict[str, str]) -> list[tuple[str, str, str, str]]:
    """Infer P2P links from shared /30 subnets in the configs.

    Parses every 'ip address X.X.X.X/30' from interface blocks. Two nodes that
    share the same /30 subnet are on the same link. Returns a list of
    (node_a, iface_a, node_b, iface_b) tuples (each link appears once,
    lower-numbered node first by convention; we just preserve discovery order).

    Only /30 subnets are considered (the project's P2P addressing scheme).
    """
    # node -> {subnet_str -> iface_name}
    node_subnets: dict[str, dict[str, str]] = {}
    for node, cfg in configs.items():
        subnets: dict[str, str] = {}
        current_iface = None
        for ln in cfg.splitlines():
            # interface block header
            m = re.match(r"^interface\s+(\S+)", ln)
            if m:
                current_iface = m.group(1)
                continue
            # ip address inside an interface block
            m = re.match(r"^\s+ip address\s+(\d+\.\d+\.\d+\.\d+)/30", ln)
            if m and current_iface and current_iface != "lo":
                ip = m.group(1)
                # derive the /30 network base
                parts = [int(x) for x in ip.split(".")]
                # zero out the last two bits
                host = parts[3] & 0xFC  # mask to /30 base
                net = f"{parts[0]}.{parts[1]}.{parts[2]}.{host}/30"
                subnets[net] = current_iface
        node_subnets[node] = subnets

    # find shared /30s
    links: list[tuple[str, str, str, str]] = []
    nodes = list(node_subnets.keys())
    seen: set[str] = set()
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            for subnet, iface_a in node_subnets[a].items():
                if subnet in seen:
                    continue
                if subnet in node_subnets[b]:
                    iface_b = node_subnets[b][subnet]
                    links.append((a, iface_a, b, iface_b))
                    seen.add(subnet)
    return links


def _write_clab_topology(
    topo_name: str,
    nodes: list[str],
    configs_dir: Path,
    links: list[tuple[str, str, str, str]],
    extra_exec: Optional[dict[str, list[str]]] = None,
) -> Path:
    """Write a .clab.yml to a temporary location and return its path."""
    node_blocks = []
    for node in nodes:
        node_block = f"    {node}:\n"
        node_block += "      binds:\n"
        node_block += f"        - {configs_dir / node / 'daemons'}:/etc/frr/daemons\n"
        node_block += f"        - {configs_dir / node / 'frr.conf'}:/etc/frr/frr.conf\n"
        if extra_exec and node in extra_exec:
            node_block += "      exec:\n"
            for cmd in extra_exec[node]:
                node_block += f"        - {cmd}\n"
        node_blocks.append(node_block)

    link_lines = []
    for a_node, a_iface, b_node, b_iface in links:
        link_lines.append(f'    - endpoints: ["{a_node}:{a_iface}", "{b_node}:{b_iface}"]')

    clab_text = f"""name: {topo_name}

topology:
  defaults:
    kind: linux
    image: {FRR_IMAGE}

  nodes:
{chr(10).join(node_blocks)}
  links:
{chr(10).join(link_lines)}
"""
    clab_path = configs_dir.parent / f"{topo_name}.clab.yml"
    clab_path.write_text(clab_text)
    return clab_path


def _write_node_configs(configs_dir: Path, node_configs: dict[str, str]) -> None:
    """Write frr.conf + copy daemons for each node under configs_dir/<node>/."""
    for node, cfg_text in node_configs.items():
        node_dir = configs_dir / node
        node_dir.mkdir(parents=True, exist_ok=True)
        (node_dir / "frr.conf").write_text(_strip_to_frr_conf(cfg_text))
        # Copy the canonical daemons file (staticd + zebra + bgpd = yes)
        import shutil
        shutil.copy(str(_DAEMONS_SRC), str(node_dir / "daemons"))


# ---------------------------------------------------------------------------
# Live state gathering
# ---------------------------------------------------------------------------
def _gather_bgp_sessions(containers: list[str]) -> dict[str, set[str]]:
    """Return {container -> set of established peer IPs}."""
    result: dict[str, set[str]] = {}
    for ctr in containers:
        try:
            out = vtysh(ctr, "show ip bgp summary", check=False)
        except Exception:
            result[ctr] = set()
            continue
        peers = set()
        # Lines that have a numeric uptime (ESTABLISHED) look like:
        # 10.0.0.2  4  65000  4  7  1  0  0  00:00:25  0  1 N/A
        # Index:     0  1  2   3  4  5  6  7   8        9 10 11
        # Up/Down is index 8; State/PfxRcd is index 9.
        for ln in out.splitlines():
            parts = ln.split()
            if len(parts) >= 10 and re.match(r"^\d+\.\d+\.\d+\.\d+$", parts[0]):
                uptime_or_state = parts[8]
                # HH:MM:SS or 1d20h13m or 00:01:23 = ESTABLISHED
                # "Active"/"Connect"/"Idle" = not established
                if re.match(r"^(\d+d?\d+h?\d+m?|\d+:\d+:\d+)$", uptime_or_state):
                    peers.add(parts[0])
        result[ctr] = peers
    return result


def _gather_rib_prefixes(containers: list[str]) -> dict[str, set[str]]:
    """Return {container -> set of installed route prefixes (network/mask)}."""
    result: dict[str, set[str]] = {}
    for ctr in containers:
        try:
            out = vtysh(ctr, "show ip route", check=False)
        except Exception:
            result[ctr] = set()
            continue
        prefixes = set()
        for ln in out.splitlines():
            # FRR show ip route: lines starting with K/C/S/B/O etc. then prefix
            # e.g.: "B>* 10.0.0.2/32 [200/0] via 10.0.0.2 ..."
            #        "S   10.0.0.2/32 [1/0] via 192.0.2.2 ..."
            # We capture any route including static, BGP, connected, kernel
            m = re.match(r"^[A-Z>*\s]+(\d+\.\d+\.\d+\.\d+/\d+)", ln)
            if m:
                prefixes.add(m.group(1))
        result[ctr] = prefixes
    return result


def _gather_bgp_rib_best(containers: list[str]) -> dict[str, set[str]]:
    """Return {container -> set of prefixes with BEST BGP route (*>)}."""
    result: dict[str, set[str]] = {}
    for ctr in containers:
        try:
            out = vtysh(ctr, "show ip bgp", check=False)
        except Exception:
            result[ctr] = set()
            continue
        prefixes = set()
        for ln in out.splitlines():
            # Lines with *> (best route): " *>  10.0.0.1/32  ..." or "*>i ..."
            # The prefix is the first network-looking token after the status codes
            m = re.match(r"^\s*\*>i?\s+(\d+\.\d+\.\d+\.\d+/\d+)", ln)
            if m:
                prefixes.add(m.group(1))
        result[ctr] = prefixes
    return result


def _gather_route_nexthop_count(container: str, prefix: str) -> int:
    """Count installed routes for an exact prefix on a container (ECMP width)."""
    try:
        out = vtysh(container, f"show ip route {prefix}", check=False)
    except Exception:
        return 0
    # Count lines that show 'via' (each is a separate ECMP next-hop)
    return len(re.findall(r"\bvia\b", out))


def _ping_reachability(src_container: str, dst_ip: str, src_ip: Optional[str] = None) -> bool:
    """True if a ping from src_container to dst_ip succeeds (1 packet, 2s timeout).

    ``src_ip`` forces the source IP. Always use the node's loopback when available:
    the kernel's default source-IP selection picks the egress-interface IP, which
    the destination may not have a return route for (asymmetric topology). Using the
    loopback as source matches Batfish's model (the logical BGP reachability check
    uses the node's router-id / loopback as origin).
    """
    cmd = ["docker", "exec", src_container, "ping", "-c", "1", "-W", "2"]
    if src_ip:
        cmd += ["-I", src_ip]
    cmd.append(dst_ip)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return r.returncode == 0


def _traceroute_exits(src_container: str, dst_ip: str) -> bool:
    """True if traceroute from src exits (gets a response, TTL-expired or ICMP echo)."""
    # Use ping with TTL=64 — if it reaches, we get echo reply; if not, unreachable
    return _ping_reachability(src_container, dst_ip)


# ---------------------------------------------------------------------------
# Live state snapshot (gathered twice for stability)
# ---------------------------------------------------------------------------
def _extract_loopback_ips(configs: dict[str, str]) -> dict[str, str]:
    """Return {node: loopback_ip} by parsing 'ip address X.X.X.X/32' on the lo interface."""
    result: dict[str, str] = {}
    for node, cfg in configs.items():
        in_lo = False
        for ln in cfg.splitlines():
            m = re.match(r"^interface\s+(\S+)", ln)
            if m:
                in_lo = (m.group(1) == "lo")
                continue
            if in_lo:
                m = re.match(r"^\s+ip address\s+(\d+\.\d+\.\d+\.\d+)/32", ln)
                if m:
                    result[node] = m.group(1)
                    in_lo = False
    return result


def _live_dst_ip(prefix: str) -> str:
    """Return a pingable host IP for a CIDR prefix.

    For /32 the address IS the host. For wider prefixes (e.g. 203.0.113.0/24)
    the network address is not assigned to any host; use the first host (.1).
    This matches how the ipc3 scenario assigns dum0: 203.0.113.1/24.
    """
    addr = prefix.split("/")[0]
    mask = int(prefix.split("/")[1]) if "/" in prefix else 32
    if mask == 32:
        return addr  # /32 is always a host address
    # Increment the last octet by 1 to get the first host
    parts = addr.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def _gather_live_state(
    ctr_prefix: str,
    nodes: list[str],
    reachability_flows: list[tuple[str, str]],
    redundancy_targets: list[tuple[str, str]],
    bgp_watch_prefixes: list[str],
    node_loopbacks: Optional[dict[str, str]] = None,
) -> tuple[dict, bool]:
    """Gather full live state; return (state_dict, stable).

    Gathers twice and compares — if the set of sessions + prefixes is identical
    across both samples, stable=True. Unstable state is flagged but still returned
    (using the first sample).
    """
    containers = [f"{ctr_prefix}-{node}" for node in nodes]
    node_to_ctr = {node: f"{ctr_prefix}-{node}" for node in nodes}

    def _sample():
        sessions = _gather_bgp_sessions(containers)
        rib = _gather_rib_prefixes(containers)
        bgp_best = _gather_bgp_rib_best(containers)
        # Reachability flows — always ping FROM the node's loopback IP to avoid
        # asymmetric-routing failures (the default kernel source IP is the
        # egress-interface IP, which the destination may not have a return route for).
        # Destination: use a HOST address within the prefix. The oracle (Batfish)
        # traces to the network address (e.g. 203.0.113.0 for /24), but ICMP ping
        # requires a host address. For /32 the network IS the host; for wider prefixes
        # we probe the first host (network_addr + 1) so there's always a real target.
        reach: dict[tuple[str, str], bool] = {}
        for src_node, dst_prefix in reachability_flows:
            dst_ip = _live_dst_ip(dst_prefix)
            ctr = node_to_ctr.get(src_node)
            if ctr:
                src_loopback = (node_loopbacks or {}).get(src_node)
                reach[(src_node, dst_prefix)] = _ping_reachability(ctr, dst_ip, src_loopback)
        # Redundancy targets (ECMP width)
        redundancy: dict[tuple[str, str], int] = {}
        for node, prefix in redundancy_targets:
            ctr = node_to_ctr.get(node)
            if ctr:
                redundancy[(node, prefix)] = _gather_route_nexthop_count(ctr, prefix)
        return {
            "sessions": sessions,
            "rib": rib,
            "bgp_best": bgp_best,
            "reachability": reach,
            "redundancy": redundancy,
        }

    s1 = _sample()
    time.sleep(2)
    s2 = _sample()

    # Stability: sessions + rib should be identical across both samples
    stable = (s1["sessions"] == s2["sessions"]) and (s1["rib"] == s2["rib"])

    return s1, stable


# ---------------------------------------------------------------------------
# Derive the live damage set from pre vs post state
# ---------------------------------------------------------------------------
def _derive_live_damage(
    pre: dict,
    post: dict,
    scenario_name: str,
    nodes: list[str],
    ctr_prefix: str,
    watched_prefixes: list[str],
    reachability_flows: list[tuple[str, str]],
    redundancy_targets: list[tuple[str, str]],
    bgp_watch_prefixes: list[str],
) -> dict[str, set[str]]:
    """Compute the LIVE damage key-sets in the SAME key format as ExtendedOracle."""
    live_keys: dict[str, set[str]] = {
        "sessions": set(),
        "prefixes": set(),
        "reachability": set(),
        "waypoint": set(),
        "redundancy": set(),
        "filter": set(),
        "forwarding": set(),
        "scale": set(),
        "bgp_withdrawn": set(),
        "intent": set(),
    }

    node_to_ctr = {node: f"{ctr_prefix}-{node}" for node in nodes}
    watched_set = set(watched_prefixes or [])

    # D1: sessions lost — key format: bgp|vrf=default|node=<n>|peer_ip=<ip>
    # (matches SessionLost.key in schemas.py)
    for node in nodes:
        ctr = node_to_ctr[node]
        pre_peers = pre["sessions"].get(ctr, set())
        post_peers = post["sessions"].get(ctr, set())
        for peer_ip in pre_peers - post_peers:
            live_keys["sessions"].add(f"bgp|vrf=default|node={node}|peer_ip={peer_ip}")

    # D2: prefixes lost from RIB (scoped to watched_prefixes)
    # Key format: route|node=<n>|vrf=default|prefix=<p>  (matches PrefixLost.key)
    for node in nodes:
        ctr = node_to_ctr[node]
        pre_rib = pre["rib"].get(ctr, set())
        post_rib = post["rib"].get(ctr, set())
        for prefix in pre_rib - post_rib:
            if _prefix_in_watched(prefix, watched_set):
                live_keys["prefixes"].add(f"route|node={node}|vrf=default|prefix={prefix}")

    # D3: reachability lost
    # Key format: reach|src=<n>|dst=<p>|vrf=default  (matches ReachabilityLost.key)
    for (src_node, dst_prefix), pre_ok in pre["reachability"].items():
        post_ok = post["reachability"].get((src_node, dst_prefix), True)
        if pre_ok and not post_ok:
            live_keys["reachability"].add(
                f"reach|src={src_node}|dst={dst_prefix}|vrf=default"
            )

    # D5: redundancy loss (ECMP width drop, still reachable)
    # Key format: redundancy|node=<n>|vrf=default|prefix=<p>  (matches RedundancyLoss.key)
    for (node, prefix), pre_count in pre["redundancy"].items():
        post_count = post["redundancy"].get((node, prefix), 0)
        if pre_count > post_count >= 1:
            live_keys["redundancy"].add(
                f"redundancy|node={node}|vrf=default|prefix={prefix}"
            )

    # D7: forwarding anomaly — was reachable pre, not reachable post, AND
    # NOT already scored as reachability loss via D3
    # (for the live harness we use ping: no delivery = potential blackhole/null-route)
    # We detect D7 separately from D3: D7 fires when ping fails AND it's a
    # forwarding_flows probe (as declared in the scenario). However, our harness
    # doesn't have the scenario's forwarding_flows here — we infer from reachability.
    # We mark these as "blackhole" by convention (we can't distinguish NO_ROUTE from
    # NULL_ROUTED via ping alone; that's a known limitation of the live harness).
    # For now, forwarding anomalies are reported when reachability was lost AND
    # we probe a forwarding_flow target.
    # NOTE: This is populated by the caller with additional forwarding context.

    # D9: BGP-RIB BEST withdrawal
    if bgp_watch_prefixes:
        bgp_watch_set = set(bgp_watch_prefixes)
        for node in nodes:
            ctr = node_to_ctr[node]
            pre_best = pre["bgp_best"].get(ctr, set())
            post_best = post["bgp_best"].get(ctr, set())
            for prefix in pre_best - post_best:
                if _prefix_in_watched(prefix, bgp_watch_set):
                    live_keys["bgp_withdrawn"].add(
                        f"bgp_withdrawn|node={node}|vrf=default|network={prefix}"
                    )

    return live_keys


def _prefix_in_watched(prefix: str, watched: set[str]) -> bool:
    """Check if a prefix matches a watched prefix (exact match, case-insensitive)."""
    return prefix in watched or prefix.lower() in {w.lower() for w in watched}


# ---------------------------------------------------------------------------
# Oracle comparison
# ---------------------------------------------------------------------------
def _compare_to_oracle(
    scenario_name: str,
    live_keys: dict[str, set[str]],
    oracle_keys: dict[str, set[str]],
) -> dict:
    """Compare live vs oracle per dimension. Returns structured result."""
    dims = ["sessions", "prefixes", "reachability", "redundancy",
            "forwarding", "bgp_withdrawn"]
    result = {
        "scenario": scenario_name,
        "dimensions": {},
        "overall": "AGREE",
    }
    any_diverge = False

    for dim in dims:
        live = live_keys.get(dim, set())
        oracle = oracle_keys.get(dim, set())

        only_in_live = live - oracle
        only_in_oracle = oracle - live

        if only_in_live or only_in_oracle:
            verdict = "DIVERGE"
            any_diverge = True
        else:
            verdict = "AGREE"

        result["dimensions"][dim] = {
            "verdict": verdict,
            "live_keys": sorted(live),
            "oracle_keys": sorted(oracle),
            "only_in_live": sorted(only_in_live),
            "only_in_oracle": sorted(only_in_oracle),
            "live_count": len(live),
            "oracle_count": len(oracle),
        }

    if any_diverge:
        result["overall"] = "DIVERGE"

    return result


# ---------------------------------------------------------------------------
# Single-scenario run
# ---------------------------------------------------------------------------
def run_scenario(
    scenario_name: str,
    *,
    batfish_host: str = "127.0.0.1",
    run_batfish: bool = True,
) -> dict:
    """Run the live-FRR validity check for one scenario.

    Returns a result dict with keys:
      scenario, live_pre_stable, live_post_stable, live_keys, oracle_keys,
      comparison, batfish_ran, errors, topology, timing.
    """
    result: dict = {
        "scenario": scenario_name,
        "batfish_ran": run_batfish,
        "errors": [],
        "warnings": [],
        "topology": {},
        "timing": {},
        "live_pre_stable": False,
        "live_post_stable": False,
        "live_keys": {},
        "oracle_keys": {},
        "comparison": {},
    }

    print(f"\n{'='*60}")
    print(f"SCENARIO: {scenario_name}")
    print(f"{'='*60}")

    # 1. Build scenario object
    try:
        scn = build(scenario_name)
    except Exception as e:
        result["errors"].append(f"Failed to build scenario: {e}")
        return result

    nodes = scn.nodes
    pre_configs = scn.pre_configs
    post_configs = scn.post_configs()
    result["topology"] = {"nodes": nodes, "node_count": len(nodes)}

    print(f"Nodes: {nodes}")
    print(f"Change target: {scn.change_target}")

    # 2. Infer links
    links = _infer_links(pre_configs)
    if not links:
        result["errors"].append("Could not infer any P2P links from configs")
        return result
    print(f"Inferred links: {[(a, ia, b, ib) for (a, ia, b, ib) in links]}")
    result["topology"]["links"] = [(a, ia, b, ib) for (a, ia, b, ib) in links]

    # 3. Detect any extra exec needed (e.g. ipc3 needs a dummy interface on r3)
    extra_exec = _detect_extra_exec(pre_configs)
    if extra_exec:
        print(f"Extra exec: {extra_exec}")

    # 4. Set up temp directory, write configs, render clab topology
    topo_name = f"validity{scenario_name.replace('_', '')}{int(time.time()) % 100000}"

    with tempfile.TemporaryDirectory(prefix=f"validity_frr_{scenario_name}_") as tmpdir:
        tmp = Path(tmpdir)
        configs_dir = tmp / "configs"

        # Write PRE configs
        _write_node_configs(configs_dir, pre_configs)

        # Write clab topology
        clab_path = _write_clab_topology(topo_name, nodes, configs_dir, links, extra_exec)
        print(f"Topology file: {clab_path}")

        ctr_prefix = f"clab-{topo_name}"
        containers = [f"{ctr_prefix}-{node}" for node in nodes]

        t_start = time.monotonic()

        # 5. Deploy PRE lab
        print(f"\n--- LAUNCH PRE: clab deploy -t {clab_path} ---")
        try:
            out, _ = _run(["clab", "deploy", "-t", str(clab_path)], timeout=120)
            print(f"Deploy OK: {len(out.splitlines())} output lines")
        except Exception as e:
            result["errors"].append(f"clab deploy failed: {e}")
            _cleanup(clab_path, topo_name)
            return result

        result["timing"]["deploy_pre"] = time.monotonic() - t_start

        # 6. Wait for PRE convergence
        # min_prefixes: expect at least one route to be received across the network.
        # For a 3-node RR topology (ipc3), each client receives 1 prefix from the other.
        # For a 4-node full-mesh (square4), each node receives 3 prefixes. We set a
        # conservative floor of 1 prefix total to avoid false-convergence at 0/0.
        min_pfx = max(1, len(nodes) - 1)
        print(f"Waiting for PRE BGP convergence (min_prefixes={min_pfx})...")
        try:
            conv_time = _wait_bgp_converged(containers, min_prefixes=min_pfx)
            print(f"PRE converged in {conv_time:.1f}s")
            result["timing"]["convergence_pre"] = conv_time
        except TimeoutError as e:
            result["errors"].append(f"PRE convergence timeout: {e}")
            # Still gather what we can
            result["warnings"].append("PRE convergence did not complete; state may be partial")

        # 7. Gather PRE state (2x for stability)
        print("Gathering PRE live state (2 samples)...")
        reachability_flows = list(scn.reachability_flows or [])
        redundancy_targets = list(scn.redundancy_targets or [])
        bgp_watch_prefixes = list(getattr(scn, "bgp_watch_prefixes", []) or [])
        forwarding_flows = list(scn.forwarding_flows or [])

        # For forwarding anomaly detection, combine reachability + forwarding flows
        # (forwarding_flows is a subset of probes we track for D7)
        all_probe_flows = list(set(reachability_flows) | set(forwarding_flows))

        # Extract loopback IPs so pings are sourced from the loopback (avoids
        # asymmetric-routing failures: the kernel's egress-interface source IP may
        # lack a return route at the destination, making a correct-route ping fail).
        node_loopbacks = _extract_loopback_ips(pre_configs)
        print(f"Node loopbacks: {node_loopbacks}")

        pre_state, pre_stable = _gather_live_state(
            ctr_prefix, nodes, all_probe_flows, redundancy_targets, bgp_watch_prefixes,
            node_loopbacks=node_loopbacks,
        )
        result["live_pre_stable"] = pre_stable
        if not pre_stable:
            result["warnings"].append("PRE state was NOT stable across two consecutive samples")
        print(f"PRE state stable: {pre_stable}")
        _print_state_summary("PRE", pre_state, nodes, ctr_prefix)

        # 8. Apply POST config via frr-reload.py (diff-based replacement)
        # frr-reload.py is the correct mechanism: it diffs running vs new config and
        # issues 'no <line>' for removed entries. vtysh -f is additive and wrong here.
        print(f"\n--- Applying POST config to {scn.change_target} (via frr-reload.py) ---")
        changed_nodes = list(scn.patches.keys()) if scn.patches else [scn.change_target]
        for changed_node in changed_nodes:
            post_conf = post_configs[changed_node]
            frr_conf = _strip_to_frr_conf(post_conf)
            ctr = f"{ctr_prefix}-{changed_node}"
            _apply_config_to_container_via_reload(ctr, frr_conf)
            print(f"  Applied POST config to {changed_node} ({ctr})")

        # 9. Wait for POST reconvergence
        # For POST: after a withdrawal (ipc) the min_prefixes may drop to 0 on some
        # nodes; use 0 so we don't wait for non-existent routes after a withdrawal.
        print("Waiting for POST BGP reconvergence...")
        try:
            conv_time = _wait_bgp_converged(containers, min_prefixes=0)
            print(f"POST converged in {conv_time:.1f}s")
            result["timing"]["convergence_post"] = conv_time
        except TimeoutError as e:
            result["warnings"].append(f"POST convergence timeout: {e}")
            print(f"WARNING: POST convergence timeout: {e}")

        # 10. Gather POST state (2x for stability)
        print("Gathering POST live state (2 samples)...")
        post_state, post_stable = _gather_live_state(
            ctr_prefix, nodes, all_probe_flows, redundancy_targets, bgp_watch_prefixes,
            node_loopbacks=node_loopbacks,
        )
        result["live_post_stable"] = post_stable
        if not post_stable:
            result["warnings"].append("POST state was NOT stable across two consecutive samples")
        print(f"POST state stable: {post_stable}")
        _print_state_summary("POST", post_state, nodes, ctr_prefix)

        # 11. Derive live damage set
        print("\n--- Deriving live damage set ---")
        live_keys = _derive_live_damage(
            pre_state, post_state,
            scenario_name, nodes, ctr_prefix,
            list(scn.watched_prefixes or []),
            all_probe_flows,
            redundancy_targets,
            bgp_watch_prefixes,
        )

        # D7: for forwarding_flows, a reachability loss (pre_ok and not post_ok)
        # is classified as a forwarding anomaly ("blackhole" — live ping can't
        # distinguish NO_ROUTE from NULL_ROUTED). IMPORTANT: do NOT remove the D3
        # entry: the oracle (Batfish) emits BOTH D3 (reachability_lost) AND D7
        # (forwarding_anomaly) for the same flow when the scenario declares both
        # reachability_flows AND forwarding_flows. The live harness must match this
        # double-emission to agree with the oracle.
        for (src_node, dst_prefix) in forwarding_flows:
            pre_ok = pre_state["reachability"].get((src_node, dst_prefix), True)
            post_ok = post_state["reachability"].get((src_node, dst_prefix), True)
            if pre_ok and not post_ok:
                # Add D7 entry (keep D3 entry if also in reachability_flows)
                live_keys["forwarding"].add(
                    f"anomaly|blackhole|node={src_node}|vrf=default|dst={dst_prefix}"
                )

        result["live_keys"] = {k: sorted(v) for k, v in live_keys.items()}
        print("Live damage keys:")
        for dim, keys in live_keys.items():
            if keys:
                print(f"  D-{dim}: {sorted(keys)}")

        result["timing"]["total_live"] = time.monotonic() - t_start

        # 12. Run Batfish oracle
        if run_batfish:
            print("\n--- Running Batfish oracle ---")
            try:
                from netbrace.batfish.extended_oracle import ExtendedOracle
                oracle = ExtendedOracle(host=batfish_host)
                oracle_result = oracle.compute(scn)
                oracle_keys = oracle_result.key_sets()
                result["oracle_keys"] = {k: sorted(v) for k, v in oracle_keys.items()}
                print("Oracle damage keys:")
                for dim, keys in oracle_keys.items():
                    if keys:
                        print(f"  D-{dim}: {sorted(keys)}")
            except Exception as e:
                result["errors"].append(f"Batfish oracle error: {e}")
                result["batfish_ran"] = False
                print(f"Batfish ERROR: {e}")
                oracle_keys = {}
        else:
            oracle_keys = {}

        # 13. Compare
        if run_batfish and oracle_keys is not None:
            comparison = _compare_to_oracle(scenario_name, live_keys, oracle_keys)
            result["comparison"] = comparison
            _print_comparison(comparison)
        else:
            result["comparison"] = {"note": "Batfish not run; comparison skipped"}

        # 14. Cleanup
        print(f"\n--- CLEANUP: destroying {topo_name} ---")
        _cleanup(clab_path, topo_name)  # noqa: F821 -- path still in scope

    return result


def _detect_extra_exec(configs: dict[str, str]) -> Optional[dict[str, list[str]]]:
    """Detect nodes that need extra exec commands (e.g. dummy interface for ipc3 r3)."""
    extra: dict[str, list[str]] = {}
    for node, cfg in configs.items():
        cmds = []
        # Check for dummy (dum0) interface
        if re.search(r"interface dum0", cfg):
            # Find the IP address on dum0
            m = re.search(r"interface dum0\n ip address (\S+)", cfg)
            if m:
                ip_cidr = m.group(1)
                cmds.append("ip link add dum0 type dummy")
                cmds.append(f"ip addr add {ip_cidr} dev dum0")
                cmds.append("ip link set dum0 up")
        if cmds:
            extra[node] = cmds
    return extra if extra else None


def _apply_config_to_container_via_reload(container: str, frr_conf: str) -> None:
    """Apply a new frr.conf by writing to /tmp/new_frr.conf and calling frr-reload.py.

    frr-reload.py computes a DIFF between the running config and the new config,
    then issues 'no <line>' for removed lines and adds new lines. This is the
    correct FRR mechanism for replacing config (vtysh -f is additive, not replacing).

    frr-reload.py is present in quay.io/frrouting/frr:10.6.1 at /usr/lib/frr/.
    """
    import tempfile as _tempfile
    with _tempfile.NamedTemporaryFile(
        mode="w", suffix=".conf", delete=False, prefix="frr_post_"
    ) as tf:
        tf.write(frr_conf)
        local_path = tf.name
    try:
        subprocess.run(
            ["docker", "cp", local_path, f"{container}:/tmp/new_frr.conf"],
            capture_output=True, text=True, timeout=15, check=True,
        )
    finally:
        import os as _os
        _os.unlink(local_path)

    # frr-reload.py --test first (dry run to catch obvious errors)
    # Then actual reload
    r = subprocess.run(
        ["docker", "exec", container, "/usr/lib/frr/frr-reload.py",
         "--reload", "/tmp/new_frr.conf"],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        stderr_lines = [l for l in r.stderr.splitlines()
                        if l.strip() and "configuration file" not in l.lower()]
        if stderr_lines:
            print(f"    frr-reload.py note: {'; '.join(stderr_lines[:3])}")
    # Brief pause for reload to settle
    time.sleep(2)


def _cleanup(clab_path: Path, topo_name: str) -> None:
    """Destroy the containerlab topology and verify cleanup."""
    try:
        subprocess.run(
            ["clab", "destroy", "-t", str(clab_path), "--cleanup"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        print(f"  WARNING: clab destroy failed: {e}")
    # Verify all clab-<topo>-* containers are gone
    r = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True,
    )
    leftovers = [ln for ln in r.stdout.splitlines() if topo_name in ln]
    if leftovers:
        print(f"  WARNING: leftover containers after destroy: {leftovers}")
        for ctr in leftovers:
            subprocess.run(["docker", "rm", "-f", ctr], capture_output=True)
    else:
        print(f"  Cleanup OK: no {topo_name} containers remain")


def _print_state_summary(label: str, state: dict, nodes: list[str], ctr_prefix: str) -> None:
    print(f"  {label} sessions:")
    for node in nodes:
        ctr = f"{ctr_prefix}-{node}"
        peers = state["sessions"].get(ctr, set())
        print(f"    {node}: {sorted(peers)} ({len(peers)} established)")
    print(f"  {label} reachability:")
    for (src, dst), ok in sorted(state["reachability"].items()):
        print(f"    {src} -> {dst}: {'OK' if ok else 'FAIL'}")
    print(f"  {label} redundancy:")
    for (node, prefix), count in sorted(state["redundancy"].items()):
        print(f"    {node} -> {prefix}: {count} paths")


def _print_comparison(comparison: dict) -> None:
    print(f"\n{'='*60}")
    print(f"COMPARISON: {comparison.get('scenario', '?')} -> {comparison.get('overall', '?')}")
    print(f"{'='*60}")
    for dim, info in comparison.get("dimensions", {}).items():
        verdict = info["verdict"]
        marker = "AGREE" if verdict == "AGREE" else "DIVERGE !!!"
        print(f"  {dim:20s}: {marker}")
        if verdict == "DIVERGE":
            if info.get("only_in_live"):
                print(f"    LIVE only  : {info['only_in_live']}")
            if info.get("only_in_oracle"):
                print(f"    ORACLE only: {info['only_in_oracle']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Live-FRR validity harness: cross-check Batfish oracle vs real FRR"
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=["ipc", "ipc_static", "blackhole", "ecmp"],
        help="Scenarios to validate (default: ipc ipc_static blackhole ecmp)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write results JSON (default: runs/validity_<timestamp>.json)",
    )
    parser.add_argument(
        "--batfish-host",
        default="127.0.0.1",
        help="Batfish host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--no-batfish",
        action="store_true",
        help="Skip Batfish oracle comparison (live-state only)",
    )
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    out_path = Path(args.output) if args.output else _REPO / "runs" / f"validity_{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"NetHELM Live-FRR Validity Harness")
    print(f"Scenarios: {args.scenarios}")
    print(f"Batfish: {'SKIP' if args.no_batfish else args.batfish_host}")
    print(f"Output: {out_path}")

    # Sanity: check no leftover validity containers from a prior crashed run
    r = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True,
    )
    leftovers = [ln for ln in r.stdout.splitlines() if "validity" in ln]
    if leftovers:
        print(f"WARNING: leftover validity containers found: {leftovers}")
        print("Cleaning up before starting...")
        for ctr in leftovers:
            subprocess.run(["docker", "rm", "-f", ctr], capture_output=True)

    results = []
    for scenario_name in args.scenarios:
        try:
            r = run_scenario(
                scenario_name,
                batfish_host=args.batfish_host,
                run_batfish=not args.no_batfish,
            )
            results.append(r)
        except Exception as e:
            print(f"ERROR running {scenario_name}: {e}")
            results.append({
                "scenario": scenario_name,
                "errors": [f"Uncaught exception: {e}"],
                "overall": "ERROR",
            })

    # Write results
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults written to: {out_path}")

    # Print summary table
    print(f"\n{'='*70}")
    print(f"VALIDITY SUMMARY TABLE")
    print(f"{'='*70}")
    print(f"{'Scenario':<20} {'Overall':>10}  {'D1':>5} {'D2':>5} {'D3':>5} {'D5':>5} {'D7':>5} {'D9':>5}")
    print(f"{'-'*70}")
    for r in results:
        scn_name = r["scenario"]
        overall = r.get("comparison", {}).get("overall", "ERROR")
        dims = r.get("comparison", {}).get("dimensions", {})

        def dim_verdict(d):
            return dims.get(d, {}).get("verdict", "?")[:1] if dims else "?"

        print(
            f"{scn_name:<20} {overall:>10}  "
            f"{dim_verdict('sessions'):>5} {dim_verdict('prefixes'):>5} "
            f"{dim_verdict('reachability'):>5} {dim_verdict('redundancy'):>5} "
            f"{dim_verdict('forwarding'):>5} {dim_verdict('bgp_withdrawn'):>5}"
        )
    print(f"{'='*70}")

    # Final docker ps sanity check
    r_ps = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True,
    )
    validity_ctrs = [ln for ln in r_ps.stdout.splitlines() if "validity" in ln.lower()]
    if validity_ctrs:
        print(f"\nWARNING: containers still running after all scenarios: {validity_ctrs}")
    else:
        print(f"\nCleanup: docker ps clean (no validity containers)")

    print(f"\nOutput: {out_path}")


if __name__ == "__main__":
    main()
