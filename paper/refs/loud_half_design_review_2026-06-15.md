<!-- Loud-half second design-lens (network-architect) review, 2026-06-15, run wf_ce54807f-1bd, 19 agents. Follow-up to scenario_validity_audit_2026-06-15.md (which gave the loud half oracle-lens only). -->

# NetBrace — Loud-Half Second-Lens (Design) Audit

## (1) Verdict

The loud half **largely holds up** under the design lens — 7 of 11 families are `CORRECT_IDIOMATIC` and converge to the declared ground truth via the declared mechanism (verified live on the pinned Batfish digest, not merely parsed). But **three families carry real design defects that survived the 2026-06-15 oracle audit**, and they cluster in one place: the **offline `--oracle fake` validation path tests the WRONG dimension for the two scenarios that are the *sole* validators of their dimension** — ecmp4 (D5 redundancy) and waypoint4 (D4 waypoint) both emit a D3-reachability key in `fake_oracle.py:303-307`, so the offline gate gives false confidence in plumbing it never exercises. The same stale-branch bug leaves `blackhole` emitting D3-only after its radius was corrected to D1x2+D2+D3+D7 in commit c7c12c1. Separately, `ecmp4` realizes its D5 instance with two bare static routes (no BGP/IGP multipath decision), and `square4`'s `remove_network` default combo is a baked-in false-quiet (pure D9, mis-graded as zero radius by the main-RIB-only v0 oracle). The static-route-as-IGP crutch recurs across ipc/square4/mgmt but is — except in ecmp4 — a *disclosed, load-bearing* fixture, not an accidental flaw. None of the seven clean families are wrong; the benchmark teaches correct routing where it grades correctly. The exception is ecmp4, where the one D5 instance is non-idiomatic *and* its offline gate is broken — that pairing is the most serious item.

## (2) Per-family design verdict

| Family | Verdict | One-line reason |
|---|---|---|
| leak_ms_reroute | CORRECT_IDIOMATIC | Converges + fires GT; IP-impersonation mechanism is design-faithful (D4 is the true signal) but under-disclosed vs blackhole. |
| lp_waypoint | CORRECT_IDIOMATIC | Canonical all-eBGP `generator_lp` is clean; static crutch correctly DEPRECATED + walled off. |
| **ipc** | **MAJOR_ISSUES** | Dead `next-hop-self` on client+origin in an all-iBGP AS (377/405); static loopback mesh substitutes for IGP (disclosed-acceptable). |
| scale_deagg | CORRECT_IDIOMATIC | Mechanism sound; `100.{b}` pool mislabeled RFC6598 and D3=∅ justification is vacuous (cosmetic). |
| clos_summary | CORRECT_IDIOMATIC | Static-discard summary is the *correct* choice (dynamic aggregate would withdraw and destroy the trap); reason is load-bearing but only implied. |
| mgmt_lockout | CORRECT_IDIOMATIC | GT correct + deterministic when isolated; verification pointer hits a flaky runner; `next-hop-self` inert (harmless). |
| blackhole | CORRECT_IDIOMATIC | Live-verified D1/D2/D3/D7 via the documented mechanism; **but its fake-oracle branch is stale (D3-only)**. |
| **ecmp4** | **MAJOR_ISSUES** | Sole D5 instance built from bare statics (not BGP/IGP multipath); **fake oracle fires D3 not D5** — offline gate never tests redundancy. |
| waypoint4 | CORRECT_IDIOMATIC (instance) | Live oracle correct; **fake-oracle branch fires D3 not D4** — same mirror-consistency bug class. |
| ospf_core6 | CORRECT_IDIOMATIC | iBGP+OSPF recursion is idiomatic; docstring self-contradicts on `network` + dead file cross-refs (frozen text only). |
| **square4** | **MAJOR_ISSUES** | AD=1 static mesh makes iBGP forwarding-decorative; **`remove_network` default = pure D9, mis-graded zero by v0 oracle** (the benchmark's own pathology, shipped as a default). |

## (3) CONFIRMED blocking/major design defects (consolidated)

All verified against live code at commit `c7c12c1` (path: `netbrace/reporting/fake_oracle.py`, not the synthesis-cited path — finding still stands).

**M-1 (major) — ecmp4 offline gate validates the wrong dimension.** `fake_oracle.py:303-307` bundles `ecmp4` with `square4`/`waypoint4` and emits a `reachability` (D3) key. The live `ExtendedOracle` fires **D5 redundancy** for ecmp4 and leaves D3 empty (`scenarios.py:191-192` sets `reachability_flows == redundancy_targets`, so `reachability_flows` is a *silent anchor*). The offline `--oracle fake` sweep therefore never exercises the redundancy keyset/aggregation/semantic-set path for the **only** D5 scenario.
*Fix (code now):* split ecmp4 out; for `(node,prefix) in scn.redundancy_targets` emit `redundancy|node=…|vrf=default|prefix=…` byte-matching `RedundancyLoss.key` (`dimensions.py:93`); drop the D3 add. Add a unit assertion that fake GT for ecmp4 has non-empty `redundancy` and empty `reachability`.

**M-2 (major) — waypoint4 offline gate validates the wrong dimension.** Same branch (:303-307): emits D3, live oracle emits **D4 waypoint** with D3 empty (`scenarios.py:154-155`). Same false-confidence class that c7c12c1 fixed for clos_summary/leak_ms/scale_deagg — waypoint4 was missed.
*Fix (code now):* split waypoint4 out; for `(s,d,w) in scn.waypoint_intents` emit `waypoint|src=…|dst=…|via=…|vrf=default`; drop the reachability add. Keep square4 on the D3 anchor.

**M-3 (major) — ecmp4 realizes D5 with bare statics, not a multipath decision.** Two static routes stand in for BGP/IGP multipath, contradicting the catalog's leaf-spine-fabric billing (catalog:225 lists D5,7,4; the static toy fires D5-only). The benchmark's *sole* D5 ground truth is built by the very crutch it flags elsewhere.
*Fix (code, can defer past v1 only if labelled):* add a canonical eBGP-DC D5 instance on the clos_summary machinery (`maximum-paths 2` + `bestpath as-path multipath-relax`, two distinct-ASN spines originating the /32, router-ids pinned to loopbacks); losing change = tear one session or `maximum-paths 2→1`. The `routes()` next-hop count still grades 2→1, so the D5 grader is unchanged. Keep the static ecmp4 as a labelled-DEPRECATED anchor, exactly as lp_waypoint's crutch was handled.

**M-4 (major) — square4 `remove_network` is a shipped false-quiet.** `generator.py:42` ships `remove_network` in the *default* intents. Under the AD=1 static full mesh, BGP never installs to the main RIB, so removing a `network` statement is a pure **D9** (BGP-RIB best-path withdrawal) with zero main-RIB effect — and the v0 `BatfishOracle` (main-RIB only) grades it **zero blast radius**. A default-shipped combo whose GT is empty/wrong.
*Fix (code now):* route `remove_network` through `ExtendedOracle` with `bgp_watch_prefixes` (D9), OR drop it from the `generator.py:42` default + `_combos` until it is. Add a regression test asserting `remove_network` GT is non-empty.

**M-5 (minor→fix-now, same class) — blackhole fake-oracle branch stale.** `blackhole` (square4-blackhole) has no dedicated branch and falls into the `square4` group (:303), emitting D3-only — violating the "structurally representative" contract after c7c12c1 corrected its radius to D1x2+D2+D3+D7.
*Fix (code now):* split blackhole out and emit D1={(r1,10.0.0.4),(r4,10.0.0.1)}, D2={(r1,10.0.0.4/32)}, D3={(r1,10.0.0.4/32)}, D7={(r1,blackhole,10.0.0.4/32)}, mirroring the live oracle. Same fix class already applied to three other branches; blackhole was missed.

**m-6 (minor) — ipc dead `next-hop-self`.** `generator_ipc.py:377` (client→RR) and `:405` (origin→RR) emit `next-hop-self` in an all-iBGP single-AS family where no router re-originates eBGP into iBGP — inert dead config (RFC 4456). Generator-only; baselines frozen → document.

## (4) Code change now vs documentation note

**Code change now (offline-gate correctness — these are the load-bearing ones):**
- M-1 ecmp4 → emit D5 redundancy key in `fake_oracle.py`, drop D3, + unit assertion.
- M-2 waypoint4 → emit D4 waypoint key, drop D3.
- M-5 blackhole → split out, emit corrected D1/D2/D3/D7 structural shape.
- M-4 square4 `remove_network` → route through ExtendedOracle/D9 or drop from the default; add non-empty-GT regression test.
- m-6 ipc → remove the two dead `next-hop-self` lines (377/405), generator-only.

**Code change now or labelled-defer (design idiom — but must not ship as the silent D5 truth):**
- M-3 ecmp4 → add the eBGP-DC multipath D5 instance as canonical; keep static as labelled-DEPRECATED. If deferred past v1, the DEPRECATED label and a docstring stating "this static instance masks the multipath/multipathConsistency facet the catalog advertises" are **mandatory now**.

**Documentation-only (frozen surfaces / disclosed fixtures — no GT impact):** square4 static-mesh-as-IGP and inert next-hop-self framing; ipc static loopback mesh disclosure; leak_ms IP-impersonation determinism disclosure (closes gauntlet-2 #53) + committed `oracle_verify_leak_*` artifact; scale_deagg `100.{b}`→RFC6598 constraint and the vacuous-D3 rewording; clos_summary "why not aggregate-address summary-only" sentence + the 3.2.2/5.2.3 cite; mgmt_lockout verification-pointer repoint; ospf_core6 `network`-wording + dead `scenario_ospf_core6.py` cross-refs.

**Bottom line:** the seven clean families are publication-grade. The four flagged families are fixable without touching frozen v0 core except where explicitly routed to the audit's existing B1/D9 work. The single highest-priority item is the **ecmp4 pair** (M-1 + M-3): the benchmark's only D5 dimension is both non-idiomatically constructed and offline-untested — fix both before any number that cites D5 ships.

Relevant files: `/home/harshitsingh/projects/NetHelm/netbrace/reporting/fake_oracle.py` (M-1,M-2,M-5 at :303-307), `/home/harshitsingh/projects/NetHelm/netbrace/tasks/safety/generator.py:42` (M-4), `/home/harshitsingh/projects/NetHelm/netbrace/tasks/safety/baseline_ecmp4.py` + `/home/harshitsingh/projects/NetHelm/netbrace/tasks/safety/scenarios.py:183-192` (M-3), `/home/harshitsingh/projects/NetHelm/netbrace/tasks/safety/generator_ipc.py:377,405` (m-6).
