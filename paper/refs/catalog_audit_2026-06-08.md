# Blast-Radius Catalog — Fleet Audit & Synthesis (2026-06-08)

> Two fleet subagents (Max plan) audited `blast_radius_scenario_catalog.md` before
> we scale to the question base. **noc-veteran** = realism / necessity / real-world
> frequency. **industry-expert** = 2026 currency / modern stack. Both grounded in
> the KB + live web research. This file is the synthesis + the build decision.

## Where they AGREE (act on immediately — uncontroversial)

1. **Mechanisms in the 20 are correct; the multi-dimensional D1–D8 framing is the
   genuine novelty.** No outright nonsense. The sins are redundancy + a couple of
   over-claimed oracles + a dated technology *mix*.
2. **Merge redundant scenarios** (don't inflate the count):
   - **S04 (ACL reorder) → instance of S03** (same header-space mechanism).
   - **S14 (spine drain) → instance of S06** (same ECMP-removal mechanism).
3. **Fix over-claimed oracles (honesty ledger):**
   - **S13**: Batfish models steady state — score suboptimal best-path + `detectLoops`,
     **do NOT claim oscillation** (that's LIVE).
   - **S20**: score the **D8 route-count threshold**, **not** which prefixes a TCAM
     evicts (Batfish can't know that).
4. **Report as failure-CLASSES × parameterized generators, not a raw "200–400"
   count.** Reviewers respect "N mechanistically distinct classes, frequency-weighted
   instances" and distrust "312 scenarios" (invites "how many are trivial dupes?").
   Both experts independently said this. Target ≈ **180–250 graded instances** from
   **~20–26 classes**, weighted by real-world frequency + parameter richness.
5. **Add a `route-validity` typed element to D6** (VALID / INVALID / NOT_FOUND) and
   an **IGP-type / data-plane tag** — the scoring surface must cover the modern stack.
6. **Citation fixes (load-bearing):** NetPress → **NetArena** (arXiv:2506.03231 was
   retitled); NetConfBench → **draft-01**; NIKA → **640 incidents / 5 scenarios /
   54 issues** (repo `zhihao1998/LLM4NetLab`). Add modern RFCs to refs now (7432,
   9136, 9252, 7938, 8950, 8402, 8667, 8665, 9234, 7911, 7908 + ASPA drafts).
7. **New classes both implicitly bless** (cheap, gradeable, grounded):
   - **Management-plane / OOB lockout** — "does the change sever NOC-jumphost →
     device mgmt-IP?" = a clean `differentialReachability` query. Grounded in
     Facebook 2021 + Cloudflare Jun 2022. **noc-veteran's standout new idea:
     novel, cheap, viscerally real.**

## The frequency-weighted SPINE (noc-veteran's ranked real killers)

All statically Batfish-gradeable, all grounded in a named outage, all where LLMs
demonstrably fail:

| Rank | Failure class | Real grounding | ~instances |
|---|---|---|---|
| 1 | **Internal routing-policy collapse** (route-map/filter withdraws prefixes the backbone needs; sessions stay UP, RIB empties) | **Rogers Jul 2022, Facebook Oct 2021** | 8–12 |
| 2 | **Route leak / more-specific / RPKI-invalid** (pure D4/D7; session+prefix count give NO signal — justifies the whole multi-dim thesis) | Cloudflare 2019, Telekom Malaysia 2015 | 6–10 |
| 3 | **next-hop-self / recursive-resolution silent killer** (S08 generalized) | Operational lore; Rogers pattern | 5–6 |
| 4 | **RR / cluster failure** (S01) | iBGP scaling design | 6–8 |
| 5 | **local-pref/MED "empty blast" trap** (S10 — the documented LLM failure mode: models wrongly predict session loss on attribute changes) | `network_change_management.md` | 6–8 |
| 6 | **ACL / VRF segmentation delta** (S03 + S07, S04 absorbed — Batfish-beats-humans showpiece) | NIKA / Forward Networks | 8–10 |
| 7 | **Anycast withdrawal** (S16 = Cloudflare Jun 2022, non-linear blast) | `cloudflare_dc_outage_jun2022.md` | 4–6 |
| 8 | **Management-plane lockout** (new) | Facebook 2021 / Cloudflare 2022 | 3–4 |

**Second wave (still gradeable):** max-prefix teardown (3–4), OSPF area/MTU (S05/S12),
recursive blackhole (S15), prefix-list ordering/implicit-deny traps (4–6), BFD-risk
*classification* (3–4, config-reasoning not steady-state delta).

**noc-veteran says REJECT for v1:** chasing a 300+ raw count; SRv6/TI-LFA; MLAG/L2;
NTP/cert; deep EVPN Type-2 mobility; any scenario whose only interesting effect is
LIVE-only (PMTUD, stateful-FW, transient microloop) until the static spine is done.

## The modern-stack push (industry-expert)

Verdict: **STALE as a 2026 *mix* — not wrong, but a 2015 textbook.** A reviewer from
ETH NSG / KTH / a hyperscaler will note the absence of the three things they operate:

- **P0 EVPN/VXLAN fabric** (Type-2/5, RT/RD, ESI multihoming, IRB) — 40–60 instances.
  FRR 10.6 supports it → **live-gradeable** (Batfish can't).
- **P0 RPKI/ROV + RFC 9234 roles/OTC + ASPA** (production in ARIN/RIPE Dec'25–Jan'26)
  — 30–45. Route-validity as a first-class blast element. **HYBRID** (ROA annotation
  + own validity calc, or live Routinator/FRR).
- **P1 Segment Routing (SR-MPLS/SRv6/TI-LFA/SR-TE)** — 25–40. SRGB mismatch, prefix-SID
  collision, SR-TE waypoint removal. FRR 10.6 has SRv6/RFC 9252 + TI-LFA.
- **P1 automation/intent as an INPUT-FORMAT axis** (same scenario as CLI vs
  YANG/NETCONF vs declarative intent) — novel + cheap, layer over existing scenarios.
- **P2 IPv6/dual-stack** — variant axis, not a family.
- Add **IS-IS** scenarios (zero today; IS-IS is the dominant SP/SR IGP).

## THE COLLISION (the one real fork — for Harshit)

**noc-veteran:** defer SRv6 + deep EVPN; the LIVE-only modern stack eats the build
budget for signal the oracle can't produce deterministically; ship the static
BGP-policy spine where LLMs demonstrably fail.

**industry-expert:** EVPN/RPKI/SR are *mandatory* for 2026 credibility, and the
FRR 10.6 live oracle in the lab CAN grade them.

**Both are right within their lane.** The tiebreaker is oracle determinism + build
cost + what makes the *first* paper strongest, vs. what makes it look current.

### My synthesis / recommended resolution
- **v1 spine = the 8 frequency-weighted static classes above** (rock-solid Batfish
  determinism, the LLM-failure finding, ships fast). This is the paper's core.
- **+ a credibility layer that is cheap AND gradeable:** fold in **RPKI/ROV
  route-validity** (it IS the modern face of the route-leak class #2 — clean typed
  element, HYBRID via ROA annotation) and a **modest EVPN Type-5 RT-leak set**
  (maps onto the VRF-leak class #6 we already keep; small, live-FRR-gradeable).
- **Defer to v2:** SRv6 / SR-TE / TI-LFA, deep EVPN Type-2 mobility, and all
  LIVE-only-transient effects — stated reason: oracle determinism + first-paper
  focus + budget, not lack of importance.
- **Adopt now regardless:** all the AGREE items (merges, oracle-honesty fixes,
  class×generator framing, route-validity element, mgmt-lockout class, citation
  fixes). The input-format axis = a fast follow after the spine.

This keeps the NOC veteran's "static spine where LLMs fail, don't chase volume" AND
takes the industry expert's "add RPKI + a touch of EVPN + fix the dated framing +
generator framing" — deferring only the genuinely expensive/weak-oracle modern
stack, with the deferral reasoned.

**Open decision for Harshit:** how much modern stack in v1 (see chat question).
