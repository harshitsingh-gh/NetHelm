# OSPF Inter-Area Summary-Cost Quiet Reroute — an `area range cost` edit silently re-homes the recursive resolution of an unchanged BGP next-hop across a different ABR

## Mechanism (blast-radius relevant)

This is the **recursive-resolution** member of the IGP-underlay quiet-reroute family.
It is distinct from the link-metric hot-potato reroute (`igp_metric_hotpotato_quiet_reroute.md`):

- In the link-metric case, two iBGP paths are attribute-tied and BGP best-path falls
  through to RFC 4271 §9.1.2.2 step (e) — lowest IGP metric to the **NEXT_HOP** — so a
  link-cost edit makes BGP pick a **different egress / a different next-hop VALUE.**
- Here, BGP best-path is **byte-identical** pre/post: the same single iBGP route, the
  same NEXT_HOP (e.g. the egress router's loopback `172.20.2.9`), same LOCAL_PREF / MED /
  AS_PATH. **No BGP decision changes at all.** What changes is one layer down: which
  **internal route** the RIB uses to *recursively resolve that unchanged next-hop.*

The setup is a multi-area OSPF underlay with **two ABRs** (`wabr`, `babr`) connecting the
ingress area to the area that contains the BGP egress and its next-hop loopback. The
egress loopback's `/32` is **suppressed behind an `area N range A.B.C.D/M cost C`**
inter-area summary (Type-3 LSA) — so at the ingress router the **summary, not the `/32`,
is the longest-prefix-match that resolves the BGP next-hop.** A remote router's cost to
the summarized space is `(intra-area cost to the advertising ABR) + (the configured
summary cost C)`. Lower the summary cost on the bypass ABR (or raise it on the
waypoint ABR), and the recursion threads the SAME next-hop through the bypass ABR
instead of the waypoint ABR. Egress and reachability are unchanged; only the internal
path to reach the egress moved.

**Operational framing of the change:** retuning `area range cost` to steer which ABR a
remote area prefers is **documented, intentional traffic-engineering practice** — done
during dual-ABR consolidations, area redesigns, DC-pod migrations, and "prefer the
primary backbone uplink" tuning. It is low-ceremony underlay work that touches no BGP
config, so the egress-path side effect on a mandated transit/inspection node is exactly
the kind of second-order effect that slips review.

## Why this is a *quiet* (D4/D10-only) blast-radius event

1. **D1 = ∅** — an `area range cost` edit touches no BGP FSM and no OSPF adjacency
   (no MTU/area/network-type/passive change). All sessions stay ESTABLISHED.
2. **D2 = ∅** — the BGP prefix is BEST in every RIB pre and post; same mask, same
   attributes, same next-hop. Nothing withdrawn. (The egress `/32` was already
   suppressed behind the summary in BOTH snapshots — it is never the resolver, so its
   suppression is not a D2 event in the watch set.)
3. **D3 = ∅, D7 = ∅** — the bypass ABR genuinely delivers to the same egress; no
   blackhole, no loop. (Falsification gate: if the bypass cannot actually deliver, D3/D7
   fire and the instance is correctly disqualified as LOUD.)
4. **D5 = ∅ — IFF a STRICT summary-cost gap holds in BOTH snapshots.** This is the
   load-bearing purity constraint, identical in spirit to the link-metric case. If the
   two inter-area costs are **equal**, OSPF installs BOTH next-hops (ECMP width 2) →
   **D5 FIRES and D4 degrades to a mixed transit.** The generator MUST assert a strict
   (non-equal) resolved inter-area cost and exactly one installed next-hop in each
   snapshot. `maximum-paths 1` does not save you in the steady-state model — only a
   strict resolved-cost gap does.
5. **D4 fires** — all traces stop transiting the mandated ABR/waypoint.
   **D10 fires** — the "traffic to X MUST transit Y" invariant breaks.

Pure-quiet signature: nothing lost, withdrawn, blackholed, looped, or de-redundant;
traffic still arrives at the same egress; only the mandated transit node is silently
bypassed.

## Why this is a DISTINCT cause from its nearest neighbors

- **vs. link-metric hot-potato (`igp_metric_hotpotato_quiet_reroute.md`):** there the
  decisive change is BGP best-path step-(e) picking a **different next-hop**; here the
  next-hop is **identical** and only the recursive resolution of it moves. Different
  control-plane layer (RIB LPM recursion vs BGP best-path tiebreak). For a model under
  test the *prose* looks similar ("an OSPF cost changed"), but the protocol mechanism is
  genuinely different and the link costs are UNTOUCHED in this one.
- **vs. BGP `aggregate-address summary-only` (`aggregate_summary_collapses_te_specific.md`):**
  that suppresses a **BGP more-specific** so observer LPM falls back to a BGP aggregate
  on another egress — the arbiter is BGP-layer LPM and a BGP prefix disappears. Here no
  BGP prefix changes; the suppression is in the **OSPF** Type-3 summary and the decision
  is in **IGP recursive resolution.**
- **vs. redistribution AD shadow (`redistribution_ad_shadow_reroute.md`):** that is a
  cross-protocol AD contest (OSPF-110 steals from iBGP-200) re-sourcing the delivery
  route. Here there is no second protocol copy and no AD contest — one OSPF summary, one
  iBGP route, and the summary's *metric* moves the recursion.
- **vs. explicit `lp_waypoint`:** zero BGP surface; the diff is a single OSPF
  `area range cost` number.

## Real-world grounding

- **Mechanism — DOCUMENTED.** `area N range A.B.C.D/M cost C` sets the metric of the
  inter-area Type-3 summary LSA; a remote router's cost to that space = intra-area cost
  to the ABR + the summary cost. Tuning it to steer ABR preference is explicit vendor /
  design guidance:
  - Cisco "OSPF Inter-area route summarization" / OSPF design KB: the `cost` keyword on
    `area range` sets the summary metric; recommend pinning the summary cost manually (or
    via a loopback in the range) so it does not drift with intra-area changes.
    https://community.cisco.com/t5/networking-knowledge-base/ospf-inter-area-route-summarization/ta-p/3145113
  - Cisco "OSPF Design Best Practices": for multi-ABR areas, summarize on all ABRs;
    manually setting summary cost influences which ABR remote routers prefer; "use lower
    costs on the preferred ABR" to attract traffic to the primary backbone connection.
    https://community.cisco.com/t5/networking-knowledge-base/ospf-design-best-practices/ta-p/3112070
  - FRR OSPFv2 docs: `area (A.B.C.D|<0-4294967295>) range A.B.C.D/M [cost <0-16777215>]`.
    https://docs.frrouting.org/en/latest/ospfd.html
- **Summarization loses information → suboptimal paths / blackholes — DOCUMENTED.**
  ipSpace.net "OSPF Summarization and Split Areas": "Route summarization (regardless of
  the routing protocol) always results in information loss and potential suboptimal paths
  or black holes." The worked split-area example literally blackholes traffic toward the
  more-specific destinations once the summary hides them — the same information-loss
  mechanism that, in the quiet topology, re-homes recursion instead of dropping traffic.
  https://blog.ipspace.net/2024/03/ospf-split-areas-summarization/
- **Inter-area cost composition — DOCUMENTED.** networklessons / study-ccna: the inter-area
  best route is intra-area cost to the ABR plus the Type-3 LSA metric, so the summary cost
  is a first-class steering lever.

**Confidence note for the publication:** the mechanism (summary-cost sets the Type-3
metric; recursion re-homes; `/32` suppressed behind the range; summarization causes
suboptimal/blackhole side effects) is **DOCUMENTED**. A single *named public post-mortem*
of "an `area range cost` retune silently bypassed a mandated inspection/transit waypoint"
is **NOT located** — such events surface internally as "why is this flow no longer hitting
the scrubber/firewall" tickets, not published outages. Grounding confidence = **documented
for the mechanism; analogous for the specific waypoint-bypass framing.** Do NOT assert a
named outage. (Contrast the link-metric sibling, which additionally has peer-reviewed
*measured* grounding on AT&T/Sprint backbones — that one is the stronger-grounded member;
this one is the recursive-resolution variant grounded on vendor/design documentation.)

## Blast-radius mapping

- **D1 = ∅** — OSPF `area range cost` edit; no BGP FSM event, OSPF adjacency stays Full.
- **D2 = ∅** — BGP prefix stays best with identical next-hop; nothing withdrawn.
- **D3 = ∅, D7 = ∅** — bypass ABR delivers to the same egress; no blackhole/loop.
- **D5 = ∅** — STRICT resolved inter-area cost gap pre AND post → single installed
  next-hop. (HAZARD: equal summary cost fires D5/ECMP and pollutes D4. Generator MUST
  assert the strict gap and read back nh-count = 1; do not rely on `maximum-paths 1`.)
- **D4 = fires** — all traces stop transiting the mandated ABR/waypoint.
- **D10 = fires** — "traffic to X MUST transit Y" invariant broken.

## Generator / oracle constraints (load-bearing, live-verified by the oracle-engineer)

1. Baseline = multi-area OSPF underlay, two ABRs, BGP egress + next-hop loopback inside
   the far area, ZERO static resolvers.
2. The egress next-hop `/32` MUST be **suppressed behind the `area range`** so the
   summary is the LPM resolver at the ingress (verified: `routes(src, <egress>/32)` rows
   = 0). If the `/32` leaks, it (not the summary) resolves the next-hop and the
   summary-cost edit is vacuous.
3. Use the **bare `area N range A.B.C.D/M cost C` form** on the pinned digest. The
   FRR-current idiomatic `advertise cost C` form is UNRECOGNIZED on the 11-month digest
   (re-verify on any digest bump); `default-information originate` is UNRECOGNIZED
   (the default-route flavour is NOT gradeable in this FRR dialect).
4. Assert a **strict** resolved inter-area cost gap and exactly one installed next-hop in
   BOTH snapshots (verified: equal cost → nh-count = 2 → D5 LOUD).
5. Include a **no_op calibration control**: a summary-cost edit that does NOT cross the
   gap (waypoint ABR still wins) — prose-indistinguishable from the bypass, ground truth
   empty — to prove a passing model reasoned about recursive resolution rather than
   pattern-matching on "an OSPF cost line changed."

## Related
- `igp_metric_hotpotato_quiet_reroute.md` — the link-metric sibling (best-path step-(e),
  different egress; stronger peer-reviewed grounding).
- `aggregate_summary_collapses_te_specific.md` — BGP-layer summary-only LPM fallback.
- `redistribution_ad_shadow_reroute.md` — cross-protocol AD contest re-sourcing delivery.
- `../batfish/batfish_verified_facts.md` — digest-pinned FRR OSPF syntax facts.
