# Batfish — Verified Facts, Column Names, and Known Limitations

## What Batfish Is
Batfish is an open-source network configuration analysis tool. It builds a complete model of a network from configuration files (without a running network), then answers questions about routing, reachability, and correctness. It uses the pybatfish Python client to interact with a running Batfish server.

## Docker Setup (NetHELM)
```
docker run -d --name batfish -p 9996:9996 -p 9997:9997 batfish/allinone:netbrace
```
Ports: 9996 (gRPC questions), 9997 (HTTP status/UI).

## Key pybatfish API

### Session + Snapshot
```python
from pybatfish.client.session import Session
bf = Session(host="localhost")
bf.set_network("my_network")
bf.init_snapshot("/path/to/snapshot_dir", name="snap1", overwrite=True)
```
Snapshot directory must contain a `configs/` subdirectory with router config files.

### bgpSessionStatus Question
Returns all BGP sessions and their status.
```python
from pybatfish.question import bfq
result = bfq.bgpSessionStatus().answer(snapshot="snap1").frame()
```
**Verified column names (FRR/IOS):**
- `Node` — local router name
- `VRF` — VRF name (usually "default")
- `Local_AS` — local AS number
- `Remote_AS` — remote AS number
- `Local_IP` — local BGP source IP
- `Remote_IP` — remote peer IP
- `Session_Type` — "IBGP" | "EBGP_SINGLEHOP" | "EBGP_MULTIHOP"
- `Established_Status` — "ESTABLISHED" | "NOT_ESTABLISHED" | "UNIQUE_MATCH"

**Filter for established sessions:**
```python
established = result[result["Established_Status"] == "ESTABLISHED"]
```

### bgpRib Question
Returns BGP RIB entries.
```python
result = bfq.bgpRib().answer(snapshot="snap1").frame()
```
Columns: `Node`, `VRF`, `Network` (prefix), `Next_Hop_IP`, `Next_Hop_Interface`, `Origin_Protocol`, `Local_Pref`, `MED`, `Communities`, `AS_Path`, `Status`.

### routes Question
Returns the RIB (all protocols).
```python
result = bfq.routes().answer(snapshot="snap1").frame()
```
Columns: `Node`, `VRF`, `Network`, `Next_Hop_IP`, `Next_Hop_Interface`, `Protocol`, `Metric`, `Admin_Distance`, `Tag`.

### traceroute Question
Simulates packet forwarding from a source.
```python
from pybatfish.datamodel.flow import HeaderConstraints
result = bfq.traceroute(
    startLocation="@enter(r1[eth0])",
    headers=HeaderConstraints(srcIps="10.0.0.1", dstIps="192.168.1.0/24")
).answer(snapshot="snap1").frame()
```
**Disposition values (verified):**
- `ACCEPTED` — packet delivered to destination
- `DENIED_IN` — inbound ACL/policy denied
- `DENIED_OUT` — outbound ACL/policy denied
- `NO_ROUTE` — routing table lookup failed (black hole)
- `LOOP` — routing loop detected
- `INSUFFICIENT_INFO` — Batfish lacks info to determine outcome
- `EXITS_NETWORK` — packet exits the modeled network (expected for egress)
- `NEIGHBOR_UNREACHABLE` — next-hop unreachable at L2/L3

### reachability Question
Tests if packets can flow between endpoints.
```python
result = bfq.reachability(
    pathConstraints=PathConstraints(startLocation="r1"),
    headers=HeaderConstraints(srcIps="10.0.0.1", dstIps="10.0.0.2"),
    actions=["ACCEPTED"]
).answer(snapshot="snap1").frame()
```

### differentialReachability (snapshot pairs)
Compares reachability between two snapshots.
```python
bf.set_network("my_network")
result = bfq.differentialReachability(
    pathConstraints=PathConstraints(startLocation="/.*/ "),
    headers=HeaderConstraints(dstIps="0.0.0.0/0"),
    actions=["ACCEPTED"]
).answer(snapshot="post", reference_snapshot="pre").frame()
```

### searchFilters
Tests ACL/prefix-list behavior.
```python
result = bfq.searchFilters(
    filters="acl_name",
    action="permit",
    headers=HeaderConstraints(srcIps="10.0.0.0/8")
).answer(snapshot="snap1").frame()
```

## FRR-Specific Limitations (Verified in Lab)

### ACL / Prefix-list Parsing
**KNOWN LIMITATION**: Batfish does NOT model FRR-style `access-list` statements for BGP filtering. FRR uses a different ACL format from IOS. Symptoms:
- `searchFilters` returns empty or incorrect results for FRR ACLs
- BGP route filtering via FRR access-lists is not reflected in Batfish bgpRib

**Workaround**: Use `ip prefix-list` in FRR configs (IOS-style prefix-lists ARE parsed by Batfish). Alternatively, test filter dimension (D6) against IOS/Arista configs.

### FRR Route Maps
Route maps with `match ip address prefix-list` work. Route maps with `match ip address access-list` may not parse correctly.

### FRR next-hop rewrite levers — what IS and ISN'T modeled (live-verified on pinned digest, 2026-06-14)
**Tested on `batfish/allinone` `sha256:09817554db90…` (== `:nethelm`), lp_waypoint topology, by the oracle-engineer (NOT from memory — live bgpRib/traceroute reads):**
- **`route-map … / set ip next-hop <literal>` (outbound) IS MODELED.** A `set ip next-hop 10.0.0.X` on a border's iBGP-out route-map rewrites the advertised NEXT_HOP: src's bgpRib best route for the customer /24 changed from the eBGP /30 (`192.0.2.10`) to the rewritten literal (`10.0.0.2` / `10.0.0.3`), the route-map structures appear in `definedStructures`, parse = PASSED. Rewriting to a DIFFERENT egress's loopback (`10.0.0.3`=alt) deterministically (10×) flips the forwarding path src→way→dst ⇒ src→alt→dst, FIB next-hop count stays 1 (no D5). So a next-hop-literal rewrite CAN fire a clean, deterministic, pure D4+D10.
- **BUT it is degenerate, not a new mechanism.** Rewriting to the injecting border's OWN loopback (`set ip next-hop 10.0.0.2` on way→src) leaves the trace byte-identical (src→way→dst) — way is still on-path ⇒ D4 DEAD (the documented H2 live-kill). Rewriting to a *different* egress's loopback produces the SAME ground-truth signature as `lp_waypoint` (egress moves off way, D4+D10 fire, D5/D2/D3 empty, reachability preserved) — only the diff token differs (NH-literal vs LOCAL_PREF). Same oracle output, same difficulty class ⇒ taxonomy-inflating sibling, barred by the "every new scenario must be a NEW mechanism" rule.
- **`set ip next-hop unchanged` is PARTIALLY_UNRECOGNIZED (parse-dropped, NO-OP)** in the FRR dialect — byte-identical to baseline. The "next-hop-unchanged" framing is inexpressible here.
- **`neighbor X next-hop-self` is a NO-OP** even on a plain eBGP-readvertised route over iBGP (TEST A: NH stayed `192.0.2.10`, no rewrite) — not just on RR-reflected routes. Any next-hop-self-based quiet-reroute variant is therefore dead in the FRR/Batfish model; use the outbound `set ip next-hop <literal>` form (which IS modeled) if a rewrite is genuinely needed.
- **The only genuinely DISTINCT, gradeable next-hop member is the ELIMINATION variant** (`nexthop_self_quiet_reroute.md`): REMOVING the rewrite makes one of two paths unresolvable so the survivor wins by elimination, WITH a strict baseline MED/prepend discriminator above router-id to dodge the ECMP/D5 trap (equal-attribute PRE → Batfish MULTIPATHS, fib_nh=2, D4-already-violated-PRE + D5-on-collapse — live-confirmed). That is a SUBTRACTION, not the ADDITION/rewrite the "H9 next-hop rewrite" prompt describes ⇒ the rewrite-shift H9 is KILLED; spend the slot on the elimination form (tracked separately).

### FRR/Cumulus PBR is NOT modeled — all PBR stanzas are parse-dropped (verified empirically, 2026-06-14)
**KNOWN LIMITATION — kills any policy-based-routing / per-flow data-plane-override scenario (e.g. H4 PBR classifier drift) in the FRR track.**
- On the pinned digest `batfish/allinone` `sha256:09817554db90…` (== `:nethelm` == `:latest`), every FRR PBR stanza emits **"This syntax is unrecognized"** and is silently dropped: `pbr-map ... seq`, `nexthop-group`, `nexthop <ip>`, `match dscp`, `set nexthop`, `set nexthop-group`, and the interface `pbr-policy <map>`.
- Test was **format-fair**: the device file parsed as `CUMULUS_CONCATENATED` (the FRR vendor parser was engaged — the non-PBR peer nodes returned `PASSED`), and the PBR device returned `PARTIALLY_UNRECOGNIZED`. `definedStructures(nodes=<dev>)` shows only `interface` — **zero** PBR/nexthop-group structures. The `PBR_POLICY` named-structure specifier exists in Batfish only for **Cisco IOS / NX-OS** (`ip policy route-map`), never produced by the FRR parser.
- **Decisive data-plane test:** on a converged topology, `traceroute` with `HeaderConstraints(dscps=[0])` vs `dscps=[46])` returns **byte-identical** trace sets — DSCP marking (and any other PBR match field) has **zero** forwarding effect. Post-snapshot forwarding == pre-snapshot, so a waypoint (D4) check sees the intended transit node on the path in BOTH snapshots → **D4 can never fire**. The result is DEAD (blast radius = ∅), not a quiet miss.
- **Two compounding impossibilities for the "classifier (ACL/object-group/class-map) drift" premise:** (1) FRR PBR matches packet fields **inline** (`match src-ip/dst-ip/dscp/mark/...`), there is no ACL/object-group/class-map indirection to "drift"; (2) even the inline `match` is unmodeled. The premise is doubly inexpressible in the FRR dialect.
- **Oracle limit (independent):** the `ExtendedOracle` traceroutes are **destination-only** — all call sites pass `headers={"dstIps": dst_ip}` (oracle.py:143; extended_oracle.py:159,172,332). No `dscps`/`srcIps`/`ports`/`ipProtocols` threading. Grading a per-FLOW (5-tuple/DSCP) waypoint violation while ordinary flows still transit the waypoint would require a 5-tuple oracle extension that does not exist.
- **Verdict / workaround:** PBR / per-flow data-plane override is **NOT gradeable in the FRR track — KILL it there.** Gradeable substitutes: (i) VRF/route-leak steering of a source-scoped prefix (control-plane; already the leak family); or (ii) defer PBR to an **Arista cEOS / Cisco-IOS / NX-OS** snapshot where Batfish models `ip policy route-map` + `PBR_POLICY` in the data plane (verify empirically there before authoring, and add the 5-tuple oracle extension).

### MED comparability knobs are UNMODELED in FRR (verified in master source, 2026-06-14)
**KNOWN LIMITATION — kills any scenario whose lever is MED comparability eligibility.**
- `bgp always-compare-med` and `bgp deterministic-med` **PARSE but are DROPPED** in the FRR dialect. The tokens exist (`FrrLexer.g4` `ALWAYS_COMPARE_MED`; `Frr_bgp.g4` rule `rb_always_compare_med`) so the line does not error, but `FrrConfigurationBuilder.java` has **zero** enter/exit handlers for them (grep on master: 0 hits for `always_compare`/`AlwaysCompareMed`/`deterministic` across 2034 lines). Parsed-and-dropped → no-op. (`AlwaysCompareMed` IS modeled for the Cisco/Arista/IOS-XR/ASA/F5 representations — FRR only.)
- More fundamentally, Batfish's BGP best-path comparator **compares MED UNCONDITIONALLY across ASes**, with no same-leftmost-AS gate. `BgpRib.java:209` is a bare `Long.compare(lhs.getMetric(), rhs.getMetric())`. The code comment (lines ~200-207) is explicit: *"TODO: better support for MED rules. Most rules are currently not supported: normally this comparison is done only if the first AS is the same in both AS Paths; `always-compare-med` overrides above."* So **Batfish's default already behaves like `always-compare-med`.**
- **Consequence for blast-radius scenarios:** any mechanism that relies on the RFC 4271 §9.1.2.2(c) "MED only compared within the same neighbor AS" gate — including the proposed `always-compare-med-enable` quiet-reroute — is a **NULL oracle in FRR**. The pre-state (incomparable MEDs, waypoint wins on a later tie-break) never exists in the model because Batfish compares the MEDs at the MED step regardless of AS; PRE best-path is already the low-MED bypass; POST (flag added) is byte-identical because the flag is dropped. Blast radius = ∅. This is a *false-quiet bug*, not a quiet miss.
- **Verdict:** MED-comparability mechanisms are NOT gradeable in FRR. They would need a vendor (IOS/EOS/XR) baseline where the flag IS modeled — but even there Batfish's shared comparator gates MED on neither AS nor the flag, so the "incomparable→comparable flip" still would not reproduce. Treat MED-comparability as out-of-scope for the oracle until/unless Batfish implements the same-AS MED gate. (Mechanics confirmed against `batfish/batfish@master` `BgpRib.java`, `FrrConfigurationBuilder.java`, `FrrLexer.g4`, `Frr_bgp.g4` on 2026-06-14.) Real-network operational reality of MED oscillation is genuine — RFC 3345 (McPherson, Gill, Walton, Retana, Aug 2002) — it is the *oracle* that is blind, not the failure mode that is fake.

### ADD-PATH / additional-paths (RFC 7911) is INEXPRESSIBLE in FRR — sibling of the always-compare-med no-op (verified in master source, 2026-06-14)
**KNOWN LIMITATION — kills any scenario whose lever is BGP path-diversity advertisement (add-path / diverse-path).**
- `addpath-tx-all-paths`, `addpath-tx-bestpath-per-AS`, `bgp additional-paths send/receive` have **ZERO lexer tokens and ZERO parser rules** in the Batfish FRR dialect. Verified on `batfish/batfish@master`: `FrrLexer.g4` (1192 lines) contains no `addpath`/`additional`/`add-path` token — the only multipath/diversity tokens are `MAXIMUM_PATHS` (L315) and `MULTIPATH_RELAX` (L330); `Frr_bgp.g4` (564 lines) has no addpath/additional rule — the only multipath rules are `rbafi_maximum_paths` / `rbafi6_maximum_paths` (`MAXIMUM_PATHS (IBGP)? num NEWLINE`) and `rbbb_aspath_multipath_relax` (`AS_PATH MULTIPATH_RELAX NEWLINE`).
- Because there is no token AND no rule, the add-path line is **parsed-and-dropped with no error** (same failure class as always-compare-med, above). The pre/post snapshots are byte-identical → blast radius = ∅. This is a **false-quiet NULL oracle**, NOT a quiet miss: it passes `verify_determinism.py` trivially (empty == empty ≥10×) precisely because the oracle computes nothing.
- **Deeper structural reason it can never be a pure-quiet (D4+D10-only) scenario even if expressible:** the oracle DEFINES path diversity as the installed-FIB next-hop count (`extended_oracle.py:_nexthop_count` L187-189; `_redundancy_diff` fires iff `before > after >= 1`, L251-259; D10 `redundancy_floor` reduces to the same count). So a *forwarding* path-count drop is LOUD (fires D5 / D10-redundancy_floor) and a *non-forwarding backup* path loss leaves the single installed next-hop unchanged → D4 (forward-trace transit) and D10-waypoint stay EMPTY → nothing fires. There is no regime where "lost a backup path that was never the forwarding path" lands cleanly in D4+D10. `ExtendedBlastRadius` (`dimensions.py` L310-355) has no advertised / BGP-RIB / adj-rib-out path-SET cardinality element type — a per-client path-set diversity dimension would have to be built, and it is by construction NOT "D4+D10 only", so it cannot satisfy the pure-quiet constraint regardless.
- **The only FRR diversity primitive Batfish models is best-path-EQUAL multipath** (`maximum-paths` / `multipath-relax`). Collapsing it 2→1 IS gradeable, but it lowers the installed next-hop count → fires D5 → it is the already-built LOUD ECMP-collapse class (`clos_summary` / `ecmp4`), not a new quiet mechanism.
- **Verdict:** ADD-PATH-suppression is NOT gradeable in FRR (null oracle), and even forced into an expressible `maximum-paths 2→1` form it degenerates into the existing LOUD D5 ECMP-collapse class or the `rr-bestpath-reflect-flip` / igp-metric quiet BUILD family (path-count 1→1, egress flipped via OSPF cost) that already exists. It adds nothing distinct. Expressibility would require an Arista-EOS dialect (addpath IS in the EOS extractor; Batfish has dataplane `BgpAddPathNonEcmpBest`/`UniqueNextHop` tests) — but that breaks the all-FRR single-dialect baseline invariant AND still cannot produce a pure D4+D10 signature. The *operational* failure mode (RR + no add-path = clients have no hot backup, slow RR-mediated reconverge — route reflection ≈doubles post-failure convergence vs full mesh, arXiv:2503.15249; tier-1 RR meshes leave most routers with a single external route, "BGP Route Reflection Revisited") is REAL — see `../noc/rr_bestpath_hiding.md`. It is the *oracle* that is blind to it in FRR, not the failure mode that is fake.

### FRR OSPF inter-area summary (`area range`) — what IS and ISN'T modeled (live-verified on pinned digest, 2026-06-14)
**Tested on `batfish/allinone` `sha256:09817554db90…` (== `:nethelm`), 4-node multi-area design (src/wabr/babr/eg), by the oracle-engineer (live bgpRib/routes/traceroute reads, NOT memory):**
- **`area N range A.B.C.D/M cost C` (BARE `cost` form) IS MODELED.** Parses as
  `CUMULUS_CONCATENATED` with zero init issues; the summary appears at the remote node as
  `proto=ospfIA`. Changing the summary `cost` flips the remote node's installed inter-area
  next-hop (e.g. `192.0.2.2`(wabr) → `192.0.2.6`(babr)) and the forward trace
  (`src,wabr,eg` → `src,babr,eg`), both ACCEPTED. This drives **recursive resolution of an
  unchanged iBGP next-hop** — see `../noc/ospf_summary_cost_nexthop_reroute.md`.
- **Inter-area `/32` specifics are SUPPRESSED behind an `area range`.** `routes(src,
  <egress>/32)` returned rows = 0 with the range configured → the **summary is the LPM
  resolver** at remote nodes. This is the linchpin that makes the summary-cost lever
  distinct from the link-cost hot-potato lever.
- **EQUAL summary cost → LOUD.** With both inter-area costs equal (e.g. 100 == 100), the
  remote node installs **2 distinct next-hops** (ECMP) → **D5 fires.** The generator must
  hold a STRICT cost gap in both snapshots (verified to keep nh-count = 1).
- **`area ... range ... advertise cost C` (FRR-CURRENT idiomatic form) is UNRECOGNIZED**
  on this 11-month digest ("This syntax is unrecognized"). Use the BARE `cost` form here.
  **Re-verify on any digest bump** — this is a digest-pinned syntax dependency.
- **`default-information originate` is UNRECOGNIZED** in this FRR OSPF dialect → the
  default-route reroute flavour is NOT gradeable in FRR (parse-dropped, no-op).
- Determinism: `compute_extended_with_determinism_check(runs=10)` = byte-identical 10×,
  because the summary COST (a strict-gap OSPF metric) decides the inter-area route ABOVE
  any router-id tiebreak → exactly one installed route, no router-id/age multipath
  nondeterminism. Only equality (LOUD) loses determinism.

### Supported Config Formats
Batfish parses: Cisco IOS, Cisco IOS-XE, Cisco IOS-XR, Cisco NX-OS, Arista EOS, Juniper JunOS, Palo Alto PAN-OS, iptables, AWS VPC, Azure/GCP (limited), FRR (partial — see limitations above).

## Snapshot Directory Structure
```
snapshot_dir/
├── configs/
│   ├── r1.cfg   ← router config file (one per device)
│   ├── r2.cfg
│   └── ...
└── batfish/     ← optional: layer 1 topology, runtime data
    └── layer1_topology.json
```

## Layer 1 Topology (optional)
Required for correct link modeling on some topologies:
```json
{
  "edges": [
    {"node1": {"hostname": "r1", "interfaceName": "eth0"},
     "node2": {"hostname": "r2", "interfaceName": "eth0"}}
  ]
}
```

## Multi-Snapshot Workflow (Pre/Post Diff)
```python
bf.init_snapshot(pre_dir, name="pre")
bf.init_snapshot(post_dir, name="post")
# Question answered against "post", compared with "pre":
result = bfq.bgpSessionStatus().answer(snapshot="post", reference_snapshot="pre").frame()
```
For differential questions, only use questions that support the `reference_snapshot` parameter. bgpSessionStatus does NOT natively diff — use two separate `.answer()` calls and diff in Python.

## ExtendedOracle (NetHELM Custom)
Location: `oracle/extended.py`
`ExtendedOracle.compute(pre_dir, post_dir)` returns a dict with keys:
- `d1_sessions`: {"lost": [...], "gained": [...]}
- `d2_prefixes`: {"lost": [...], "gained": [...]}
- `d3_reachability`: {"lost": [...], "gained": [...]}
- `d4_waypoint`: {"violations": [...]}
- `d5_redundancy`: {"degraded": [...]}
- `d7_forwarding`: {"changed": [...]}
- `d6_filter`: not yet implemented (schema-only)
- `d8_scale`: not yet implemented (schema-only)

## Common Errors and Fixes
- `java.lang.OutOfMemoryError`: increase Docker memory (`--memory 8g`); large topologies need >4GB
- `BatfishException: No snapshot`: call `bf.init_snapshot()` before any question
- `KeyError: 'Established_Status'`: column name is case-sensitive; always check `.columns` first
- `Empty DataFrame`: snapshot parsed correctly but no sessions/routes exist; verify config syntax
- Model not started: `docker ps` to check; restart with `docker start batfish`
