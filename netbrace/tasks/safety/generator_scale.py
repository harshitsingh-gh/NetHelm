"""Class-8 generator — SCALE / DE-AGGREGATION-OVERFLOW (D8 FIB/RIB pressure).

This is the parameterized generator for the ``scale_deagg`` MECHANISM (audit fix
K3, paper/refs/audit_2026-06-10_publication_safety.md §2 K3 + §5): the templated
split currently covers only ONE mechanism (the policy-withdrawal M1 class); this
adds structurally-varied, contamination-controlled HELD-OUT variants for the
de-aggregation / table-flood class so the per-dimension statistics, the modal
floor, and the contamination story all stop resting on n=1.

It turns the verified ``scale_deagg`` mechanism (an upstream de-aggregates a
covering supernet into its constituent /24 more-specifics, flooding the downstream
edge past its annotated FIB budget — the Rogers Jul-2022 re-cast) into DISTINCT,
oracle-gradeable instances over axes that change the GROUND-TRUTH STRUCTURE or the
required reasoning, with per-seed randomized ASN / addressing / node-names /
supernet as the CONTAMINATION CONTROL (the mechanism is public; each emitted
instance is novel even for a famous incident).

Relationship to the hand-authored instance (scenario_scale_deagg): that is the
GROUNDED, incident-anchored template this generator is parameterized FROM.
Generated instances set ``provenance="templated"`` (the PRIMARY decontaminated
split); the hand-authored one keeps ``"handauthored"`` (the GROUNDED split). The
mechanism is identical and verified; the generator's value is DIVERSITY of blast
STRUCTURE + difficulty + novel numbering, not new mechanisms.

Structural axes (each genuinely changes GT structure or the required reasoning):

  * margin ∈ {over_clear, over_marginal, under} — drives whether D8 fires and how
    hard the model must COUNT:
      - ``over_clear``    — the specifics count comfortably exceeds the edge's
        annotated FIB budget. D8 FIRES with a comfortable margin (the easy case).
      - ``over_marginal`` — the post count exceeds the budget by EXACTLY 1. D8 still
        FIRES — but the model must COUNT precisely, not pattern-match: vibing
        "de-agg => overflow" is right here only by luck, and a model that
        miscounts by one gets it wrong.
      - ``under``         — the post count stays BELOW the budget. D8 does NOT fire.
        This is the CALIBRATION TRAP for models that pattern-match
        "de-aggregation => overflow": the change IS a de-aggregation (the specifics
        genuinely appear, it is not a no-op), but the count does not cross the
        stated budget, so the honest answer is "no D8 violation". A model that
        flags overflow here HALLUCINATES damage (FSA on the scale axis).
    The per-seed budget AND the specifics count are derived JOINTLY so the margin
    class holds, and the ABSOLUTE numbers are randomized per seed. The budget is a
    STATED annotation in the prompt (per the existing scenario's honest framing);
    the specifics COUNT is NEVER in prose — the model counts the /24s from the diff.

  * supernet_fate ∈ {withdrawn, kept} — drives the D2 loss signal (a DIFFERENT GT
    structure), the honest watch-set per the red-team fix:
      - ``withdrawn`` — the upstream DROPS the supernet while originating the
        specifics (the classic de-agg: summary -> constituents). The supernet row
        truly leaves both RIBs, so D2 FIRES on the watched supernet — the benign
        supernet->specifics SWAP. The model that reports "the /16 was withdrawn" is
        RIGHT (honest watch-set), not penalised.
      - ``kept``      — the upstream KEEPS advertising the supernet ALONGSIDE the
        new specifics (a "leak the specifics but keep the cover" change). The
        supernet never leaves any RIB, so D2 = ∅ — a PURE D8 signal with NO loss
        view at all, the hardest version of the trap (nothing in any
        loss/connectivity view moves, only the table grows). Different GT structure
        from ``withdrawn``.

That's 3 (margin) × 2 (supernet_fate) = 6 structural combos × seeds.

Watch-set honesty (re-read the 'D2 watch-set gerrymander' red-team finding,
progress.md Day 20): the watch set is the loopbacks (negative controls) + the
supernet + a SAMPLE of the specifics (the first, a middle, and the last /24). No
gerrymandering — we watch the supernet so its withdrawal is HONESTLY scored, and we
watch real specifics (which are ADDED, never lost, so they stay out of D2) so the
watch set is not curated to manufacture a particular D2 answer. The specifics being
ADDED (not lost) is structural: D2 reflects only the supernet, exactly per its
fate.

Proxy honesty (mirrors scenario_scale_deagg, do not weaken): the FIB budget is a
'spec budget' annotation, LAB-SCALED, never claimed as a silicon ceiling; the
route-count proxy is the main-RIB row count (single-VRF), valid for fib/rib ONLY
(see ExtendedOracle._scale_violations / _ROUTE_COUNT_RESOURCES). The oracle scores
the count-vs-budget THRESHOLD, never which route a TCAM evicts. Only the edge
carries a budget (it is the overflow victim); the upstream is unconstrained.

Determinism contract (oracle_determinism_spec_v1.md, class 8 = STATIC-DET): a
two-node chain with a single origin per prefix and no ECMP tie; router-ids pinned
to the (randomized but fixed-per-seed) loopbacks; each de-aggregated prefix backed
by its own discard (blackhole) static so BGP can source it regardless of timing.
The installed-route COUNT on a pinned snapshot is independent of any per-flow hash,
so it is byte-identical across runs. Each emitted Scenario round-trips and is
gradeable by ExtendedOracle.compute unchanged.
"""

from __future__ import annotations

import difflib
import random
from dataclasses import dataclass
from typing import Optional

from netbrace.tasks.safety.scenarios import Scenario
from netbrace.topology.patches import apply_unified_diff

# --------------------------------------------------------------------------- #
# Axis value sets (the enumerable space).
# --------------------------------------------------------------------------- #
MARGIN_VALUES = ("over_clear", "over_marginal", "under")
SUPERNET_FATE_VALUES = ("withdrawn", "kept")

AXES = {
    "margin": MARGIN_VALUES,
    "supernet_fate": SUPERNET_FATE_VALUES,
}

# The edge's FIXED installed-route count (the routes that exist REGARDLESS of how
# many block specifics it learns): its own loopback /32, the connected /30 link
# net, and the local /32 on that link. Verified live on the scale_deagg baseline
# (BASELINE_EDGE_COUNT=4 = 3 fixed + 1 /16 block route). Pinned here so the
# margin arithmetic is auditable from source; re-confirmed live in the verify
# harness / oracle round-trip.
_EDGE_FIXED_ROUTES = 3

# How many /24 specifics each margin class targets ON THE EDGE'S COUNT side. The
# edge POST installed-route count is:
#     _EDGE_FIXED_ROUTES + n_specifics + (1 if supernet kept else 0)
# We pick the budget per seed and then derive n_specifics so the margin holds. The
# absolute numbers are randomized per seed (see _draw_params); these are the bands
# the derivation must land in. Kept deliberately small so the flood is observable
# in a 2-node lab (lab-scaled, disclosed proxy).
_SPECIFIC_MIN, _SPECIFIC_MAX = 8, 64  # constituent-/24 count range across seeds


@dataclass(frozen=True)
class ScaleSpec:
    """A point in the Class-8 generator space (the axis tuple, pre-randomization)."""

    margin: str
    supernet_fate: str

    def dims_label(self) -> str:
        return f"{self.margin}-{self.supernet_fate}"


def enumerate_specs() -> list[ScaleSpec]:
    """All axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[ScaleSpec] = []
    for margin in MARGIN_VALUES:
        for fate in SUPERNET_FATE_VALUES:
            out.append(ScaleSpec(margin, fate))
    return out


def enumerable_count() -> int:
    """Number of distinct axis combinations (each ×∞ randomized seeds)."""
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996): 4200000000-4294967294. We keep clear of the
# hand-authored 65010/65020 family so a generated instance never collides with it,
# and use DISTINCT upstream/edge ASNs (this is eBGP).
_ASN_LO, _ASN_HI = 4_200_000_000, 4_200_099_999

# Node base-name pools (string only; topology role is unchanged).
_NAME_POOLS = ["upstream", "core", "transit", "provider", "agg", "border"]
_EDGE_NAME_POOLS = ["edge", "cust", "downstream", "access", "leaf", "spoke"]

# Supernet pools. We de-aggregate a /16 into constituent /24s, so the supernet is
# always a /16 drawn from documentation / RFC-1918 / RFC-6598 customer space (a
# safe, non-routable block). Each is a /16 base "A.B" (the third+fourth octets are
# carved as 100.B.i.0/24 specifics). We render the second octet per seed too.
_SUPERNET_POOLS = [
    ("100.64", "RFC6598 CGN shared (carrier customer space)"),
    ("100.{b}", "RFC6598 CGN shared (carrier customer space)"),
    ("10.{b}", "RFC1918 private (enterprise customer space)"),
    ("172.{b16}", "RFC1918 private (enterprise customer space)"),
]

# Loopback /24 pools (each instance carves /32s from ONE /24, disjoint from the
# supernet pools above so loopbacks never collide with the de-aggregated block).
_LOOPBACK_POOLS = ["10.255.{c}", "192.168.{c}"]

# eBGP /30 link supernet pools (the directly-connected session rides this).
_LINK_POOLS = [(198, 51, 100), (203, 0, 113), (192, 0, 2)]  # TEST-NET-2/-3/-1


@dataclass(frozen=True)
class _Params:
    """The randomized-but-fixed-per-seed concrete values for one instance."""

    upstream_asn: int
    edge_asn: int
    up_name: str
    edge_name: str
    loop_block: str          # e.g. "10.255.37" -> loopbacks 10.255.37.N/32
    link_block: tuple[int, int, int]  # first three octets of the /30 link
    supernet_b: str          # the /16 base "A.B" e.g. "100.64" / "10.42"
    budget: int              # the edge FIB budget (stated annotation)
    n_specifics: int         # number of /24 constituents (derived for the margin)


def _draw_params(spec: ScaleSpec, seed: int) -> _Params:
    rng = random.Random(seed)
    upstream_asn = rng.randint(_ASN_LO, _ASN_HI)
    # distinct edge ASN (eBGP) — re-draw until different.
    edge_asn = rng.randint(_ASN_LO, _ASN_HI)
    while edge_asn == upstream_asn:
        edge_asn = rng.randint(_ASN_LO, _ASN_HI)

    up_name = rng.choice(_NAME_POOLS)
    edge_name = rng.choice(_EDGE_NAME_POOLS)
    while edge_name == up_name:
        edge_name = rng.choice(_EDGE_NAME_POOLS)

    loop_block = rng.choice(_LOOPBACK_POOLS).format(c=rng.randint(0, 250))
    link_block = rng.choice(_LINK_POOLS)

    # supernet /16 base; render any {b}/{b16} placeholder (avoid octet 0/255).
    sup = rng.choice(_SUPERNET_POOLS)[0]
    supernet_b = sup.format(b=rng.randint(1, 254), b16=rng.randint(16, 31))

    # ---- joint budget + specifics-count derivation (the margin discriminator) --
    # POST edge count = _EDGE_FIXED_ROUTES + n_specifics + kept_extra, where
    # kept_extra = 1 iff the supernet is KEPT (still learned alongside the
    # specifics). We pick n_specifics randomly in band, then SET the budget so the
    # margin class holds exactly. Both numbers thus vary per seed AND the absolute
    # budget is never derivable from the margin class alone.
    kept_extra = 1 if spec.supernet_fate == "kept" else 0
    n_specifics = rng.randint(_SPECIFIC_MIN, _SPECIFIC_MAX)
    post_count = _EDGE_FIXED_ROUTES + n_specifics + kept_extra

    if spec.margin == "over_clear":
        # budget comfortably below the post count: a margin of >=3 routes.
        slack = rng.randint(3, max(3, n_specifics // 2))
        budget = post_count - slack
    elif spec.margin == "over_marginal":
        # post count exceeds the budget by EXACTLY 1 (budget = post_count - 1).
        budget = post_count - 1
    else:  # "under": post count stays strictly below the budget.
        # budget comfortably above the post count, but the BASELINE (pre) count
        # must ALSO be under it (it always is: baseline <= post). Margin >=2.
        head = rng.randint(2, 6)
        budget = post_count + head

    # Floor the budget above the baseline pre-count so the change is the only thing
    # that could (in the over cases) cross it — never a baseline that already
    # overflows. Pre count = _EDGE_FIXED_ROUTES + 1 (it learns the single supernet
    # in the baseline). Keep budget strictly above that.
    pre_count = _EDGE_FIXED_ROUTES + 1
    if budget <= pre_count:
        budget = pre_count + 1  # defensive; only reachable for tiny n_specifics

    return _Params(
        upstream_asn=upstream_asn, edge_asn=edge_asn, up_name=up_name,
        edge_name=edge_name, loop_block=loop_block, link_block=link_block,
        supernet_b=supernet_b, budget=budget, n_specifics=n_specifics,
    )


# --------------------------------------------------------------------------- #
# Topology + derived addressing.
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    params: _Params
    spec: ScaleSpec
    upstream: str
    edge: str
    up_loop: str             # "x.y.z.1"
    edge_loop: str           # "x.y.z.2"
    up_link_ip: str          # "a.b.c.1"
    edge_link_ip: str        # "a.b.c.2"
    supernet: str            # "<A.B>.0.0/16"
    specifics: list[str]     # ["<A.B>.0.0/24", ...] length n_specifics


def _build_topo(spec: ScaleSpec, params: _Params) -> _Topo:
    up_loop = f"{params.loop_block}.1"
    edge_loop = f"{params.loop_block}.2"
    b, c, d = params.link_block
    up_link_ip = f"{b}.{c}.{d}.1"
    edge_link_ip = f"{b}.{c}.{d}.2"
    supernet = f"{params.supernet_b}.0.0/16"
    specifics = [f"{params.supernet_b}.{i}.0/24" for i in range(params.n_specifics)]
    return _Topo(
        params=params, spec=spec, upstream=params.up_name, edge=params.edge_name,
        up_loop=up_loop, edge_loop=edge_loop, up_link_ip=up_link_ip,
        edge_link_ip=edge_link_ip, supernet=supernet, specifics=specifics,
    )


# --------------------------------------------------------------------------- #
# Config text rendering (FRR / CUMULUS_CONCATENATED, the verified baseline format).
# Mirrors baseline_scale_deagg's exact text shape so it parses identically.
# --------------------------------------------------------------------------- #
def _node_config(topo: _Topo, node: str, *, networks: list[str],
                 statics: list[str]) -> str:
    """Render one FRR node (the eBGP pair shares this shape).

    ``networks`` are the BGP ``network`` originations (beyond the node's own
    loopback) and ``statics`` are the backing discard statics (one per originated
    block prefix) so BGP can source each route.
    """
    p = topo.params
    is_up = node == topo.upstream
    loop = topo.up_loop if is_up else topo.edge_loop
    link_ip = topo.up_link_ip if is_up else topo.edge_link_ip
    asn = p.upstream_asn if is_up else p.edge_asn
    peer_ip = topo.edge_link_ip if is_up else topo.up_link_ip
    peer_asn = p.edge_asn if is_up else p.upstream_asn

    lines: list[str] = [
        node, "",
        "# This file describes the network interfaces",
        "auto lo", "iface lo inet loopback", f"    address {loop}/32", "",
        "auto eth1", "iface eth1 inet static", f"    address {link_ip}/30", "",
        "# ports.conf --", "",
        "frr version 10.6.1", "frr defaults traditional", f"hostname {node}",
        "service integrated-vtysh-config", "!", "ip forwarding", "!",
    ]
    for s in statics:
        lines.append(s)
    if statics:
        lines.append("!")
    lines += [
        "interface lo", f" ip address {loop}/32", "!",
        "interface eth1", f" ip address {link_ip}/30", "!",
        f"router bgp {asn}", f" bgp router-id {loop}",
        f" neighbor {peer_ip} remote-as {peer_asn}", " !",
        " address-family ipv4 unicast", f"  network {loop}/32",
    ]
    for net in networks:
        lines.append(f"  network {net}")
    lines += [" exit-address-family", "!", "line vty", "!", ""]
    return "\n".join(lines)


def _baseline_upstream(topo: _Topo) -> str:
    """Upstream baseline: originates ONLY the single covering supernet."""
    return _node_config(
        topo, topo.upstream,
        networks=[topo.supernet],
        statics=[f"ip route {topo.supernet} blackhole"],
    )


def _baseline_edge(topo: _Topo) -> str:
    """Edge baseline: originates nothing but its own loopback; learns the supernet."""
    return _node_config(topo, topo.edge, networks=[], statics=[])


def _post_upstream(topo: _Topo) -> str:
    """Upstream POST: de-aggregate per the margin (count of specifics) + supernet fate.

    * supernet_fate == "withdrawn": drop the supernet origination + its static and
      originate the constituent /24s (each backed by its own discard static).
    * supernet_fate == "kept": KEEP the supernet origination + static AND ADD the
      constituent /24s alongside it.
    """
    spec_statics = [f"ip route {p} blackhole" for p in topo.specifics]
    spec_networks = list(topo.specifics)
    if topo.spec.supernet_fate == "withdrawn":
        statics = spec_statics
        networks = spec_networks
    else:  # kept
        statics = [f"ip route {topo.supernet} blackhole"] + spec_statics
        networks = [topo.supernet] + spec_networks
    return _node_config(topo, topo.upstream, networks=networks, statics=statics)


def _baseline_configs(topo: _Topo) -> dict[str, str]:
    return {topo.upstream: _baseline_upstream(topo), topo.edge: _baseline_edge(topo)}


def _unified(before: str, after: str, node: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile=f"{node}.conf", tofile=f"{node}.conf", lineterm="",
    )
    patch = "\n".join(diff) + "\n"
    if apply_unified_diff(before, patch) != after:
        raise RuntimeError(f"generated patch for {node} does not round-trip")
    return patch


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: ScaleSpec, seed: int) -> Scenario:
    params = _draw_params(spec, seed)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    after_up = _post_upstream(topo)
    patch = _unified(pre[topo.upstream], after_up, topo.upstream)

    # Watch set (HONEST, no gerrymander): loopbacks (negative controls) + the
    # supernet + a SAMPLE of the specifics (first / middle / last). We watch the
    # supernet so its withdrawal (in the "withdrawn" fate) is scored honestly, and
    # we watch real specifics (which are ADDED, never lost, so they never enter D2)
    # so the watch set is not curated to manufacture a D2 answer.
    sample_idx = sorted({0, len(topo.specifics) // 2, len(topo.specifics) - 1})
    sampled = [topo.specifics[i] for i in sample_idx]
    watched = [f"{topo.up_loop}/32", f"{topo.edge_loop}/32", topo.supernet] + sampled

    # D8 budget annotation: ONLY the edge carries a budget (it is the overflow
    # victim); the upstream's table grows but it is the originator, unconstrained.
    resource_limits = {topo.edge: {"fib": params.budget}}

    # Prose (PROMPT HYGIENE GATE): config edit + intent + the BUDGET annotation
    # ONLY. NEVER the specifics count, NEVER the outcome. The over/under distinction
    # MUST be invisible from prose style — the same words for all six combos, the
    # budget number the only varying literal. The model counts the /24s from the
    # diff and compares against the stated budget.
    if spec.supernet_fate == "withdrawn":
        edit = (
            f"On {topo.upstream} (AS{params.upstream_asn}), remove the single "
            f"covering aggregate `network {topo.supernet}` (and its backing discard "
            f"static) and instead originate the constituent more-specific /24s "
            f"inside that block, each backed by its own discard static."
        )
    else:  # kept
        edit = (
            f"On {topo.upstream} (AS{params.upstream_asn}), keep advertising the "
            f"covering aggregate `network {topo.supernet}` and additionally "
            f"originate the constituent more-specific /24s inside that block, each "
            f"backed by its own discard static."
        )
    description = f"{edit} See the diff for the exact lines."

    intents_text = (
        f"Advertise the customer block {topo.supernet} to {topo.edge} (the "
        f"operator's stated goal is finer-grained traffic engineering by "
        f"advertising the constituent /24s). POLICY/RESOURCE BUDGET: the "
        f"{topo.edge} router's forwarding table (FIB) has a ceiling of "
        f"{params.budget} installed routes — the change MUST keep {topo.edge} "
        f"within that budget. (A device's FIB ceiling is legitimate known context; "
        f"the resulting post-change route count is NOT stated and must be derived "
        f"from the diff + configs.)"
    )

    name = f"gen_scale_{spec.dims_label()}_s{seed}"
    return Scenario(
        name=name,
        nodes=[topo.upstream, topo.edge],
        pre_configs=pre,
        change_target=topo.upstream,
        patch=patch,
        description=description,
        intents_text=intents_text,
        watched_prefixes=watched,
        resource_limits=resource_limits,
        # under-kept has an EMPTY ground truth by construction (benign add of
        # specifics below budget, supernet retained) — a calibration CONTROL, not
        # a damage trap (red-team freeze gate 2026-06-10 #4; mirrors generator_lp's
        # is_trap=(effect=="bypass") doctrine).
        is_trap=not (spec.margin == "under" and spec.supernet_fate == "kept"),
        provenance="templated",
    )


# --------------------------------------------------------------------------- #
# Public API (mirrors generator_ipc).
# --------------------------------------------------------------------------- #
def generate_scale_deagg(seed: int, spec: Optional[ScaleSpec] = None) -> Scenario:
    """Emit ONE Class-8 (scale/de-agg) instance.

    With ``spec=None`` the axis tuple is chosen deterministically from ``seed`` (so
    a bare ``generate_scale_deagg(s)`` is reproducible and covers the space as ``s``
    varies). Passing an explicit ``spec`` pins the structure and uses ``seed`` only
    for the randomized addressing — this is how the suite enumerates every axis
    combination with distinct numbering.
    """
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def generate_scale_suite(n: int, seed: int = 0) -> list[Scenario]:
    """Emit ``n`` DISTINCT Class-8 instances with unique ids.

    Coverage strategy (mirrors generator_ipc.generate_ipc_suite): walk the axis
    space in order and assign each spec a distinct seed (``seed + position``) so the
    structure AND the randomized numbering both vary. If ``n`` exceeds the axis
    count we wrap, giving the SAME structure a NEW randomized instance (still novel,
    still unique-id — the seed is in the name). Ids are guaranteed unique.
    """
    specs = enumerate_specs()
    out: list[Scenario] = []
    for i in range(n):
        spec = specs[i % len(specs)]
        out.append(_scenario_from_spec(spec, seed + i))
    return out


def all_combos(seed: int = 0) -> list[Scenario]:
    """Emit EXACTLY one instance per structural combo (all 6), each at a distinct
    seed so the numbering varies across combos too. The held-out coverage set."""
    specs = enumerate_specs()
    return [_scenario_from_spec(spec, seed + i) for i, spec in enumerate(specs)]
