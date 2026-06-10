# Hyperscaler Data Center Fabric Design (Clos / Leaf-Spine / 5-Stage)

## Why this file exists
NetHELM blast-radius scenarios must be grounded in how mega-scale DCs are ACTUALLY
built, not in textbook two-spine toy fabrics. The structural properties below
(ECMP width, no-summarization underlay, per-tier ASN, RR-vs-mesh, add-path) are
what make a change either surgical or catastrophic. The companion file
`hyperscaler_dc_failure_modes.md` maps specific changes to blast (D1–D8); this file
is the design substrate those scenarios sit on. The canonical NetHELM dimensions are
D1–D8 (see `../batfish/blast_radius_patterns.md`); the briefing's "D1–D9" is treated
as D1–D8 here — there is no D9 defined in the corpus, do not invent one.

---

## 1. The Clos / fat-tree underlay — what the topology buys you

A folded Clos (a.k.a. fat-tree / leaf-spine) is a multi-stage non-blocking
topology built from small fixed-radix merchant-silicon switches. Stages:

- **3-stage**: ToR (leaf) ↔ spine. Single pod.
- **5-stage**: ToR (Tier-3) ↔ aggregation/fabric (Tier-2) ↔ spine/super-spine
  (Tier-1). Pods interconnected by a spine tier.

RFC 7938 §3 describes exactly this and uses the 5-stage Clos as its running example;
it notes "Clos topologies that have more than 5 stages are very uncommon."
[RFC 7938 §3](https://datatracker.ietf.org/doc/html/rfc7938)

**The blast-radius-relevant invariant:** in a clean (symmetric) Clos every leaf
reaches every other leaf via *all* spines with equal cost. So:

- Draining **one spine of N** removes 1/N of bisection capacity — a CAPACITY event,
  not a reachability event, IF wiring is symmetric.
- If wiring is **asymmetric** (a spine is cabled to only a subset of leaves, or a
  pod is under-built), draining that spine can **partition** the subset that
  depended on it. This is the trap: "it's just a spine, we have N of them" is only
  true under symmetry.

RFC 7938 §3.2.2 states the structural fact that makes summarization dangerous:
"Tier 1 switches have exactly one path to every server in this topology."
[RFC 7938 §3.2.2](https://datatracker.ietf.org/doc/html/rfc7938)

---

## 2. Google Jupiter — scale and the spine-heterogeneity trap

Google's Jupiter is the canonical published mega-fabric. Numbers (Google Cloud blog,
"The evolution of Google's Jupiter data center network"):

- 2015 generation: >30,000 servers, 40 Gb/s per server, >1 Pb/s aggregate.
- 2022: >6 Pb/s of datacenter bandwidth.
- Three original pillars: SDN (logically centralized control), Clos topology, and
  merchant switch silicon.
- Control plane: **Orion** SDN control plane; routing evolved from Valiant Load
  Balancing to dynamic traffic engineering (techniques from the B4 WAN).
[Google Cloud blog](https://cloud.google.com/blog/topics/systems/the-evolution-of-googles-jupiter-data-center-network)
[Jupiter Rising, SIGCOMM 2015](https://conferences.sigcomm.org/sigcomm/2015/pdf/papers/p183.pdf)
[Jupiter Evolving, SIGCOMM 2022](https://web.stanford.edu/class/cs244/papers/poutievski-sigcomm22.pdf)

**The blast-radius lesson from Jupiter's own design motivation:** Google explicitly
calls out that a classic Clos spine forces uniformity — "Clos topologies inherently
require all-to-all fanout from aggregation blocks to the spine; adding to the spine
incrementally would require rewiring the entire data center." Their cited
heterogeneity example: a new 200 Gb/s aggregation block connected to 3 old 100 Gb/s
spine blocks and 1 new 200 Gb/s spine block runs "only 25% of the links … at
200Gb/s." Mixed-speed fabrics create **asymmetric capacity**, which is the precondition
for the "drain one spine → unexpected congestion/partition" failure. Jupiter's later
move to Apollo Optical Circuit Switches (MEMS mirrors) removes the rigid spine
entirely — but most enterprises and most of the other hyperscalers still run rigid
electrical Clos. [Google Cloud blog, same URL].

---

## 3. Meta data center fabric — pods, planes, and HGRID

Meta's published fabric design (Engineering at Meta):

- Original "data center fabric" (2014): pod-based; each pod has a set of fabric
  switches; "spine planes" interconnect pods. The pod is the unit of capacity.
  [Meta 2014](https://engineering.fb.com/2014/11/14/production-engineering/introducing-data-center-fabric-the-next-generation-facebook-data-center-network/)
- **F16 / Minipack (2019)**: each rack connects to **16 separate planes**; ToR has
  1.6T up / 1.6T down. Per pod: **sixteen 128-port 100G fabric switches**, replacing
  the previous four 400G — "3x fewer fabric chips, going from 48 infra switches per
  pod to only 16 per pod." Minipack = 128x100GE, single 12.8T ASIC (Broadcom TH3).
- **HGRID**: building-scale aggregation layer; scales to six buildings per region,
  each with a full F16 fabric. Same disaggregated principles as **Fabric Aggregator**.
- Hop counts (deterministic by design): same-fabric best case six hops;
  building-to-building flows "always take eight hops."
[Meta F16/Minipack](https://engineering.fb.com/2019/03/14/data-center-engineering/f16-minipack/)
[Fabric Aggregator](https://engineering.fb.com/2018/03/20/data-center-engineering/fabric-aggregator-a-flexible-solution-to-our-traffic-demand/)

**The "16 planes" detail is blast-radius gold:** at Meta scale a "spine" is really 16
independent planes. Losing one plane is ~1/16 capacity. But a config push (a CI/
automation job) that targets "all switches in plane role X" can hit all 16 planes at
once if the targeting selector is wrong — the disaggregated, automated design is what
turns a single bad template into a whole-fabric event. This is the structural reason
Meta's own Oct-2021 global outage (cross-referenced; see
`../noc/facebook_bgp_outage_oct2021.md`, **do not duplicate**) had unbounded blast:
a single backbone command, not a single device.

---

## 4. Microsoft Azure / AWS — what is public

- **Azure**: runs a global WAN (IGP + BGP, multi-vendor) feeding regional DC
  fabrics. The Jan-2023 outage (detailed in the failure-modes file) is the public
  window into how a single WAN-router command triggers fabric-wide IGP recompute and
  BGP churn. [Network World](https://www.networkworld.com/article/971873/global-microsoft-cloud-service-outage-traced-to-rapid-bgp-router-updates.html)
- **AWS**: less topology is public, but the Dec-2021 us-east-1 event reveals the
  architecture: a **separate internal network** hosting "monitoring, internal DNS,
  authorization, and EC2 control plane components," connected to the main network
  "through dedicated networking devices." That seam is a blast-radius boundary — see
  failure-modes file. [AWS message 12721](https://aws.amazon.com/message/12721/)

These two confirm a general hyperscaler property: **the control/management plane
rides dedicated devices/links that are themselves a single failure domain**, and the
tooling used to recover depends on them (same lesson as Meta Oct-2021 and Rogers
`../noc/rogers_canada_outage_jul2022.md`).

---

## 5. BGP in the DC (RFC 7938) — the design rules that govern blast radius

RFC 7938 ("Use of BGP for Routing in Large-Scale Data Centers", Aug 2016) is the
operator bible for the eBGP-underlay design Meta/Microsoft/Cumulus/Arista shops run.
The rules that matter for scenarios:

- **eBGP-only underlay** (§5.1). Each device is its own AS; no IGP needed for the
  underlay. A failure is masked "as soon as the BGP speaker finds an alternate path"
  given Clos symmetry. [RFC 7938 §5.1].
- **Per-tier ASN scheme** (§5.2.1): one shared ASN across all Tier-1 (spine) devices;
  a unique ASN per Tier-2 set per cluster; a unique ASN per Tier-3 (ToR). This is
  deliberate — eBGP's AS-path loop prevention is what stops microloops/path-hunting
  in the Clos. (§5.2.2 covers `Allowas-in` to work around the 1023-private-ASN limit.)
  [RFC 7938 §5.2].
  - **Blast-radius implication:** because ToRs share-or-don't-share ASNs by design,
    a wrong ASN or a stray `allowas-in` can re-open loop paths the design closed.
- **ECMP / multipath is mandatory and wide** (§6.1–6.2): "multipath relax" /
  "multipath multiple-AS" must be on (eBGP multipath across different neighbor ASNs);
  ECMP fan-out scales with radix — "ECMP fan-out of 32 would be required when
  building a Clos network using 64-port devices." [RFC 7938 §6].
  - **Blast-radius implication:** if `maximum-paths` is left at the default 1, the
    fabric silently collapses to single-path — capacity and redundancy (D5) gone with
    sessions/prefixes (D1/D2) untouched. A classic "looks fine, isn't" change.
- **DO NOT SUMMARIZE the underlay** (§5.2.3, explicit): "Summarizing subnets in a
  Clos topology results in route black-holing under a single link failure (e.g.,
  between Tier 2 and Tier 3 devices), and hence must be avoided." The mechanism (see
  §6 of failure-modes file): the summary stays valid at the aggregator even after a
  leaf becomes unreachable via it, so other leaves keep hauling traffic to a spine
  that drops it. [RFC 7938 §5.2.3].
- **Fast fallover** (§7.1): eBGP sessions are torn down on link-down in ms; this is
  the primary convergence mechanism (BFD augments it).

Operator corroboration that summarization is simply avoided at scale:
[ipSpace "Avoid Summarization in Leaf-and-Spine Fabrics"](https://blog.ipspace.net/2018/06/avoid-summarization-in-leaf-and-spine/).

---

## 6. Overlay stack (EVPN/VXLAN, add-path, anycast) — properties for scenarios

The L3 underlay above carries a BGP-EVPN/VXLAN overlay in most modern fabrics. Deep
EVPN mechanics and failure patterns are in `../rfcs/evpn_vxlan_dc.md` (**do not
duplicate**); the blast-radius-relevant fabric properties:

- **Spines as EVPN route reflectors.** Spines commonly RR the overlay. A spine RR
  loss is redundancy (D5) not reachability if ≥2 RRs; loss of the *last* RR cluster
  is overlay-wide D2/D3. (See `../rfcs/evpn_vxlan_dc.md` spine-failure pattern.)
- **Add-path is what preserves ECMP/anycast through an RR.** Without RFC 7911
  add-path, an RR advertises only its single best path, so RR clients lose path
  diversity even though multiple equal paths exist; anycast services need multiple
  paths advertised to ECMP-balance.
  [ipSpace add-path](https://blog.ipspace.net/2021/12/bgp-multipath-addpath/),
  [RFC 7911].
  - **Blast-radius implication:** removing/forgetting `additional-paths send` on an
    RR silently halves anycast capacity and kills fast reconvergence — D5/D7 with
    D1/D2 clean. Another "looks fine, isn't."
- **Route-target / route-distinguisher are the tenant-isolation knobs.** An RT typo
  is the EVPN equivalent of a route leak (cross-VRF) or a silent partition (tenant
  can't reach itself across pods). Auto-derived RTs (`ASN:VNI`) mismatch the moment
  two fabrics with different ASNs are stitched.
  [ipSpace multi-pod RT tshoot](https://blog.ipspace.net/2025/11/evpn-multi-pod-tshoot-rt/).
- **Anycast (services + anycast gateway) depends on ECMP width.** Anycast prefixes
  are advertised from many VTEPs; the fabric must ECMP them. Lose ECMP (e.g.,
  `maximum-paths 1`, or add-path off) → all anycast traffic homes to one instance.
  [Anycast in the DC](https://www.dnzydn.com/2023/08/04/anycast-inside-the-data-centers/).
- **RPKI/ROV lives at the DC EDGE, not the fabric.** Underlay/overlay are private AS
  space; RPKI matters where the DC peers the Internet (the edge/PE routers). Treat
  RPKI-invalid scenarios as edge scenarios, not fabric scenarios. (See
  `../rfcs/bgp_security_rpki.md`.)

---

## 7. Forwarding-table scale (TCAM/FIB) — the hard ceiling

Merchant silicon has a *fixed* FIB; RIB is bounded only by DRAM. This asymmetry is a
whole failure class (detailed in failure-modes §3):

- Broadcom Trident 2 (≈90% of merchant leaf/spine for years): ~64k–72k IPv4 / ~20k–36k
  IPv6 FIB entries, with Unified Forwarding Table partitioning to trade host-route vs
  LPM space. Tomahawk/Trident 3, Jericho/Qumran (external TCAM) raise the ceiling, but
  the ceiling is always *finite and silent*.
  [STORDIS FIB scaling](https://stordis.com/scaling-the-forwarding-information-base-on-merchant-silicon/),
  [ipSpace Trident 2 / Nexus 9500](https://blog.ipspace.net/2014/06/trident-2-chipset-and-nexus-9500/).
- **Blast-radius implication:** a change that grows installed routes past the FIB
  profile (de-aggregation, full-table leak into the fabric, a too-big leaf summary,
  an EVPN type-2 explosion from MAC churn) causes **FIB-overflow → routes punted to
  slow path or dropped** while the RIB (and Batfish's modeled RIB) looks perfectly
  healthy. This is the DC-internal cousin of 512k/768k-day. This is a D8 (scale)
  event and is exactly the Rogers class (`../noc/rogers_canada_outage_jul2022.md`)
  re-cast at fabric scale.

---

## 8. Quick reference: structural property → why it changes blast radius

| Property (as actually deployed) | Safe-looking change that bites | Dim |
|---|---|---|
| N spines, symmetric wiring | "drain one spine" — fine IF symmetric, partition if not | D3/D5/D8 |
| 16 planes (Meta F16), automated push | one bad template hits all planes via bad selector | D1–D3 fabric-wide |
| eBGP per-tier ASN, AS-path loop-prevention | stray `allowas-in` / wrong ASN re-opens loops | D7 (loops) |
| `maximum-paths`/multipath-relax required | default `maximum-paths 1` → silent single-path | D5/D7 |
| No underlay summarization (RFC 7938 §5.2.3) | "tidy up" with a summary → blackhole on link fail | D3 |
| Spine = EVPN RR + add-path | drop add-path → anycast/ECMP diversity gone | D5/D7 |
| Auto RT = ASN:VNI | stitch two ASNs → RT mismatch → tenant partition | D2/D3 |
| Fixed FIB (Trident ~64–72k v4) | route growth past profile → FIB overflow | D8 |
| Dedicated mgmt/control network (AWS, Meta) | break it → also break the recovery tooling | recovery time |

---

## References (primary first)
- [RFC 7938 — Use of BGP for Routing in Large-Scale Data Centers](https://datatracker.ietf.org/doc/html/rfc7938)
- [Jupiter Rising, SIGCOMM 2015](https://conferences.sigcomm.org/sigcomm/2015/pdf/papers/p183.pdf)
- [Jupiter Evolving, SIGCOMM 2022 (PDF)](https://web.stanford.edu/class/cs244/papers/poutievski-sigcomm22.pdf)
- [Google Cloud blog — evolution of Jupiter](https://cloud.google.com/blog/topics/systems/the-evolution-of-googles-jupiter-data-center-network)
- [Meta — data center fabric (2014)](https://engineering.fb.com/2014/11/14/production-engineering/introducing-data-center-fabric-the-next-generation-facebook-data-center-network/)
- [Meta — F16 & Minipack (2019)](https://engineering.fb.com/2019/03/14/data-center-engineering/f16-minipack/)
- [Meta — Fabric Aggregator (2018)](https://engineering.fb.com/2018/03/20/data-center-engineering/fabric-aggregator-a-flexible-solution-to-our-traffic-demand/)
- [RFC 7911 — Advertisement of Multiple Paths in BGP (add-path)](https://datatracker.ietf.org/doc/html/rfc7911)
- [ipSpace — Avoid Summarization in Leaf-and-Spine](https://blog.ipspace.net/2018/06/avoid-summarization-in-leaf-and-spine/)
- [ipSpace — BGP add-path / multipath](https://blog.ipspace.net/2021/12/bgp-multipath-addpath/)
- [STORDIS — FIB scaling on merchant silicon](https://stordis.com/scaling-the-forwarding-information-base-on-merchant-silicon/)
- Cross-refs (internal, do not duplicate): `../noc/facebook_bgp_outage_oct2021.md`,
  `../noc/rogers_canada_outage_jul2022.md`, `../rfcs/evpn_vxlan_dc.md`,
  `../rfcs/bgp_security_rpki.md`, `../batfish/blast_radius_patterns.md`.
