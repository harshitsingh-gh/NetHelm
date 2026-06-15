# BGP FlowSpec Redirect — Per-Flow Quiet Path-Bypass (mechanism, grading limits, real-world grounding)

## Mechanism (blast-radius relevant)

BGP FlowSpec (RFC 8955, obsoletes RFC 5575) distributes traffic-filtering /
traffic-engineering rules via BGP NLRI. A rule matches a flow by **5-tuple-ish
criteria** (dst-prefix, src-prefix, IP-protocol, dst/src port, and others) and applies
an **action** carried as an extended community. The actions are: rate-limit (0x8006),
traffic-action/sample (0x8007), **redirect-to-VRF** (0x8008, rt-redirect AS-2octet),
and **redirect-to-IP next-hop** (0x8108 / draft-ietf-idr-flowspec-redirect-ip — an
RFC-track follow-on for networks without L3VPN). DDoS scrubbing is the dominant
operational use: a NOC operator originates a FlowSpec rule that **redirects only the
attacked flow** into a clean VRF (whose default route points at the scrubbing
appliance) or to the scrubber's IP next-hop, while *all other traffic to the same
destination keeps its normal path*.

The **quiet-half hazard**: a redirect rule (or a stale redirect rule that was never
withdrawn after an attack subsided) silently steers the victim flow off its mandated
path — e.g. away from an inspection / DPI / LI-tap / firewall waypoint — while the
destination stays fully reachable via the bypass. The object invariant (sessions,
prefixes, reachability, loop-freedom) is preserved; only the **path predicate for one
flow** changes: the network still proves "dst reachable" but silently stops proving
"dst reachable THROUGH the mandated waypoint." Per-flow (sub-prefix) selectivity makes
this *purer* than any prefix-level reroute — other flows to the same prefix are
untouched, so D2/D3/D5/D7 cannot fire even partially.

## Blast-radius mapping (intended, real-world)

- **D1 = ∅** — FlowSpec is a separate AFI/SAFI (AFI 1/2, SAFI 133/134); originating a
  FlowSpec NLRI does NOT touch the IPv4/IPv6-unicast BGP FSM. No session drops.
- **D2 = ∅** — no unicast prefix is withdrawn; the redirect is a forwarding action, not
  a RIB change for the destination prefix.
- **D3 = ∅, D7 = ∅** — the bypass/scrubber forwards the flow on to the destination;
  reachability preserved, no blackhole/loop (assuming the redirect NH is live and the
  scrubber passes clean traffic).
- **D5 = ∅** — a single redirect next-hop; BGP best-path for the prefix is unchanged.
- **D4 fires** — the redirected flow stops transiting the mandated waypoint.
- **D10 fires** — "traffic to X (this flow) MUST transit Y" invariant broken.

## Why it is a DISTINCT mechanism (not a variant of the quiet-reroute family)

The decisive diff is **below BGP best-path, in the data plane, and per-flow**:

- vs `igp_metric_hotpotato_quiet_reroute` / `med_driven_quiet_reroute` /
  `lp_waypoint` / `rr_bestpath_hiding` / `nexthop_self_quiet_reroute`: every one of
  those flips the **BGP best-path for the whole prefix** by changing an attribute or an
  IGP/next-hop resolution. FlowSpec redirect leaves BGP best-path **identical** and
  overrides only the FIB for **one matched flow**. Other flows to the same prefix are
  unaffected — this is the novel **per-flow / sub-prefix** axis no other mechanism has.
- vs `community_triggered_remote_action`: closest cousin (a BGP-propagated remote
  policy action), but that is a coarse policy knob; FlowSpec adds 5-tuple flow
  granularity and a data-plane redirect.

## Real-world grounding (VERIFIED — confidence labelled)

- **FlowSpec redirect is real and deployed for DDoS scrubbing diversion**
  (documented). redirect-to-VRF: RFC 8955 §7.4 / ext-community 0x8008. redirect-to-IP:
  draft-ietf-idr-flowspec-redirect-ip (RFC-track). Vendor support: Juniper Feature
  Explorer (5197 VRF, 5199 IP-NH), Nokia SR-OS docs, Cisco IOS-XR. Operator how-tos:
  Noction (redirect-via-VRF and redirect-to-IP config examples), NANOG 58 Serodio
  "Traffic Diversion Techniques for DDoS Mitigation using BGP Flowspec."
- **Adoption is LOWER than hoped** (documented). Kentik / APNIC (Justin Ryburn, Apr
  2025, "BGP Flowspec doesn't suck — we're just using it wrong"): adoption "remains
  lower than anticipated," quantified only anecdotally; redirect-to-VRF "difficult to
  use" in networks without L3VPN, which is why redirect-to-IP was drafted.
- **Every PUBLIC FlowSpec outage is the LOUD half, not the quiet bypass** (documented).
  CenturyLink/Lumen AS3356 Aug 2020 (a FlowSpec rule crashed line cards → BGP sessions
  withdrawn → D1/D2/D3 backbone-wide). Cloudflare 2013 (a rule matching illogical
  packet sizes malfunctioned Juniper line cards → all traffic dropped). Both are
  D1/D2/D3 catastrophes — the OPPOSITE of a quiet D4/D10 miss.
- **No named public post-mortem of a quiet FlowSpec-redirect waypoint bypass exists**
  (gap). Like the IGP hot-potato waypoint bypass, such events are caught internally as
  "why did this flow stop hitting the scrubber/tap" tickets, not published outages.
  Mechanism confidence = **documented**; the quiet waypoint-bypass framing =
  **analogous** (the redirect mechanism is documented; the inspection-node-on-the-path
  invariant is the operational overlay we add). DO NOT claim a named outage for the
  quiet variant.

## GRADING LIMIT — why this is currently a FALSE-quiet on the FRR/pinned digest

Verified against Batfish master grammar (2026-06-14, by the oracle-engineer, not from
memory):

1. **Native FlowSpec is ungrammared in the FRR dialect.** `Frr_bgp.g4` rule `rbaf`
   accepts only `ipv4_unicast | ipv6_unicast | l2vpn_evpn` — there is no flowspec
   address-family token. The rule is dropped on ingest; pre == post → empty oracle.
2. **FRR PBR emulation is also ungrammared.** `pbr-map` / `nexthop-group` /
   `pbr-policy` are pbrd / Linux `ip rule` kernel constructs; `Frr_interface.g4`
   accepts only `description | ip | ipv6 | shutdown | no`, and
   `FrrConfiguration.java` has no packet-policy/PBR field. Lines are ignored; the
   interface packet-policy is never set; traceroute is unchanged pre vs post.
3. **FRR `set ip next-hop` is a red herring.** It is a control-plane route-map SET
   attribute that rewrites the next-hop for the **whole prefix** in the RIB — NOT a
   per-flow data-plane redirect.
4. **The only Batfish-modeled redirect is Cisco-IOS / Arista-EOS / Juniper PBR**
   (`PBR_POLICY` structure type, applied in traceroute/forwarding analysis) — a
   different dialect from the FRR baseline.
5. **The oracle's D4 check is dstIps-only and all-or-nothing-ECMP.**
   `extended_oracle.py` calls traceroute with `headers={'dstIps': dst_ip}` only — zero
   dstPorts / ipProtocols / applications usage anywhere; `_waypoint_diff` is
   forward-only and `pre_ok = all(waypoint in n for n in traces)`. It cannot isolate a
   single sub-prefix flow from background traffic to the same prefix.

Net: on the pinned FRR digest the oracle returns an **empty set by instrument
blindness, not computed truth**. A model that correctly answered "D4 violated for flow
X" would be scored WRONG against the empty oracle (the inverse-quiet failure). The
determinism gate would PASS on the NULL oracle and give false confidence.

## What it takes to build this for real (TWO gates, not one)

1. **A vendor dialect Batfish models PBR/FlowSpec-redirect in** — Cisco IOS, Arista
   cEOS, or Juniper (data-plane `PBR_POLICY`). FRR can never express it on the pinned
   digest.
2. **A 5-tuple D4 oracle extension** — accept `HeaderConstraints` with `dstIps +
   dstPorts + ipProtocols`, trace the concrete victim flow, compare its transit set
   pre vs post, isolated from background traffic. Additive; keep the dstIps-only path
   for existing scenarios. Feasible (Batfish traceroute already accepts those header
   fields) but INSUFFICIENT ALONE — needs gate (1) too.

## Disposition

**DEFER.** Real and genuinely novel (per-flow sub-prefix path bypass — a new axis), but
(a) oracle-blind on the FRR/pinned digest, (b) weakly grounded (mechanism documented;
quiet bypass only analogous; adoption low), and (c) all public FlowSpec outages are the
loud half. Resurrect as a NEW dimension once an IOS/EOS/Juniper baseline AND the
5-tuple-D4 oracle extension both exist.

## References

- RFC 8955 (Dissemination of Flow Specification Rules; obsoletes 5575):
  https://www.rfc-editor.org/rfc/rfc8955.html
- draft-ietf-idr-flowspec-redirect-ip (Redirect-to-IP Action):
  https://datatracker.ietf.org/doc/draft-ietf-idr-flowspec-redirect-ip/
- Juniper Feature Explorer — redirect-to-VRF (5197), redirect-to-IP (5199):
  https://apps.juniper.net/feature-explorer/feature/5197
- Nokia SR-OS BGP FlowSpec:
  https://documentation.nokia.com/acg/23-10-2/books/classic-cli-part-i/c110-bgp-flowspec-for-ipv4-and-ipv6.html
- Kentik / APNIC, Ryburn, "BGP Flowspec doesn't suck — we're just using it wrong"
  (Apr 2025, adoption + redirect-to-VRF difficulty):
  https://blog.apnic.net/2025/04/04/bgp-flowspec-doesnt-suck-were-just-using-it-wrong/
- Noction — redirect via VRF / redirect-to-IP config examples:
  https://www.noction.com/blog/bgp-ddos-flowspec ;
  https://www.noction.com/blog/flowspec-redirect-to-ip
- NANOG 58 — Serodio, "Traffic Diversion Techniques for DDoS Mitigation using BGP
  Flowspec":
  https://archive.nanog.org/sites/default/files/wed.general.trafficdiversion.serodio.10.pdf
- KB cross-refs: `noc/centurylink_bgp_flowspec_aug2020.md` (loud-half outage),
  `noc/igp_metric_hotpotato_quiet_reroute.md` (sibling quiet-bypass, but
  prefix-level + gradeable on FRR), `batfish_verified_facts.md` (FRR PBR/FlowSpec
  ingest limits).
