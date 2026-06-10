# Hyperscaler DC Failure Modes → Blast-Radius Mapping

## Purpose
Real change/failure → blast mappings at DATA-CENTER scale, each tied to a real
incident or authoritative source and mapped to the NetHELM dimensions D1–D8
(definitions in `../batfish/blast_radius_patterns.md`). These are the scenarios that
distinguish a serious blast-radius benchmark from a toy "shut a neighbor" set: the
ones with second-order effects, where a change that looks safe isn't.

> Note on dimensions: the corpus defines **D1–D8**. The briefing said "D1–D9"; there
> is no D9 — mappings below use D1–D8. D8 = scale/resource overflow.
>
> Accuracy discipline (cf. the Rogers correction in
> `../noc/rogers_canada_outage_jul2022.md`): each entry states what is *confirmed by
> the cited source* vs. what is *general mechanism / operational lore*. Do not state
> reconstructed detail as fact.

---

## 1. Automation / CI fat-finger pushed fleet-wide (the #1 hyperscaler blast)

**The mechanism (confirmed pattern, multiple sources).** Hyperscale fabrics are
configured by automation (templates + a rollout system), not by hand. The blast
radius of a config change is therefore determined by the **rollout selector**, not by
one device. A wrong selector, a bad template variable, or a change that passes
per-device validation but is wrong *in aggregate* hits every device matching the
selector simultaneously.

- **Meta, Oct 4 2021** is the canonical real instance: a single backbone command
  intended to assess capacity withdrew the backbone globally. Blast = entire AS32934
  (~140k prefixes), DNS, auth, and the recovery tooling itself. Full writeup +
  dimension mapping already in `../noc/facebook_bgp_outage_oct2021.md` — **cross-ref,
  do not duplicate.** Class lesson: a backbone/automation change has **unbounded**
  blast because everything depends on it.
- **Industry baseline:** Uptime Institute attributes two-thirds to four-fifths of
  incidents to human error, and configuration/change management is repeatedly the
  most frequent network-outage cause.
  [Data Center Outage causes (Uptime cited)](https://andcable.com/cable-management/data-center-outage-causes-prevention/)

**Blast / dimensions:** scales with selector. Worst case D1–D3 fabric-wide + recovery
time. The valuable scenario is the **canary trap**: a change that is correct on the
canary leaf but wrong fleet-wide (e.g., a route-map that depends on a neighbor that
only some leaves have), so it passes the canary and detonates on rollout.

**Batfish modellability:** HIGH for the *static* effect — apply the templated change
to the snapshot and diff RIB/FIB/sessions across all nodes. Batfish is in fact a good
proxy for the "validate the aggregate, not just one device" lesson.

---

## 2. WAN/backbone command with vendor-divergent behavior → IGP recompute storm + BGP flap (Azure, Jan 25 2023)

**Confirmed root cause (Microsoft PIR, via Kentik/ThousandEyes/Network World).** A
planned change to update an IP address on a WAN router: "a command given to the
router caused it to send messages to all other routers in the WAN, which resulted in
all of them recomputing their adjacency and forwarding tables." It was "a standard
command with different behaviors on different router models … issued outside of
standard procedures," causing **all WAN routers in the IGP domain to recompute
reachability.**
[Network World](https://www.networkworld.com/article/971873/global-microsoft-cloud-service-outage-traced-to-rapid-bgp-router-updates.html)
[Kentik analysis](https://www.kentik.com/blog/digging-into-the-recent-azure-outage/)

**The cascade (BGP-visible, from Kentik):**
- IGP-wide recompute → BGP prefixes "withdrawn completely and then almost immediately
  readvertised … repeated several times," i.e. **route flap / churn**, not a clean
  withdrawal.
- Kentik observed e.g. 20.47.42.0/24 (centralindia) withdrawn 07:12 UTC, restored
  10:36 UTC; ~104 of 370+ AS8075 prefixes saw no impact (partial blast).
- Transit share rose (Arelion/Lumen/GTT/Vocus) as peering paths dropped — traffic
  shifted to transit (D7).
- Secondary self-inflicted **route leak/origination** 07:42–07:48 UTC: AS8075
  announced prefixes it shouldn't (e.g., space overlapping T-Mobile), mostly
  contained to Australia. [Kentik, same URL].

**Dimensions:** D2 (intermittent withdraw/readvertise), D7 (path shift peering→transit),
D3 (packet loss windows), partial-blast (not all prefixes). The triggering edit is a
**D6-class change** (a single command) with a **fabric-wide D2/D7 blast** via IGP
recompute. The vendor-divergent-command angle is the scenario hook: the SAME command
is benign on vendor A, catastrophic on vendor B.

**Batfish modellability:** PARTIAL. Batfish models the post-change steady state
(adjacencies/forwarding) but NOT the transient flap/oscillation or the runtime
"command behaves differently per model." Score the steady-state delta; flag the
transient as live-only.

---

## 3. FIB / TCAM exhaustion at fabric scale (D8 — the Rogers class, re-cast in the DC)

**Mechanism (confirmed hardware fact).** Merchant silicon FIB is fixed and small
relative to RIB. Trident 2 (~90% of merchant leaf/spine for years): ~64k–72k IPv4 /
~20k–36k IPv6 FIB entries; UFT partitioning trades host vs LPM space. Exceeding the
profile → routes punted to slow path or dropped, while RIB looks healthy.
[STORDIS](https://stordis.com/scaling-the-forwarding-information-base-on-merchant-silicon/)
[ipSpace Trident 2](https://blog.ipspace.net/2014/06/trident-2-chipset-and-nexus-9500/)
[Noction 768k/TCAM](https://www.noction.com/blog/768k-day-512k-tcam)

**Changes that trigger it:**
- De-aggregation (a peer/leaf starts originating /32s instead of a summary).
- A full Internet table (or another VRF's table) leaked into the fabric VRF.
- EVPN type-2 (MAC/IP) explosion from a MAC-move/flap storm filling host-route space.
- Raising a leaf's advertised specifics fleet-wide.

**Real grounding:** Rogers Jul 2022 is the flagship real-world overload/crash event
(filter *removal* → route flood → core capacity exceeded → crash). Detailed +
corrected in `../noc/rogers_canada_outage_jul2022.md` — **cross-ref, do not
duplicate.** The DC instance is the same dimension (D8) with a FIB rather than a
control-plane-memory ceiling.

**Dimensions:** D8 primary; D2/D3 as routes silently fail to install; D1 only if the
device crashes/resets as a consequence (Rogers) — not as the trigger.

**Batfish modellability:** Batfish gives the route COUNT; the FIB ceiling is a *spec*
annotation per device. Score count-vs-limit threshold (a D8 oracle), NOT which
specific routes the hardware evicts (that is live/platform-dependent).

---

## 4. Underlay route summarization → blackhole on link failure (RFC 7938 §5.2.3)

**Confirmed mechanism (RFC + operator).** RFC 7938 §5.2.3: "Summarizing subnets in a
Clos topology results in route black-holing under a single link failure … and hence
must be avoided." ipSpace gives the concrete chain: when spines advertise a summary
(or default) and leaf specifics aren't propagated leaf-to-leaf, after an L1–S1 link
fails "no routing update is sent to other leaves, and they continue sending the
traffic as they did before … toward S1 … where the traffic will be dropped because S1
has no route for prefixes advertised by L1."
[RFC 7938 §5.2.3](https://datatracker.ietf.org/doc/html/rfc7938)
[ipSpace](https://blog.ipspace.net/2018/06/avoid-summarization-in-leaf-and-spine/)

**The trap:** the change ("summarize at the aggregation tier to save FIB / tidy the
table") looks like a *best practice* import from enterprise/WAN design. In a Clos it
is the opposite — it creates a silent blackhole that only manifests on a *subsequent*
link failure. Two-step: change is benign until a second event.

**Dimensions:** the summarization change itself = D6 (and arguably reduces D2 churn,
looking *beneficial*). The blast appears only when a link fails: D3 (blackhole) for
the leaves behind the failed link, with D2 on the device showing the summary still
present (the lie: prefix "present" but unreachable). Excellent test of whether a model
understands conditional/second-order blast.

**Batfish modellability:** HIGH and ideal — model summary-applied snapshot, then a
link-failure snapshot, and traceroute shows blackhole while the summary route persists
in RIB. This is a strong two-snapshot scenario.

---

## 5. Microloops & convergence transients at Clos scale

**Mechanism (confirmed; well-documented class).** During reconvergence, neighboring
nodes can briefly disagree on the path, forming transient forwarding loops
(microloops) until all FIBs update. In a Clos the eBGP per-tier ASN scheme and
AS-path loop prevention (RFC 7938 §5.2) suppress *persistent* loops, but transient
microloops still occur on link/node up/down. See `../noc/microloop_and_transient_blackholes.md`
(general treatment — cross-ref, do not duplicate). There is even patent literature on
reducing microloops in eBGP Clos networks.
[USPTO 10574566 — reducing microloops in eBGP Clos](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10574566)

**The DC-specific trap:** a change that *re-opens* loop paths the design closed —
e.g., adding `allowas-in`/`as-override` on a ToR (to "fix" a route that the AS-path
filter was correctly dropping), or assigning a duplicate/wrong ASN so loop prevention
no longer discriminates. Now a transient microloop can become a *persistent* loop.

**Dimensions:** D7 (forwarding path / loop) primary; D3 (traffic dropped in the loop,
TTL-expiry). D1/D2 typically clean — the sessions are up and the prefix is "present,"
which is exactly why this is hard.

**Batfish modellability:** Batfish detects forwarding LOOP disposition on traceroute
for *persistent* loops (the `allowas-in` case is modellable). Sub-second *transient*
microloops during convergence are timing-dependent → live-only.

---

## 6. ECMP / multipath inconsistency — silent loss of width and diversity

**Mechanism (confirmed; RFC 7938 §6 + add-path docs).** The fabric depends on wide
ECMP and on add-path through RRs. Two safe-looking changes silently collapse it:
- Leaving/reverting `maximum-paths` to the default **1** (multipath off), or dropping
  `bgp bestpath as-path multipath-relax` so cross-ASN equal paths no longer install
  as ECMP. RFC 7938 §6.2 makes multipath mandatory. [RFC 7938 §6](https://datatracker.ietf.org/doc/html/rfc7938)
- Removing `additional-paths send` on a spine/RR: clients drop to a single best path,
  killing anycast balance and backup-path fast reconvergence.
  [ipSpace add-path](https://blog.ipspace.net/2021/12/bgp-multipath-addpath/)
  [Anycast in the DC](https://www.dnzydn.com/2023/08/04/anycast-inside-the-data-centers/)

**The trap:** zero change to sessions (D1=0) and zero change to prefix presence
(D2=0). The fabric "looks identical." But bisection capacity drops by the ECMP factor
and there's no longer a hot backup path — so the NEXT link failure that ECMP used to
absorb now causes a full reconverge/drop. Capacity + resilience gone invisibly.

**Dimensions:** D5 (redundancy N→1), D7 (all traffic homes to one path); D8 in effect
(capacity), but D1/D2/D3 clean until a follow-on failure.

**Batfish modellability:** PARTIAL/GOOD. Batfish shows the number of installed
best/ECMP routes for a prefix and the multipath set; diffing pre/post reveals the
collapse from N next-hops to 1. Anycast/runtime hashing is not modeled.

---

## 7. EVPN/VXLAN control-plane mistakes (RT/RD, type-3, MAC churn)

Deep mechanics in `../rfcs/evpn_vxlan_dc.md` (cross-ref, do not duplicate). The
blast-radius-worthy DC instances:
- **Route-target mismatch** (typo, or auto-RT `ASN:VNI` mismatch when stitching two
  fabrics with different ASNs): tenant MAC/IP (type-2) not imported on the remote pod
  → **silent partition** of a tenant across pods. Sessions up, no error.
  [ipSpace multi-pod RT tshoot](https://blog.ipspace.net/2025/11/evpn-multi-pod-tshoot-rt/)
- **Type-3 (inclusive-multicast) missing/filtered** for a VNI: BUM/ARP not flooded →
  first-packet/ARP-resolution failures for new flows.
- **MAC-move / duplicate-MAC storm**: drives type-2 churn → control-plane load + FIB
  host-route growth (feeds §3). NX-OS default dup-detection: 5 moves / 180 s.
  [Cisco NX-OS VXLAN dup-detect](https://www.cisco.com/c/en/us/td/docs/switches/datacenter/nexus9000/sw/7-x/vxlan/configuration/guide/b_Cisco_Nexus_9000_Series_NX-OS_VXLAN_Configuration_Guide_7x/b_Cisco_Nexus_9000_Series_NX-OS_VXLAN_Configuration_Guide_7x_chapter_0100.html)

**Dimensions:** D2/D3 for RT mismatch (per-tenant partition), with D1 clean (the
"silent failure" property is the whole point). D8 for MAC-churn-driven host-route
growth.

**Batfish modellability:** PARTIAL — Batfish has partial EVPN support (session status
yes; type-2 maybe; type-3/4/5 limited; VXLAN data-plane not modeled). RT mismatch may
be detectable as a missing import; the data-plane partition needs lab/live. See
`../rfcs/evpn_vxlan_dc.md` for exact limits.

---

## 8. Control/management-plane dependency loops (AWS Dec 2021; Cloudflare Nov 2023)

**AWS us-east-1, Dec 7 2021 (confirmed, AWS message 12721).** An automated scaling
activity in the main network triggered "a large surge of connection activity that
overwhelmed the networking devices between the internal network and the main AWS
network." Internal network hosts "monitoring, internal DNS, authorization, and EC2
control plane components." Congestion → latency/errors → more retries → feedback loop.
Critically, "monitoring data was still not visible to our operations team so they had
to continue resolving the issue with reduced system visibility." Fix included
"additional network configuration that protects potentially impacted networking
devices."
[AWS message 12721](https://aws.amazon.com/message/12721/)

**Cloudflare control-plane outage, Nov 2 2023 (confirmed, CF blog).** A utility power
event + failing UPS + faulty breakers took down the PDX-04 facility holding CF's
largest analytics cluster and >1/3 of the HA cluster. Control plane / dashboard / API
down ~Nov 2 11:44 → Nov 4 04:25 UTC; **data plane (proxy/CDN) kept serving** — the
blast was confined to control plane because of plane separation, but recovery was
slow due to facility/HA-cluster concentration.
[Cloudflare post-mortem](https://blog.cloudflare.com/post-mortem-on-cloudflare-control-plane-and-analytics-outage/)

**Dimension framing:** these are not single-prefix BGP scenarios; they are
**blast-radius-boundary / dependency** scenarios. The lesson for NetHELM scenario
design: a change to the control/management network has blast = "everything that
depends on it, including the tools used to fix it" — the same recovery-time
amplification seen in Meta Oct-2021 and Rogers Jul-2022. Model as a dependency/
single-failure-domain annotation, not as a RIB diff.

**Batfish modellability:** LOW for the congestion/feedback dynamics and power events;
these are not control-plane-config scenarios. Use them to justify a dependency/
single-failure-domain dimension, not as Batfish-graded items.

---

## Summary table: change → trap → blast → dimension → real grounding → Batfish

| # | Change | The trap ("looks safe") | Primary blast | Dims | Real grounding | Batfish |
|---|---|---|---|---|---|---|
| 1 | Templated config pushed fleet-wide | passes canary, wrong in aggregate | fabric-wide loss | D1–D3 | Meta Oct-2021 | HIGH (static) |
| 2 | WAN router command (IP change) | "standard" command, vendor-divergent | IGP recompute + BGP flap, path shift | D2,D7,D3 | Azure Jan-2023 | PARTIAL |
| 3 | De-agg / leak / MAC explosion | RIB fine, FIB silently overflows | routes don't install / crash | D8,(D2,D3) | Rogers (class) + Trident FIB | count-vs-limit |
| 4 | Summarize at aggregation tier | "best practice," reduces table | blackhole on later link fail | D6 then D3 | RFC 7938 §5.2.3 | HIGH (2-snap) |
| 5 | `allowas-in`/dup ASN to "fix" a route | one route returns | persistent microloop | D7,D3 | RFC 7938 §5.2 + microloop file | persistent: yes |
| 6 | revert `maximum-paths`/drop add-path | sessions+prefixes identical | ECMP width & backup gone | D5,D7 | RFC 7938 §6 / add-path | PARTIAL/GOOD |
| 7 | EVPN RT/RD typo or auto-RT stitch | sessions up, no error | tenant partition across pods | D2,D3 | ipSpace multi-pod RT | PARTIAL |
| 8 | change to mgmt/control network | "it's just management" | breaks svc + recovery tooling | recovery | AWS Dec-2021, CF Nov-2023 | LOW |

---

## References (primary first)
- [AWS — Summary of the AWS Service Event in US-EAST-1 (Dec 2021)](https://aws.amazon.com/message/12721/)
- [Cloudflare — Control Plane and Analytics Outage post-mortem (Nov 2023)](https://blog.cloudflare.com/post-mortem-on-cloudflare-control-plane-and-analytics-outage/)
- [RFC 7938 §5.2.3 / §6 — summarization & ECMP](https://datatracker.ietf.org/doc/html/rfc7938)
- [Kentik — Digging into the Azure outage (Jan 2023)](https://www.kentik.com/blog/digging-into-the-recent-azure-outage/)
- [Network World — Azure outage / rapid BGP updates](https://www.networkworld.com/article/971873/global-microsoft-cloud-service-outage-traced-to-rapid-bgp-router-updates.html)
- [STORDIS — FIB scaling on merchant silicon](https://stordis.com/scaling-the-forwarding-information-base-on-merchant-silicon/)
- [Noction — 768k day / TCAM overflow](https://www.noction.com/blog/768k-day-512k-tcam)
- [ipSpace — Avoid summarization in leaf-spine](https://blog.ipspace.net/2018/06/avoid-summarization-in-leaf-and-spine/)
- [ipSpace — BGP add-path/multipath](https://blog.ipspace.net/2021/12/bgp-multipath-addpath/)
- [ipSpace — multi-pod EVPN RT troubleshooting](https://blog.ipspace.net/2025/11/evpn-multi-pod-tshoot-rt/)
- [USPTO 10574566 — reducing microloops in eBGP Clos](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10574566)
- Cross-refs (internal): `../noc/facebook_bgp_outage_oct2021.md`,
  `../noc/rogers_canada_outage_jul2022.md`,
  `../noc/microloop_and_transient_blackholes.md`, `../rfcs/evpn_vxlan_dc.md`,
  `../rfcs/bgp_security_rpki.md`, `../batfish/blast_radius_patterns.md`,
  `./hyperscaler_fabric_design.md`.
