r"""Family-2 generator — ORIGIN-CODE TIEBREAK FLIP (the `origin_code` mechanism): a
DUAL-ORIGIN customer prefix whose two copies reach `src` tied on LOCAL_PREF and
AS_PATH length, so the BGP best-path decision falls to the ORIGIN step (RFC 4271
§9.1.2.2 (b): lowest Origin number wins — IGP < EGP < INCOMPLETE). The decisive change
re-stamps ONE side's customer-/24 ORIGIN code (igp ↔ incomplete) via the redistribution
route-map's `set origin`, collapsing the ORIGIN tie so the decision falls THROUGH to the
next §9.1.2.2 step — a LATENT MED — which favors the bypass egress. No LOCAL_PREF, no
AS_PATH, no prefix and no session is touched.

This is the hardest comparator in the quiet-half catalog (Family 2, BUILD_V1.1): unlike
the Family-1 underlay-displacement mechanisms (IGP cost / redistribute-AD / next-hop
elimination) the diff lives entirely in the BGP origination namespace, yet it is NOT a
first-order LOCAL_PREF/AS_PATH edit a model catches by reflex — it is a `set origin`
re-stamp whose only routing consequence is an ORIGIN-code change. The reader must know the
RFC 4271 decision order AND that `set origin igp/incomplete` in the redistribution
route-map overrides the redistribute default ORIGIN (FRR docs, ipSpace "BGP Origin
Attribute"; honored by the Batfish FRR model — live-verified on the pinned digest; see
knowledge/corpus/noc/origin_code_quiet_reroute.md).

DIFF-SHAPE SYMMETRIZATION (the 2-feature surface-leak fix, 2026-06-16). PRE-fix the two
knobs rendered DIFFERENT diff SHAPES — the `way` knob a `network`->`redistribute` method
swap (~6+/3-), the `alt` knob a redistribute seq-restatement (~2+/1-) — and the `set
origin` literal value (igp vs incomplete) coupled to (knob XOR effect). The (diff-SHAPE) x
(`set origin` literal) JOINT was perfectly diagonal over the 4 (knob x effect) combos: a
zero-reasoning XOR probe `(method_swap_shape XOR set_origin_igp) -> is_trap` separated
bypass from no_op at balanced-accuracy 1.0 even though NO single feature exceeded 0.5
(the single-feature probe MISSED it). The fix:
  1. SYMMETRIZE THE SHAPE: BOTH knobs render the edited egress's customer /24 in the SAME
     `redistribute static route-map REDIST_CUST` construct PRE *and* POST (way's PRE igp is
     produced by `set origin igp` in the redistribution route-map, not by `network`). The
     decisive edit is therefore the IDENTICAL restatement for both knobs — renumber the
     customer prefix-list seq (5->10) and rewrite the `set origin` value — a fixed-shape
     2+/2- diff whose +/- line COUNT no longer encodes which knob or which effect.
  2. BALANCE THE LITERAL: the surviving char-length / value signal of the `set origin`
     literal (`igp` 15 chars vs `incomplete` 22) is decorrelated from the label by the
     way<->alt physical-slot BALANCED-SWAP (_role_position.balanced_swap, the community_lp
     pattern): across the real finite suite the swap is balanced WITHIN each label class, so
     the edited-node loopback octet / name suffix / node-list index carry ZERO label info
     and the (edited-node x literal) interaction cannot recover the effect.
The legitimate discriminator stays "which origination is on the inspection/waypoint path"
(read the PRE origin + the waypoint intent — routing reasoning), NEVER the literal or the
shape.

Decision order (RFC 4271 §9.1.2.1 degree of preference = LOCAL_PREF, then §9.1.2.2
"Breaking Ties (Phase 2)": (a) shortest AS_PATH > (b) lowest ORIGIN > (c) lowest MED,
same-neighbor-AS only > ... > BGP Identifier/router-id last). `src` learns the customer
/24 over TWO eBGP paths byte-identical on LOCAL_PREF (default 100) and AS_PATH length
(both [AS_egr], length 1, because `way` and `alt` ORIGINATE the prefix — they do not
re-advertise a dst-originated copy), so §9.1.2.2 (a) ties and the decision reaches (b)
ORIGIN. The two paths differ ONLY in ORIGIN code (b) and in a latent MED (c):

  * PRE: the way-side copy is stamped ORIGIN=igp (`redistribute static` + `set origin igp`)
    and the alt-side ORIGIN=incomplete (`redistribute static` + `set origin incomplete`).
    igp < incomplete, so at §9.1.2.2 (b) the way copy wins and src->customer transits the
    inspection node `way`. The latent MED (way=200, alt=50) at step (c) is NEVER consulted
    PRE because (b) already decided.
  * DIFF (bypass): flip the deciding side's ORIGIN (`set origin igp`<->`set origin
    incomplete`) so BOTH copies become equal-ORIGIN. Step (b) now TIES, and the decision
    falls THROUGH to the MED step §9.1.2.2 (c). HONEST ATTRIBUTION (audit M2): PRE the
    ORIGIN step (b) is decisive; POST/bypass the ORIGIN step ties and the **MED step (c) is
    the real POST discriminator** — the waypoint moves because alt's MED 50 < way's 200,
    NOT because of an ORIGIN inequality. The card is a two-attribute mechanism: an ORIGIN
    flip that UNGATES a latent MED gap. (The MED is preserved across the flip — it lives in
    REDIST_CUST `set metric <m>` PRE and POST, never deleted.)
  * POST/no_op: the SAME redistribution-route-map restatement of the CUSTOMER /24 on the
    SAME egress (prefix-list seq renumbered, `set origin` rewritten), but the rewritten
    `set origin` value EQUALS the PRE value, so the customer copy's ORIGIN code lands
    EXACTLY where it was PRE. Step (b) is unchanged, the best path stays on `way`, and
    ground truth is COMPLETELY EMPTY. The no_op diff therefore NAMES the customer prefix
    (its prefix-list / route-map lines) exactly as the bypass does — the two twins are
    construction-parallel AND diff-shape-identical; only reading the `set origin` value
    against the PRE origin (real routing reasoning) tells them apart. (This closes the
    audit-M3 gameability tell, where the OLD no_op edited the OWN loopback /32 and never
    mentioned the customer prefix, so a purely syntactic "does the patch mention the
    customer prefix?" heuristic separated trap from calibration with ZERO routing
    reasoning.)

Why the decision lands on MED, not router-id, once ORIGIN ties (the falsified-tiebreak
gate, docs/oracle_determinism_spec_v1.md / verified live on the pinned digest): after
§9.1.2.2 (b) ties, the next steps are (c) MED, then eBGP-over-iBGP (both eBGP → tie) and
IGP-metric to NEXT_HOP (directly-connected eBGP → tie); if nothing breaks the tie before
the BGP-Identifier/router-id step Batfish installs an ECMP MULTIPATH, which fires D5 and
KILLS D4. The MED gap (way 200 vs alt 50) at step (c) is the STRICT discriminator that
resolves the decision BEFORE router-id is reached, in BOTH snapshots — exactly one best
path at `src` each time, no ECMP tie, maximum-paths default 1.

MED COMPARABILITY — HONEST ACCOUNT (audit M2/M3). RFC 4271 §9.1.2.2 (c) says MED is
"only comparable between routes learned from the same neighboring AS". The topology DOES
satisfy that gate (both customer copies arrive at `src` from neighbor-AS AS_egr), so the
mechanism is RFC-faithful. BUT the oracle does NOT depend on that gate: Batfish's
best-path comparator compares MED UNCONDITIONALLY across ASes — `BgpRib.java:209` is a
bare `Long.compare(lhs.getMetric(), rhs.getMetric())` with no same-leftmost-AS check
(knowledge/corpus/batfish/batfish_verified_facts.md ~line 140; verified on master
2026-06-14). `bgp deterministic-med` / `bgp always-compare-med` PARSE-and-DROP in the FRR
dialect (zero handlers) and are deliberately NOT emitted. So do NOT claim Batfish honors a
same-AS MED gate — it does not; the same-AS topology is for RFC realism, the oracle
compares the MEDs regardless.

MED-PRESERVATION NOTE (audit M4 / FIX #4 — RESOLVED, NOT provisional). The bypass diff does
NOT remove the MED. The customer /24 is originated by `redistribute static route-map
REDIST_CUST` PRE *and* POST, and the MED lives in that route-map as `set metric <m>` in
BOTH states (200 on way, 50 on alt). The decisive edit touches ONLY the prefix-list seq and
the `set origin` value; the `set metric` line is unchanged, so it is not even in the +/-
diff. So the bypass changes EXACTLY ONE routing-relevant attribute — the ORIGIN code —
while holding LOCAL_PREF, AS_PATH, NEXT_HOP and MED constant. The latent MED that decides
POST is the SAME MED that existed (but was un-consulted) PRE.

THE QUIET SIGNATURE (D4 waypoint + D10 intent ONLY): a `set origin` / `redistribute` edit
is not a session parameter and never resets a BGP FSM (RFC 4271 §8: Established exits only
on NOTIFICATION/hold-timer/TCP teardown), so D1=∅. The /24 stays present-and-best in
every RIB across the diff (only WHICH copy wins at src changes; both copies remain
valid), so D2=∅; `alt` delivers the /24 exactly as `way` did (a real, verified path), so
D3=∅, D7=∅. The strict MED gap means exactly one best path in each snapshot — D5=∅ and
the oracle is byte-identical. A naive model predicts a session reset or a prefix loss; the
oracle says ONLY the waypoint (D4) and the matching intent (D10) move.

Topology (5 nodes, ALL eBGP, directly-connected /30 next-hops — no statics except the
two that the DUAL-ORIGIN itself requires, see below)::

           way (AS_egr) --/30-- dst (AS_egr) --/30-- host (AS_egr; customer /24)
          /  way ORIGINATES the customer /24                       ^
   src --/30                                                       | the /24 lives here
  (AS_src) \  alt ORIGINATES the customer /24                      |
           alt (AS_egr) --/30-- dst -----------------------------/

  * `src` (AS_src) eBGP-peers DIRECTLY (over the /30 link IP, no update-source, no
    multihop) with both `way` (AS_egr) and `alt` (AS_egr). Both upstreams are the SAME
    AS so the two customer paths `src` receives share neighbor-AS = AS_egr, which makes
    the latent MED RFC-comparable (RFC 4271 §9.1.2.2 (c): MED is compared only across
    same-neighbor-AS paths). NB the oracle compares MED unconditionally regardless (see
    the MED-comparability note above); the same-AS topology is for RFC realism.
  * `way`, `alt`, `dst`, `host` all live in AS_egr (one customer/egress AS). `way` and
    `alt` each ORIGINATE the customer /24 toward `src` via `redistribute static` — way
    stamped igp, alt stamped incomplete — so `src`'s two received paths have
    AS_PATH=[AS_egr], length 1 (the AS_PATH-length tie that forces the decision down to
    ORIGIN). They do NOT learn the /24 from `dst` over BGP (that would lengthen the
    AS_PATH and break the tie).
  * The customer /24 physically lives on `host`'s connected dummy interface; `dst`
    forwards to `host` and `way`/`alt` forward to `dst`, all via the two REQUIRED static
    routes toward the /24 (the dual-origin construction needs them: `redistribute static`
    has nothing to redistribute without a static). These statics are GENUINELY REQUIRED by
    the mechanism, not a recursive-next-hop crutch: they exist to make the two
    ORIGINATIONS legal and the prefix deliverable, and they are inside AS_egr's forwarding
    plane, never on `src`.

Structural axes (each a genuinely distinct config-reading task or a calibration control
— NOT a clone):

  * knob ∈ {way_to_incomplete, alt_to_igp} — two DIFFERENT ORIGIN re-stamps that both
    collapse the ORIGIN ordering to a tie, each on the OPPOSITE device and the OPPOSITE
    direction of the flip (so a model cannot pattern-match one rewrite):
      - way_to_incomplete : PRE way ORIGIN=igp, alt ORIGIN=incomplete; way wins on ORIGIN.
        The change flips WAY's customer ORIGIN igp->incomplete, the ORIGIN step ties, and
        the latent MED (alt 50 < way 200) takes over.
      - alt_to_igp : SAME PRE (way igp wins). The change flips ALT's customer ORIGIN
        incomplete->igp, the ORIGIN step ties, and the SAME latent MED takes over. Same
        outcome class, opposite device + opposite flip direction, a distinct construct to
        read.

  * effect ∈ {bypass, no_op} — the calibration axis:
      - bypass : the flip actually collapses the customer /24's ORIGIN tie (§9.1.2.2 (b)),
        ungating the latent MED (c). D4+D10 fire; D1/D2/D3/D5/D7 = ∅. THE trap.
      - no_op  : the SAME redistribution-route-map restatement of the CUSTOMER /24 on the
        SAME egress, but the rewritten `set origin` value EQUALS the PRE value so the
        customer copy's ORIGIN code is unchanged — the best path stays on `way`. Ground
        truth is COMPLETELY EMPTY across ALL dimensions. CRITICALLY the no_op diff is
        SHAPE-IDENTICAL to the bypass (same prefix-list + `set origin` +/- lines) and NAMES
        the customer prefix exactly as the bypass does, so neither a syntactic "does the
        patch touch the customer prefix?" heuristic NOR a diff-shape probe can separate
        trap from calibration. Only reading the `set origin` value and reasoning whether it
        lands where it was PRE separates them — genuine best-path reasoning.

That is 2 knobs × 2 effects = 4 structural combos × seeds.

Per-seed randomization (contamination control, exactly like generator_lp): the egress
AS, the source AS, the loopback block, the link /30 supernet, the customer /24, and the
node base name are all drawn deterministically from the seed. Same seed ⇒ byte-identical
instance; different seed ⇒ a novel instance even for this public mechanism.

Per-label BALANCED-SWAP (the 2-feature surface-leak fix, mirrors generator_community_lp):
the way<->alt PHYSICAL slot (loopback octet, node name suffix, node-list index) is swapped
on a balanced subset WITHIN each label class over the real finite suite the sweep builds,
so the edited-node physical identity is split ~50/50 within bypass AND within no_op and
carries ZERO label information. The LOGICAL roles (way=waypoint, alt=bypass) remain the
ground-truth anchors; only their physical identity moves.

Determinism contract (oracle_determinism_spec class STATIC-DET): every best-path decision
is STRICT in both snapshots — PRE the ORIGIN step §9.1.2.2 (b) (igp < incomplete) decides;
POST/bypass the ORIGIN step ties and the MED step §9.1.2.2 (c) (50 < 200) decides, ABOVE
the BGP-Identifier/router-id step; POST/no_op nothing about the customer decision moves
(the rewritten `set origin` equals PRE). Exactly one best path at `src` each time, no
equal-cost ECMP tie, maximum-paths default 1. D4 is scored by
ExtendedOracle._waypoint_diff as the all-traces-transit invariant; D10 by the matching
kind="waypoint" IntentInvariant.

LIVE-VERIFIED (pinned batfish/allinone:nethelm @ 09817554db90): PRE src best = igp via
way (ORIGIN (b) beats incomplete; MED 200 not consulted), trace src->way->dst->host;
bypass flips the deciding ORIGIN, both copies become equal-ORIGIN, step (b) ties and the
MED (c) (alt 50 < way 200) decides, trace src->alt->dst->host; reachability preserved both
ways; bypass combos -> {waypoint, intent} ONLY, no_op combos -> COMPLETELY EMPTY across all
dims, bypass combos 10x byte-identical. Re-verified post-symmetrization in
runs/oracle_verify_origin_code_2feat_*.

Public API mirrors generator_lp / generator_community_lp:
    generate_origin_code_suite(n, base_seed=...)        -> list[Scenario]
    generate_origin_code_all_combos(seed=...)           -> list[Scenario]
    generate_origin_code_instance(seed, spec=None)      -> Scenario
    enumerate_specs() / enumerable_count()
"""

from __future__ import annotations

import dataclasses
import difflib
import random
from dataclasses import dataclass
from typing import Optional

from netbrace.tasks.safety.scenarios import IntentInvariant, Scenario
from netbrace.tasks.safety import _role_position as _rp
from netbrace.topology.patches import apply_unified_diff

# --------------------------------------------------------------------------- #
# Axis value sets (the enumerable space).
# --------------------------------------------------------------------------- #
KNOB_VALUES = ("way_to_incomplete", "alt_to_igp")
EFFECT_VALUES = ("bypass", "no_op")

AXES = {
    "knob": KNOB_VALUES,
    "effect": EFFECT_VALUES,
}

# The latent MED carried toward src on each upstream's customer-/24 advertisement.
# way's is STRICTLY HIGHER than alt's so that once the ORIGIN step ties (post bypass)
# the same-neighbor-AS MED comparison favors alt (the bypass egress). The gap is the
# strict discriminator that keeps the decision off router-id (no D5 ECMP).
_MED_WAY = 200
_MED_ALT = 50

# The PRE ORIGIN code of each LOGICAL egress's customer /24 (the §9.1.2.2 (b) ordering
# that makes `way` win PRE). way=igp beats alt=incomplete.
_PRE_ORIGIN = {"way": "igp", "alt": "incomplete"}


@dataclass(frozen=True)
class OriginCodeSpec:
    """A point in the Family-2 origin-code generator space (axis tuple, pre-random)."""

    knob: str
    effect: str

    def dims_label(self) -> str:
        return f"{self.knob}-{self.effect}"


def enumerate_specs() -> list[OriginCodeSpec]:
    """All VALID axis tuples, in a fixed order (the enumerable instance space)."""
    out: list[OriginCodeSpec] = []
    for knob in KNOB_VALUES:
        for effect in EFFECT_VALUES:
            out.append(OriginCodeSpec(knob, effect))
    return out


def enumerable_count() -> int:
    return len(enumerate_specs())


# --------------------------------------------------------------------------- #
# Per-seed randomized parameters (the contamination control).
# --------------------------------------------------------------------------- #
# Private 4-byte ASN range (RFC 6996). TWO distinct ASNs: the source AS (src) and the
# egress AS (way/alt/dst/host all share it -> the two customer paths src receives have
# the SAME neighbor-AS, which is what makes the latent MED comparable). Clear of the
# hand-authored 65000 family.
_ASN_LO, _ASN_HI = 4_200_300_000, 4_200_399_999

_CUSTOMER_POOLS = [
    "203.0.113.0",   # TEST-NET-3
    "198.51.100.0",  # TEST-NET-2
    "192.0.2.0",     # TEST-NET-1
    "100.64.{c}.0",  # CGNAT shared (carrier customer space)
]

_NAME_POOLS = ["r", "rtr", "pe", "node", "edge", "bdr"]

_ROLES = ("src", "way", "alt", "dst", "host")

# The pair whose PHYSICAL slot is balanced-swapped per seed (the inspection/bypass pair).
_SWAP_PAIR = ("way", "alt")


@dataclass(frozen=True)
class _Params:
    """The randomized-but-fixed-per-seed concrete values for one instance."""

    src_asn: int             # the source AS (eBGP to both upstreams)
    egr_asn: int             # way/alt/dst/host share this (so MED is comparable at src)
    loop_block: str          # e.g. "10.37.0" -> loopbacks 10.37.0.X/32
    link_block: tuple[int, int, int]  # first three octets of the /30 link supernet
    customer_net: str        # e.g. "198.51.100" (the /24 base, no mask)
    decoy_net: str           # an off-path /24 (NO static) -> route-map clause-20 inert
    name: dict[str, str]     # role -> randomized node name string
    swap: bool               # True => exchange way<->alt physical slot (the FB-5 fix)


def _replace_swap(params: _Params, swap: bool) -> _Params:
    """Return a copy of ``params`` with the balanced swap injected (frozen dataclass)."""
    return dataclasses.replace(params, swap=swap)


def _draw_params(seed: int) -> _Params:
    rng = random.Random(seed)

    src_asn = rng.randint(_ASN_LO, _ASN_HI)
    egr_asn = src_asn
    while egr_asn == src_asn:
        egr_asn = rng.randint(_ASN_LO, _ASN_HI)

    loop_block = f"10.{rng.randint(1, 250)}.{rng.randint(0, 250)}"
    link_block = (192, rng.randint(0, 250), rng.randint(0, 250))

    cust = rng.choice(_CUSTOMER_POOLS).format(c=rng.randint(0, 250))
    customer_net = ".".join(cust.split(".")[:3])

    # A DECOY /24 (distinct from the customer /24) used by an inert route-map clause-20:
    # it has NO static route, so `redistribute static` never presents it and clause-20
    # never fires. Re-stamping clause-20's ORIGIN is therefore best-path-NEUTRAL (the
    # no_op edit), while clause-10 (the customer /24, which HAS a static) governs the real
    # advertisement (the bypass edit). Same diff SHAPE, the discriminator is WHICH clause.
    decoy_net = customer_net
    while decoy_net == customer_net:
        dpool = rng.choice(_CUSTOMER_POOLS).format(c=rng.randint(0, 250))
        decoy_net = ".".join(dpool.split(".")[:3])

    base = rng.choice(_NAME_POOLS)
    name = {role: f"{base}{i}" for i, role in enumerate(_ROLES, start=1)}

    # The way<->alt swap is NOT drawn here. An unconstrained per-seed Bernoulli does not
    # balance over a finite suite, and because the edited node IS the swapped (way/alt) pair
    # the edited-node loopback octet/name/index would leak the label (FB-5 class). The swap
    # is assigned by the suite via _rp.balanced_swap(occurrence-within-label) so it is
    # balanced WITHIN each label class. _draw_params returns swap=False; the real value is
    # injected in _scenario_from_spec / the suite (one-off instances get a per-seed parity).
    return _Params(src_asn=src_asn, egr_asn=egr_asn, loop_block=loop_block,
                   link_block=link_block, customer_net=customer_net,
                   decoy_net=decoy_net, name=name, swap=False)


# --------------------------------------------------------------------------- #
# Topology builder. Links (lower role first): src-way, src-alt, way-dst, alt-dst,
# dst-host. Deterministic addressing derived from the randomized blocks. The way<->alt
# PHYSICAL slot (loopback octet, name) is exchanged when params.swap (the FB-5 balance).
# --------------------------------------------------------------------------- #
@dataclass
class _Topo:
    params: _Params
    spec: OriginCodeSpec
    name: dict[str, str]
    loopback: dict[str, str]
    rid_index: dict[str, int]
    ip: dict[tuple[str, str], str]
    customer_prefix: str
    customer_ip: str
    decoy_prefix: str


def _build_topo(spec: OriginCodeSpec, params: _Params) -> _Topo:
    # The LOGICAL roles way/alt are the ground-truth anchors; their PHYSICAL slot
    # (loopback octet, node name suffix index) is exchanged when params.swap so the
    # edited-node identity carries no label info (balanced over the suite).
    base_rid = {"src": 1, "way": 2, "alt": 3, "dst": 4, "host": 5}
    rid_index = _rp.swapped_rid_index(base_rid, params.swap, _SWAP_PAIR)
    name = _rp.swapped_names(params.name, params.swap, _SWAP_PAIR)

    loopback = {r: f"{params.loop_block}.{rid_index[r]}" for r in _ROLES}

    b, c0, c1 = params.link_block

    def addr(off: int) -> str:
        return f"{b}.{c0}.{c1}.{off}"

    # /30 link supernets, one per link, carved from the link block:
    #   src-way  base .0  (src=.1,  way=.2)
    #   src-alt  base .4  (src=.5,  alt=.6)
    #   way-dst  base .8  (way=.9,  dst=.10)
    #   alt-dst  base .12 (alt=.13, dst=.14)
    #   dst-host base .16 (dst=.17, host=.18)
    ip: dict[tuple[str, str], str] = {
        ("src", "way"): addr(1), ("way", "src"): addr(2),
        ("src", "alt"): addr(5), ("alt", "src"): addr(6),
        ("way", "dst"): addr(9), ("dst", "way"): addr(10),
        ("alt", "dst"): addr(13), ("dst", "alt"): addr(14),
        ("dst", "host"): addr(17), ("host", "dst"): addr(18),
    }

    customer_prefix = f"{params.customer_net}.0/24"
    customer_ip = f"{params.customer_net}.1"
    decoy_prefix = f"{params.decoy_net}.0/24"

    return _Topo(params=params, spec=spec, name=name, loopback=loopback,
                 rid_index=rid_index, ip=ip, customer_prefix=customer_prefix,
                 customer_ip=customer_ip, decoy_prefix=decoy_prefix)


# --------------------------------------------------------------------------- #
# Config text rendering (FRR / CUMULUS_CONCATENATED, frr 10.6.1 — the verified
# baseline_ospf_core6 / generator_lp format). All eBGP, directly-connected /30 peers.
# --------------------------------------------------------------------------- #
_FRR_VER = "frr version 10.6.1"
_LINK_MASK = "/30"


def _iface_header(node_name: str, loopback: str,
                  eth: list[tuple[str, str]], dummies: list[tuple[str, str]]) -> str:
    """The /etc/network/interfaces-style block (CUMULUS_CONCATENATED header)."""
    ib = [
        node_name, "",
        "# This file describes the network interfaces",
        "auto lo", "iface lo inet loopback", f"    address {loopback}/32", "",
    ]
    for iface, ipm in eth + dummies:
        ib += [f"auto {iface}", f"iface {iface} inet static", f"    address {ipm}", ""]
    ib += ["# ports.conf --", ""]
    return "\n".join(ib) + "\n"


def _frr_header(node_name: str) -> str:
    return (
        f"{_FRR_VER}\n"
        "frr defaults traditional\n"
        f"hostname {node_name}\n"
        "service integrated-vtysh-config\n!\n"
        "ip forwarding\n!\n"
    )


def _plain_iface(iface: str, ipm: str) -> str:
    return f"interface {iface}\n ip address {ipm}\n!\n"


# --------------------------------------------------------------------------- #
# src: AS_src, eBGP to way + alt (directly-connected /30s), NO policy. The two
# received customer paths are tied on LOCAL_PREF + AS_PATH-length, so ORIGIN decides.
# --------------------------------------------------------------------------- #
def _src_config(topo: _Topo) -> str:
    p = topo.params
    lo = topo.loopback["src"]
    eth = [("eth1", f"{topo.ip[('src', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('src', 'alt')]}{_LINK_MASK}")]
    body = [_iface_header(topo.name["src"], lo, eth, []), _frr_header(topo.name["src"])]
    body.append(_plain_iface("lo", f"{lo}/32"))
    body.append(_plain_iface("eth1", f"{topo.ip[('src', 'way')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[('src', 'alt')]}{_LINK_MASK}"))
    body.append(f"router bgp {p.src_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('way', 'src')]} remote-as {p.egr_asn}\n")
    body.append(f" neighbor {topo.ip[('alt', 'src')]} remote-as {p.egr_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


# --------------------------------------------------------------------------- #
# way / alt: AS_egr egresses that ORIGINATE the customer /24 toward src. BOTH ORIGINATE
# the customer /24 via the SAME `redistribute static route-map REDIST_CUST` construct
# (the diff-shape symmetrization). REDIST_CUST has TWO permit clauses, IDENTICAL in shape:
#   * clause 10 — `match ip address prefix-list CUST_PL` (the customer /24, which HAS a
#     static so it IS redistributed): `set origin <cust_origin>` + `set metric <med>`.
#     This clause governs the real advertisement toward src — the BYPASS edits it.
#   * clause 20 — `match ip address prefix-list DECOY_PL` (a decoy /24 with NO static, so
#     `redistribute static` never presents it and the clause NEVER fires):
#     `set origin <decoy_origin>` + `set metric <med>`. Best-path-INERT — the NO_OP edits
#     it. (Mirrors generator_community_lp's matched-tag vs ignored-tag calibration.)
# Re-stamping clause-10's ORIGIN moves the customer copy's best path (bypass); re-stamping
# clause-20's ORIGIN is inert (no_op). The two edits are diff-shape IDENTICAL (a CUST_PL
# seq renumber + a `set origin` token rewrite); the ONLY difference is WHICH clause the
# rewritten origin governs — readable only by tracing the route-map (routing reasoning).
# The latent MED is carried identically PRE and POST in BOTH clauses (never removed). Both
# egresses static-route the customer /24 to dst (REQUIRED by the dual-origin construction).
# The OWN loopback is ALWAYS originated by `network <lo>/32` (never touched).
# --------------------------------------------------------------------------- #
def _egress_config(topo: _Topo, role: str, *, cust_origin: str, decoy_origin: str,
                   med: int, cust_seq: int = 5) -> str:
    """Render way/alt with the customer /24 originated via `redistribute static` and a
    TWO-clause REDIST_CUST route-map (clause 10 = customer /24, clause 20 = inert decoy).

    ``cust_origin`` ∈ {"igp","incomplete"} is stamped on the customer clause (clause 10)
    via `set origin` — this is the ORIGIN code that actually reaches src. ``decoy_origin``
    is stamped on the inert decoy clause (clause 20); it has NO routing effect (the decoy
    /24 has no static, so the clause never fires). ``med`` is the role's fixed MED, carried
    identically in BOTH clauses PRE and POST (so the MED is PRESERVED across an ORIGIN
    flip). ``cust_seq`` is the CUST_PL seq number (the restatement renumbers it 5 -> 10 so
    the decisive edit produces a +/- diff line that names the customer prefix).
    """
    p = topo.params
    lo = topo.loopback[role]
    eth = [("eth1", f"{topo.ip[(role, 'src')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[(role, 'dst')]}{_LINK_MASK}")]
    body = [_iface_header(topo.name[role], lo, eth, []), _frr_header(topo.name[role])]
    body.append(_plain_iface("lo", f"{lo}/32"))
    body.append(_plain_iface("eth1", f"{topo.ip[(role, 'src')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[(role, 'dst')]}{_LINK_MASK}"))
    # REQUIRED static toward the customer /24 (via dst): makes the prefix present in the
    # RIB AND redistributable (so `redistribute static` injects it) AND forwardable to
    # dst->host. NO static toward the decoy /24 -> clause 20 never fires.
    body.append(f"ip route {topo.customer_prefix} {topo.ip[('dst', role)]}\n")
    # prefix-lists: CUST_PL (the redistributed customer /24, seq is the renumber carrier)
    # and DECOY_PL (the off-path /24 with no static).
    body.append(
        f"ip prefix-list CUST_PL seq {cust_seq} permit {topo.customer_prefix}\n!\n")
    body.append(
        f"ip prefix-list DECOY_PL seq 5 permit {topo.decoy_prefix}\n!\n")
    # The two-clause redistribution route-map (clause 10 = customer, clause 20 = inert).
    rm_lines = [
        "route-map REDIST_CUST permit 10",
        " match ip address prefix-list CUST_PL",
        f" set origin {cust_origin}",
        f" set metric {med}",
        "route-map REDIST_CUST permit 20",
        " match ip address prefix-list DECOY_PL",
        f" set origin {decoy_origin}",
        f" set metric {med}",
    ]
    body.append("\n".join(rm_lines) + "\n!\n")

    body.append(f"router bgp {p.egr_asn}\n")
    body.append(f" bgp router-id {lo}\n")
    body.append(f" neighbor {topo.ip[('src', role)]} remote-as {p.src_asn}\n")
    body.append(" !\n address-family ipv4 unicast\n")
    body.append(f"  network {lo}/32\n")
    body.append("  redistribute static route-map REDIST_CUST\n")
    body.append(" exit-address-family\n!\nline vty\n!\n")
    return "".join(body)


# --------------------------------------------------------------------------- #
# dst: AS_egr transit between the two egresses and host. NO BGP (forwarding-only);
# static toward the customer /24 via host. host: AS_egr, holds the customer /24 on a
# connected dummy interface (the real destination the traceroute is accepted at).
# --------------------------------------------------------------------------- #
def _dst_config(topo: _Topo) -> str:
    lo = topo.loopback["dst"]
    eth = [("eth1", f"{topo.ip[('dst', 'way')]}{_LINK_MASK}"),
           ("eth2", f"{topo.ip[('dst', 'alt')]}{_LINK_MASK}"),
           ("eth3", f"{topo.ip[('dst', 'host')]}{_LINK_MASK}")]
    body = [_iface_header(topo.name["dst"], lo, eth, []), _frr_header(topo.name["dst"])]
    body.append(_plain_iface("lo", f"{lo}/32"))
    body.append(_plain_iface("eth1", f"{topo.ip[('dst', 'way')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth2", f"{topo.ip[('dst', 'alt')]}{_LINK_MASK}"))
    body.append(_plain_iface("eth3", f"{topo.ip[('dst', 'host')]}{_LINK_MASK}"))
    body.append(f"ip route {topo.customer_prefix} {topo.ip[('host', 'dst')]}\n")
    return "".join(body)


def _host_config(topo: _Topo) -> str:
    lo = topo.loopback["host"]
    eth = [("eth1", f"{topo.ip[('host', 'dst')]}{_LINK_MASK}")]
    dummies = [("dum0", f"{topo.customer_ip}/24")]
    body = [_iface_header(topo.name["host"], lo, eth, dummies), _frr_header(topo.name["host"])]
    body.append(_plain_iface("lo", f"{lo}/32"))
    body.append(_plain_iface("eth1", f"{topo.ip[('host', 'dst')]}{_LINK_MASK}"))
    body.append(_plain_iface("dum0", f"{topo.customer_ip}/24"))
    return "".join(body)


# --------------------------------------------------------------------------- #
# The PRE baseline. way originates the customer /24 (clause 10) ORIGIN=igp (MED 200); alt
# ORIGIN=incomplete (MED 50). way wins at the ORIGIN step (igp < incomplete). The INERT
# decoy clause (clause 20) carries the SAME PRE origin as the customer clause on each
# egress, so the no_op's decoy flip and the bypass's customer flip move the SAME token in
# the SAME direction (per knob) -> identical changed-token distribution across labels.
# --------------------------------------------------------------------------- #
def _baseline_configs(topo: _Topo) -> dict[str, str]:
    way = _egress_config(topo, "way", cust_origin=_PRE_ORIGIN["way"],
                         decoy_origin=_PRE_ORIGIN["way"], med=_MED_WAY)
    alt = _egress_config(topo, "alt", cust_origin=_PRE_ORIGIN["alt"],
                         decoy_origin=_PRE_ORIGIN["alt"], med=_MED_ALT)
    return {
        topo.name["src"]: _src_config(topo),
        topo.name["way"]: way,
        topo.name["alt"]: alt,
        topo.name["dst"]: _dst_config(topo),
        topo.name["host"]: _host_config(topo),
    }


# --------------------------------------------------------------------------- #
# The change. ALWAYS an ORIGIN re-stamp on ONE egress (the change_target: `way` for
# knob=way_to_incomplete, `alt` for knob=alt_to_igp). BOTH effects render the IDENTICAL
# diff SHAPE — renumber the CUSTOMER prefix-list seq (CUST_PL 5 -> 10) AND rewrite ONE
# `set origin` token — differing ONLY in WHICH route-map clause the rewritten origin
# governs:
#   * bypass : flip CLAUSE-10's origin (the CUSTOMER /24 clause) PRE -> opposite -> the
#              customer copy's ORIGIN flips, the §9.1.2.2 (b) tie collapses, the latent MED
#              (c) decides -> waypoint moves.
#   * no_op  : flip CLAUSE-20's origin (the INERT DECOY clause, whose /24 has no static so
#              it is never redistributed) PRE -> opposite -> NO routing effect -> empty GT.
# Because clause 20's PRE origin EQUALS clause 10's PRE origin on each egress, the rewritten
# token is identical between the two effects of a given knob (way -> incomplete, alt ->
# igp), so the changed `set origin` token carries no label info; the CUST_PL seq renumber
# (which names the customer /24) is byte-identical in both. The ONLY discriminator is which
# clause the origin sits in (does it govern the customer /24 on the inspection path) —
# readable only by tracing the route-map (genuine best-path reasoning). The change_target,
# the `set metric` line and the OWN loopback `network <lo>/32` are untouched.
# --------------------------------------------------------------------------- #
def _change_target(spec: OriginCodeSpec) -> str:
    return "way" if spec.knob == "way_to_incomplete" else "alt"


def _apply_change(topo: _Topo) -> str:
    spec = topo.spec
    role = _change_target(spec)
    med = _MED_WAY if role == "way" else _MED_ALT

    pre_origin = _PRE_ORIGIN[role]                       # way=igp, alt=incomplete
    flip_origin = "incomplete" if pre_origin == "igp" else "igp"

    # PRE: both clauses stamp pre_origin (clause 10 = customer, clause 20 = decoy).
    # POST: the bypass flips CLAUSE 10 (customer -> reroute); the no_op flips CLAUSE 20
    # (decoy -> inert). The flipped token is identical (flip_origin) for both effects of
    # this knob; only the clause differs. CUST_PL seq is renumbered 5 -> 10 in BOTH.
    before = _egress_config(topo, role, cust_origin=pre_origin,
                            decoy_origin=pre_origin, med=med, cust_seq=5)
    if spec.effect == "bypass":
        after = _egress_config(topo, role, cust_origin=flip_origin,
                               decoy_origin=pre_origin, med=med, cust_seq=10)
    else:
        after = _egress_config(topo, role, cust_origin=pre_origin,
                               decoy_origin=flip_origin, med=med, cust_seq=10)

    if before == after:
        raise RuntimeError(
            f"change for {spec.dims_label()} produced no diff (render drift)")
    return _unified(before, after, topo.name[role])


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
# Prose (CONFIG EDIT + INTENT ONLY — never the routing OUTCOME). BOTH effects re-stamp the
# CUSTOMER prefix's ORIGIN on the same egress's redistribution route-map, so the prose
# names only WHICH construct is rewritten (`redistribute static` / prefix-list / route-map
# / `set origin` / `set metric`), never whether the best path moves, which ORIGIN code
# results, or whether the edit is neutral. CRUCIAL: the no_op prose must NOT betray its
# neutrality (no "unchanged", "no effect", etc.) — the model must DERIVE neutrality from
# the diff (the `set origin` value vs PRE) by routing reasoning, not be told. The
# forbidden-outcome lint (test_generator_family1) bars bypass/reroute/no-longer/wins/loses/
# best-path/etc; config-construct words (redistribute, prefix-list, metric, origin) are
# allowed — they name what is edited.
# --------------------------------------------------------------------------- #
def _description(topo: _Topo) -> str:
    spec = topo.spec
    role = _change_target(spec)
    rname = topo.name[role]
    asn = topo.params.egr_asn
    # The flipped `set origin` token (identical for both effects of this knob; the EFFECT
    # is which route-map clause it lands in, which the prose does NOT reveal).
    flip_origin = "incomplete" if _PRE_ORIGIN[role] == "igp" else "igp"
    edit = (
        f"in the `redistribute static` route-map on this router, rewrite a `set origin` "
        f"clause to `set origin {flip_origin}` (the matched prefix-list and the existing "
        f"metric are kept), re-listing the customer prefix in its prefix-list"
    )
    return (
        f"On `{rname}` (AS{asn}), {edit} — a one-construct origination edit. "
        f"See the diff."
    )


_INTENTS_TEXT = (
    "All traffic from `{src}` to the customer space {cust} MUST transit the "
    "inspection node `{way}`. The customer prefix MUST remain reachable. The "
    "operator's stated goal for the change is to tune how this prefix is originated "
    "into BGP."
)


# --------------------------------------------------------------------------- #
# Scenario assembly.
# --------------------------------------------------------------------------- #
def _scenario_from_spec(spec: OriginCodeSpec, seed: int,
                        swap: Optional[bool] = None,
                        occurrence: Optional[int] = None) -> Scenario:
    params = _draw_params(seed)
    if swap is None:
        # one-off instance: deterministic seed-parity (suite balance is injected below).
        swap = bool(seed % 2)
    if occurrence is None:
        occurrence = seed  # one-off: any int; balance is a suite property
    params = _replace_swap(params, swap)
    topo = _build_topo(spec, params)
    pre = _baseline_configs(topo)
    role = _change_target(spec)
    change_target = topo.name[role]
    patch = _apply_change(topo)

    src, way, alt, dst, host = (topo.name[r] for r in _ROLES)
    cust = topo.customer_prefix
    cust_host = topo.customer_ip + "/32"

    # D2 watch set: customer /24 + the four egress-side loopbacks + src loopback
    # (negative controls — a model that false-positives on a survivor loses precision).
    watched = [f"{topo.loopback[r]}/32" for r in ("src", "way", "alt", "dst")] + [cust]

    # D3 proof: src must STILL reach the customer host post-change (off-path).
    reach = [(src, cust_host)]

    # D4 waypoint intent: src->customer MUST transit `way`. Probe the /32 host so the
    # trace terminates at a real connected accept.
    waypoint_intents = [(src, cust_host, way)]

    # D10 intent invariant: the SAME waypoint restated as a kind="waypoint"
    # IntentInvariant so the intent dimension fires alongside the path dimension.
    intent_invariants = [
        IntentInvariant(
            kind="waypoint", src=src, dst=cust_host, waypoint=way,
            note=f"origin-code quiet reroute: src->{cust} must transit {way}",
        )
    ]

    name = f"gen_origin_code_{spec.dims_label()}_s{seed}"
    description = _description(topo)
    intents_text = _INTENTS_TEXT.format(src=src, cust=cust, way=way)

    # Node-list order: the change_target is placed at a BALANCED index within its label
    # class (the ct_index-leak fix), so its node-list position carries no label info even
    # though the bypass and no_op of a given knob edit the SAME node.
    node_rng = random.Random(f"origin_code_nodes_{seed}")
    nodes = _rp.balanced_node_order([src, way, alt, dst, host], change_target,
                                    occurrence, node_rng)

    return Scenario(
        name=name,
        nodes=nodes,
        pre_configs=pre,
        change_target=change_target,
        patch=patch,
        description=description,
        intents_text=intents_text,
        watched_prefixes=watched,
        reachability_flows=reach,
        waypoint_intents=waypoint_intents,
        intent_invariants=intent_invariants,
        # bypass = the trap (D4+D10 fire while sessions/prefixes/reachability survive);
        # no_op  = genuinely inert (empty GT), so is_trap stays False.
        is_trap=(spec.effect == "bypass"),
        provenance="templated",
    )


# --------------------------------------------------------------------------- #
# Public API (mirrors generator_lp / generator_community_lp).
# --------------------------------------------------------------------------- #
def generate_origin_code_instance(
    seed: int, spec: Optional[OriginCodeSpec] = None
) -> Scenario:
    """Emit ONE Family-2 origin-code instance. With ``spec=None`` the axis tuple is
    chosen deterministically from ``seed`` (so a bare call walks the space)."""
    if spec is None:
        specs = enumerate_specs()
        spec = specs[seed % len(specs)]
    return _scenario_from_spec(spec, seed)


def _selected_specs(include_noop: bool) -> list[OriginCodeSpec]:
    specs = enumerate_specs()
    if include_noop:
        return specs
    return [s for s in specs if s.effect != "no_op"]


def generate_origin_code_all_combos(
    *, seed: int = 0, include_noop: bool = True
) -> list[Scenario]:
    """One instance per structural combo (4 with no_op, 2 without), distinct seeds."""
    specs = _selected_specs(include_noop)
    return _emit_balanced(specs, seed)


def generate_origin_code_suite(
    n: int, *, base_seed: int = 0, include_noop: bool = True
) -> list[Scenario]:
    """Emit ``n`` DISTINCT instances with unique ids (walk the axis space, distinct seed
    per position; wrap with a fresh seed offset when ``n`` exceeds the combo count,
    giving the same structure a NEW randomized instance).

    The way<->alt PHYSICAL swap is BALANCED within each label class (the FB-5 / 2-feature
    fix): the k-th bypass and the k-th no_op each get a balanced-shuffle swap so the
    edited-node loopback octet / name suffix / node-list index is split ~50/50 within
    bypass AND within no_op, carrying zero label information over the actual finite suite
    the sweep builds. Together with the symmetrized diff shape, neither the shape, the
    `set origin` literal, nor any (shape x literal) / (edited-node x literal) interaction
    recovers the bypass/no_op label.
    """
    specs = _selected_specs(include_noop)
    chosen = [specs[i % len(specs)] for i in range(n)]
    return _emit_balanced(chosen, base_seed)


def _emit_balanced(chosen: list[OriginCodeSpec], base_seed: int) -> list[Scenario]:
    """Emit one Scenario per spec in ``chosen`` with a per-label BALANCED-SHUFFLE
    (way/alt)-swap assignment (the FB-5 fix, hardened against fold-aligned parity).

    For EACH label class (bypass / no_op) we assign exactly ceil(k/2) swaps to a
    DETERMINISTICALLY-SHUFFLED subset of that label's occurrences. This (a) guarantees the
    edited-node physical slot is split 50/50 within the label over the real suite the sweep
    builds, and (b) decorrelates the swap from the occurrence INDEX, so no stratified
    train/test split (which a probe could exploit) recovers the label from the edited-node
    octet/name/index. The change_target node-list INDEX is balanced the same way via
    _rp.balanced_node_order keyed on the per-label occurrence rank (shuffle-decorrelated).
    """
    by_label: dict[str, list[int]] = {}
    for i, spec in enumerate(chosen):
        by_label.setdefault(spec.effect, []).append(i)
    swap_for: dict[int, bool] = {}
    occ_rank: dict[int, int] = {}
    for label, positions in by_label.items():
        k = len(positions)
        flags = [True] * ((k + 1) // 2) + [False] * (k - (k + 1) // 2)
        rng = random.Random(f"origin_code_swap_{base_seed}_{label}")
        rng.shuffle(flags)
        for rank, (pos, fl) in enumerate(zip(positions, flags)):
            swap_for[pos] = fl
            occ_rank[pos] = rank
    out: list[Scenario] = []
    for i, spec in enumerate(chosen):
        out.append(_scenario_from_spec(spec, base_seed + i,
                                       swap=swap_for[i], occurrence=occ_rank[i]))
    return out
