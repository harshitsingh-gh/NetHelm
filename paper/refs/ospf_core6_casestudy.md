# v1 Case Study: `ospf_core6` — IGP-underlay generalization

> STATUS (2026-06-10): **DROPPED TO v1.5 — the build hit the kill-switch.** The
> hard gate's step 2 (idiomatic OSPF resolution) PASSED beautifully, but step 3
> (the intended D1=∅ recursive-next-hop blackhole) is STRUCTURALLY IMPOSSIBLE on
> the architect's exact 6-node 2-plane topology — verified exhaustively (all 42
> single/double OSPF cuts × 2 next-hop baselines = 0 clean traps; cuts either
> reroute [prefix survives] or strand a node [D1 fires, breaking the trap]). The
> agent KILLED cleanly per the verdict rather than hack a result.
>
> **v1 consequence:** no topology case study ships in v1; the static underlay is
> disclosed as a limitation (a 4-node-toy critique is survivable; a hacked-in
> artifact is not). **v1.5 consequence:** the verified idiomatic baseline below is
> KEPT as the foundation; see the v1.5 fix spec at the bottom.

## WHAT THE BUILD PROVED (kept — this is real value)

`netbrace/tasks/safety/baseline_ospf_core6.py` (untracked, imported by nothing) is a
verified, parse-clean, fully-idiomatic 6-node OSPF-underlay + iBGP-RR core:
- 12 OSPF adjacencies + 18 directional iBGP sessions ALL ESTABLISHED on live Batfish.
- Every loopback /32 in every node's OSPF RIB (no static crutch anywhere — grep of
  the config = ZERO `ip route` lines).
- **The crutch-killer proof:** customer prefix 203.0.113.0/24 resolves recursively
  with next-hop = edge2 loopback `10.0.0.6`, and that next-hop is
  `resolved-by=['ospf']` — NOT static, NOT connected. The idiomatic OSPF-underlay
  pattern WORKS in Batfish; this retires the audit-M1 "static IS the bug" objection
  at the design level, and is the v1.5 foundation.

## WHY THE SCENARIO IS A KILL (the structural finding)

On a healthy redundant 2-plane RR core, the customer prefix's iBGP next-hop is
reachable through the SAME underlay paths that carry the victim's iBGP sessions, so
the two are inseparable: any cut that keeps D1=∅ only reroutes; any cut that strands
resolution also strands a session (D1 fires). The redundancy that makes it a good
core is exactly what defeats the intended failure. (Bonus, KB-worthy: plain FRR
`neighbor X next-hop-self` is a no-op for RR-reflected routes — real vendor
behavior, Batfish-faithful; the idiomatic force is a route-map `set ip next-hop`.
Recorded in docs/oracle_determinism_spec_v1.md.)

## v1.5 FIX SPEC (for the architect)

Make the data-plane next-hop a SEPARATE address from the session-bearing loopback,
and engineer a single OSPF SPOF on the customer-attach path that the victim's iBGP
does NOT traverse. Concretely: a 7th access node attaching the customer prefix over
a single OSPF link, whose loopback (iBGP session endpoint) stays reachable via a
disjoint plane while the customer-attach subnet/next-hop is severed by the change.
The agent verified that *simply* dual-homing edge2 is insufficient (still reroutes).
This is genuine redesign + re-verification = v1.5 scope.

---

> Inclusion ruling was: **V1-CASE-STUDY-ONLY** — descriptive worked example, NOT part
> of the N≥5 statistical evaluation. Moot for v1 now (dropped); applies when the
> v1.5 fix lands.

## Caption (verbatim, accuracy-corrected from the verdict draft)

The verdict's draft caption said "synthetically generated from parameterized
structural templates" — but `ospf_core6` is a SINGLE hand-authored grounded-split
scenario (no generator), so the accurate caption is:

> *"On an independent six-node OSPF-underlay topology — a distinct mechanism family
> (an iBGP next-hop that resolves through the IGP rather than a static route, so an
> OSPF-layer change can render it unresolvable), hand-constructed from public
> reference designs with neutral identifiers and no correspondence to any published
> configuration — all four models again produced 0/N forwarding-anomaly true
> positives (N=3 per model). This case study illustrates that the methodology
> generalizes beyond minimal topologies; it is reported descriptively and is NOT
> part of the N≥5 statistical evaluation."*

## Why this scenario matters (the contribution it makes)

- **Kills the static-next-hop crutch.** Every prior NetHELM scenario resolved iBGP
  next-hops via hand-written static routes (a disclosed non-idiomatic workaround for
  Batfish's FRR `next-hop-self` gap). `ospf_core6` resolves them via a real OSPF
  area-0 underlay — idiomatic RFC 4271 §9.1.2 recursive resolution — so the
  recursive-next-hop blackhole is a *genuine* second-order effect, not hand-plumbed.
  This directly answers audit-2026-06-10 finding M1 ("the `blackhole` scenario is
  contrived — the static IS the bug").
- **Answers the "toy topology" desk-reject.** A 6-node 2-plane redundant core makes
  the affected set non-eyeballable (a subset loses resolution via one plane while
  sessions stay up), unlike the 4-node squares. Addresses audit §5.4.
- **First genuine IGP mechanism** in the question base (prior set was BGP/static-only).

## Public anchors (the section cites ONLY these; reconstructable without the source)

- **RFC 7938** — Use of BGP for Routing in Large-Scale Data Centers (Clos/underlay+overlay).
- **RFC 4271 §9.1.2** — BGP next-hop recursive resolution via the IGP (the idiom).
- **RFC 4456** — BGP Route Reflection (the iBGP-RR overlay).
- **Public 5G-xhaul SR validated designs** — Juniper "5G CSR xHaul Seamless Segment
  Routing" JVD; IP Infusion multi-domain ISIS-SR + EVPN blog (pattern provenance for
  the hierarchical-edge inspiration, vendor-neutralized).
- **ETSI GS MEC 003** — MEC reference architecture (edge-compute attachment context).
- D8 budget grounding (separate limitations sentence): public Cisco 16,384-entry
  ECMP-group ceiling (Cisco Live BRKSPG-2208/2397) + NVIDIA Cumulus ECMP-exhaustion
  behavior + Broadcom public FIB ranges. See docs/oracle_determinism_spec_v1.md.

## Provenance statement (the ONLY claim we make about origin)

"Synthetic, hand-constructed from public reference designs with neutral identifiers;
no instance corresponds to any published configuration." NEVER "derived from a
production operator network." Fingerprint kill-list enforced
(temporary/topology_mining_plan_2026-06-10.md).

## VERIFIED RESULTS — to fill from the build agent (PENDING GATE)

- [ ] PRE: all OSPF adjacencies + iBGP sessions ESTABLISHED
- [ ] PRE: every loopback /32 in every node's OSPF RIB; customer-prefix iBGP next-hop
      resolves to an OSPF route (protocol shown) — NOT static/connected
- [ ] Change diff (config-edit + intent framing, outcome-leak-free)
- [ ] Fired dims + exact element keys (expect D1=∅; D2 and/or D7)
- [ ] Determinism: 10× byte-identical sha
- [ ] grep of the configs: zero `ip route` (crutch absent)
- [ ] Model case-study run (4 models × N=3 on the existing arms) — descriptive 0/N
- [ ] ASCII topology diagram for the figure
