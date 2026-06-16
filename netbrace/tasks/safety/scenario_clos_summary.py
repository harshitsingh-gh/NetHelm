"""clos_summary — DC underlay route-summarization blackhole (RFC 7938 hazard).

The DC-fabric class: an operator "optimizes the FIB" by summarizing the underlay
on the spines — a habit imported from enterprise/WAN design — and creates a
blackhole, the exact hazard RFC 7938 §3.2.2/§5.2.3 warns summarization causes in a
Clos ("Summarizing subnets in a Clos topology results in route black-holing ... and
hence must be avoided").

MECHANISM-FAITHFULNESS NOTE (be precise; do not overclaim): RFC 7938 §5.2.3 frames
the canonical case as summarization + a *single link failure* on a healthy
symmetric fabric. THIS scenario instead models the §3.2.2 "exactly one path per
Tier-1 to each server" property as a **fixed asymmetry** (spine2 has no direct path
to leaf3) that the summary then **masks** — i.e. it is a *fixed-asymmetry instance*
of the same summarization hazard, NOT the dynamic link-failure trigger. Both are
real; the labels differ. The proper §5.2.3 link-failure version (symmetric Clos +
`fork_snapshot(deactivate_interfaces=...)` post-change) is the queued upgrade
(see paper/refs/fight_synthesis_2026-06-08.md). Do not cite §5.2.3's "link failure"
language as if this scenario implements it.

Reuses the verified `clos_summary` eBGP baseline (2 spines, 3 leaves, per-device
ASN). The baseline's FIXED asymmetry is that spine2 has no DIRECT link to leaf3
(the server's leaf). In the baseline the spines advertise the SPECIFIC /24, so
leaf1/leaf2 reach 10.3.0.1 via spine1 (their best, direct path) — DELIVERED.
Spine2 DOES learn the /24 in the baseline, but only INDIRECTLY (leaf1/leaf2
re-advertise it up to spine2); that indirect path is what the change severs.

The change (a fabric-wide "summarize the underlay" template applied to BOTH
spines):
  1. each spine ORIGINATES the covering summary 10.0.0.0/8 (a `network 10.0.0.0/8`
     backed by an `ip route 10.0.0.0/8 blackhole` discard static — the standard way
     to source an aggregate that always stays up);
  2. each spine SUPPRESSES the specific 10.3.0.0/24 toward its leaves (an outbound
     prefix-list SUMMARIZE_OUT that denies the /24 and permits everything else) —
     i.e. it advertises the summary INSTEAD of the specific. This is the
     "summarize subnets toward the leaves" optimization.

Causal chain (the model must DERIVE this from the diff + configs):
  1. After the change, leaf1 and leaf2 no longer hear the specific 10.3.0.0/24
     from either spine — only the summary 10.0.0.0/8, now advertised by spine1 AND
     spine2. Because the leaves no longer carry the /24, they stop re-advertising it
     up to spine2, so spine2 LOSES its only (indirect) path to leaf3 and falls back
     to sourcing the /8 from its own discard static — regardless of having any real
     path to the server.
  2. The two /8 advertisements arrive with different AS_PATHs (via spine1 vs
     spine2); `multipath-relax` + `maximum-paths 2` make them ECMP. leaf1/leaf2
     install BOTH next-hops for 10.0.0.0/8.
  3. For a packet to the server host 10.3.0.1, longest-prefix-match now resolves to
     the /8 (the specific is gone), so it ECMPs across spine1 and spine2:
        - via spine1: spine1 still has the real specific to leaf3 -> DELIVERED.
        - via spine2: spine2's indirect /24 (via the leaves) is now gone, leaving
          only its `10.0.0.0/8 -> discard` -> the packet is DROPPED (NULL_ROUTED)
          at spine2.
  4. So the ECMP path via spine2 blackholes while the path via spine1 delivers —
     partial loss, with the summary still present-and-best in every RIB. (D7 scores
     the single network-level fact "spine2 blackholes 10.3.0.1"; leaf1 and leaf2
     are independent WITNESSES of that same anomaly, not two separate blackholes.)
     Partial packet loss with green dashboards — the hardest signature to diagnose.

Thesis property (the "looks safe and isn't" trap), to confirm via the oracle:
  * D1 sessions_lost = ∅        (no session changes — eBGP stays ESTABLISHED)
  * D2 prefixes_lost: the SPECIFIC 10.3.0.0/24 leaves leaf1/leaf2 RIBs, but the
    covering /8 is ADDED and present-and-best, so a naive "is the destination
    covered?" check LIES (the server space still looks reachable).
  * D7 forwarding_anomalies != ∅  (a blackhole trace from leaf1/leaf2 -> 10.3.0.1
    exists, dropped NULL_ROUTED at spine2 — the SET-level invariant we score, NOT
    the per-flow ECMP hash)
  * D3 reachability_lost: scored at SET level — only fires for a flow if EVERY
    trace fails; under ECMP one trace still succeeds via spine1, so D3 may stay ∅
    while D7 fires. That asymmetry (D3 quiet, D7 loud) is the whole point: total-
    loss checks miss it; the blackhole is real and partial.

Negative controls (must NOT fire):
  * leaf3 itself serves 10.3.0.1 connected -> never pulled toward a spine.
  * loopbacks (172.16.x) are OUTSIDE the /8 summary -> unaffected by it.

Determinism (docs/oracle_determinism_spec_v1.md): scored as the data-plane SET via
traceroute disposition ("a blackhole trace EXISTS"), never the chosen ECMP path /
per-flow hash. Router-ids pinned to loopbacks; the discard static and prefix-list
are filtering-deterministic; the summary is sourced unconditionally so no live
timing affects whether it exists. STATIC-DETERMINISTIC, verify >=2x byte-identical.

Grounding: RFC 7938 §5.2.3 (verbatim) + §3.2.2 (one-path property); RFC 7938 §6.2
(multipath-relax for differing-AS ECMP); knowledge/corpus/dc/
dc_summarization_ecmp_pitfalls.md Part A; ipSpace "Avoid summarization in
leaf-and-spine"; hyperscaler_dc_failure_modes.md row 4 (RFC 7938 §5.2.3, "HIGH,
2-snap").
"""

from __future__ import annotations

import difflib

from netbrace.tasks.safety import baseline_clos_summary as base
from netbrace.topology.patches import apply_unified_diff

CHANGE_TARGET = base.CHANGE_TARGET  # "spine2" (the spine that blackholes)

SERVER_PREFIX = base.SERVER_PREFIX
SERVER_IP = base.SERVER_IP
SUMMARY_PREFIX = base.SUMMARY_PREFIX

WATCHED_PREFIXES = list(base.WATCHED_PREFIXES)

# The two remote leaves toward the server host. Both are ECMP-capable (peer both
# spines), so post-change each ECMPs the /8 and a SUBSET of traffic blackholes at
# spine2. leaf3 (serves it connected) is the negative-control source.
SERVER_HOST = base.SERVER_IP + "/32"  # 10.3.0.1/32
FORWARDING_FLOWS = [
    ("leaf1", SERVER_HOST),   # ECMPs /8 post-change: spine1 OK, spine2 blackholes
    ("leaf2", SERVER_HOST),   # same — the other remote leaf
    ("leaf3", SERVER_HOST),   # neg control: leaf3 serves the host connected
]
REACHABILITY_FLOWS = list(FORWARDING_FLOWS)

# The spines that get the fabric-wide "summarize the underlay" template.
_SUMMARY_SPINES = ["spine1", "spine2"]

# Discard static that always keeps the summary up (sourced regardless of any real
# path) — inserted just before the `router bgp` block.
_DISCARD_STATIC = "ip route 10.0.0.0/8 blackhole\n"
_DISCARD_ANCHOR = "!\nrouter bgp "

# `network 10.0.0.0/8` to originate the summary into BGP (added in the AF).
_NETWORK_LINE = "  network 10.0.0.0/8\n"
_NETWORK_ANCHOR_PREFIX = "  maximum-paths 2\n"

# Outbound prefix-list + route-map that advertises the summary INSTEAD of the
# specific toward the leaves: deny the /24 specific, permit everything else. The
# route-map is attached to every eBGP neighbor on the spine (leaf-facing). Block
# inserted at the end of the `router bgp` block, before the closing `!`.
_PFXLIST_BLOCK = (
    "!\n"
    "ip prefix-list SUMMARIZE_OUT seq 5 deny 10.3.0.0/24\n"
    "ip prefix-list SUMMARIZE_OUT seq 10 permit 0.0.0.0/0 le 32\n"
    "!\n"
    "route-map SUMMARIZE_OUT permit 10\n"
    " match ip address prefix-list SUMMARIZE_OUT\n"
)


def baseline_configs() -> dict[str, str]:
    """The (frozen) clos_summary baseline — reused verbatim."""
    return base.baseline_configs()


def _neighbor_ips(spine_cfg: str) -> list[str]:
    """The eBGP neighbor IPs declared on a spine (leaf-facing), in file order."""
    out: list[str] = []
    for ln in spine_cfg.splitlines():
        s = ln.strip()
        if s.startswith("neighbor ") and " remote-as " in s:
            out.append(s.split()[1])
    return out


def _post_spine_config(spine: str) -> str:
    """One spine with the summarize-the-underlay template applied."""
    before = base.baseline_configs()[spine]
    if _DISCARD_ANCHOR not in before or _NETWORK_ANCHOR_PREFIX not in before:
        raise RuntimeError(f"clos_summary baseline {spine} changed; re-verify anchors")

    # 1) discard static (originator-keeps-it-up) before the router block.
    after = before.replace(_DISCARD_ANCHOR, _DISCARD_STATIC + _DISCARD_ANCHOR, 1)

    # 2) originate the /8 summary in the AF.
    after = after.replace(_NETWORK_ANCHOR_PREFIX, _NETWORK_LINE + _NETWORK_ANCHOR_PREFIX, 1)

    # 3) attach the outbound SUMMARIZE_OUT route-map to every eBGP neighbor so the
    #    specific /24 is suppressed and only the summary is advertised to leaves.
    for ip in _neighbor_ips(before):
        nbr_line = f" neighbor {ip} remote-as"
        # add an `out` route-map line right after the neighbor's remote-as line.
        anchor = None
        for ln in after.splitlines():
            if ln.startswith(nbr_line):
                anchor = ln
                break
        if anchor is None:
            raise RuntimeError(f"could not anchor route-map on {spine} nbr {ip}")
        rm_line = f" neighbor {ip} route-map SUMMARIZE_OUT out"
        after = after.replace(anchor + "\n", anchor + "\n" + rm_line + "\n", 1)

    # 4) define the prefix-list + route-map (at the end of the bgp block).
    after = after.replace("!\nline vty\n", _PFXLIST_BLOCK + "!\nline vty\n", 1)
    return after


def _per_node_patch(spine: str) -> str:
    before = base.baseline_configs()[spine]
    after = _post_spine_config(spine)
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile=f"{spine}.conf", tofile=f"{spine}.conf", lineterm="",
    )
    patch = "\n".join(diff) + "\n"
    if apply_unified_diff(before, patch) != after:
        raise RuntimeError(f"clos_summary {spine} patch does not round-trip")
    return patch


def patches() -> dict[str, str]:
    """Per-node {spine: unified_diff} for the fabric-wide summarization template."""
    return {spine: _per_node_patch(spine) for spine in _SUMMARY_SPINES}


def change_patch() -> str:
    """Combined human-readable diff (all summarized spines) shown to the model."""
    return "".join(_per_node_patch(spine) for spine in _SUMMARY_SPINES)
