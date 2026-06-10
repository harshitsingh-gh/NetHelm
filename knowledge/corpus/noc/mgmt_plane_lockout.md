# Management-Plane / OOB Lockout — The Change Breaks the Tools Needed to Fix It

## Why a dedicated file
A whole class of catastrophic-duration outages is not about *which routes drop* — it
is about a change that **severs the path from the operators' tooling (NOC jump host,
monitoring, deployment, auth) to the device's management address**, so the very change
that broke the network also breaks the ability to undo it. The reachability loss is
small and specific (jump-host → mgmt-IP) but the blast on **recovery time** is
enormous. This is the dimension that turns a 5-minute fix into a multi-hour
truck-roll. It is a distinct, gradeable blast — score the reachability of the
*management path*, separately from the data-plane blast. Dimensions per
`../batfish/blast_radius_patterns.md` (primarily D3 restricted to the management path).
DEEPENS the OOB notes in `./facebook_bgp_outage_oct2021.md` and
`./cloudflare_dc_outage_jun2022.md`.

## The mechanism
The management plane (SSH/console/API to a device's mgmt address, plus the services
operators depend on: internal DNS, auth/MFA, monitoring, deployment) must reach the
device over *some* path. If that path runs **in-band** — over the same production
control plane the change affects — then a change that breaks production also breaks
management, and recovery cannot proceed remotely. The fix in every post-mortem is the
same: a **truly independent out-of-band (OOB) network** that does not depend on the
production routing/DNS/auth being healthy. The trap is an OOB that only *looks*
independent because it shares a dependency (in-band DNS, in-band auth, a transit link,
a shared loopback).

## Real incident grounding

**Facebook/Meta, Oct 4 2021.** A backbone change withdrew Facebook's routes and
disconnected its data centers. Recovery was crippled because the management tooling
shared the broken network: *"Facebook engineers could not use their normal remote
access tools because those tools also relied on the internal network that was down.
Physical access to data centers was required. Multi-factor authentication systems were
also unavailable because they relied on the same infrastructure."* Engineers had to
physically travel to data centers for console access.
(see `./facebook_bgp_outage_oct2021.md`;
[FB Engineering — Oct 4 outage](https://engineering.fb.com/2021/10/05/networking-traffic/outage-details/))

**AWS us-east-1, Dec 7 2021.** An internal-network congestion event broke AWS's own
control/management plane, which depends on that same internal network. From the AWS
post-mortem:
- Monitoring blindness: *"This congestion immediately impacted the availability of
  real-time monitoring data for our internal operations teams, which impaired their
  ability to find the source of congestion and resolve it."*
- Deployment tooling down: *"our internal deployment systems, which run in our
  internal network, were impacted, which further slowed our remediation efforts."*
- Console down: *"Customers also experienced login failures to the AWS Console in the
  impacted region during the event."*
- Even support ticketing: *"Our Support Contact Center also relies on the internal AWS
  network, so the ability to create support cases was impacted."*
[AWS — Summary of the Dec 7 2021 US-EAST-1 event](https://aws.amazon.com/message/12721/)

**Rogers, Jul 8 2022.** Recovery was prolonged because *"the OOB management depended
on the same infrastructure"* as the crashed core — staff could not remotely reach the
devices they needed to roll back (see `./rogers_canada_outage_jul2022.md`).

**Cloudflare, June 2022 DC outage.** The OOB-dependency angle is noted in
`./cloudflare_dc_outage_jun2022.md` — cross-ref rather than repeat.

Common thread across all four: the management plane was a **dependency of**, not
independent of, the thing that broke. That is the failure mode this class tests.

## The change → trap → blast
**Change classes that sever the management path (each looks like a routine, narrowly
scoped edit):**
- An ACL / firewall rule "cleanup" on a mgmt/transit interface that drops the
  jump-host subnet or the SSH/NETCONF port to the mgmt-IP.
- Shutting/renumbering the interface or VRF that carries OOB, or removing a static
  route the jump-host → mgmt-IP path depends on (recursive next-hop, cf. Pattern 3 in
  `blast_radius_patterns.md`).
- Moving management into the same VRF/IGP as production "to simplify," eliminating the
  independence.
- Tightening auth (TACACS/RADIUS source, MFA reachability) so the device can no longer
  authenticate the operator because the auth server is now unreachable.

**Trap:** the data-plane blast may be small or even *intended* — the engineer thinks
"I'm just tightening an ACL / cleaning a route." The unscored damage is that the
*management path itself* is now in the blast radius. If the change also (or later)
breaks production, there is no remote way back in.

**Blast set:**
- **D3 (management path)** — THE PRIMARY DIMENSION, but scoped specifically: a
  traceroute/reachability check from **jump-host source → device mgmt-IP / SSH port**
  goes from ACCEPTED to NO_ROUTE or DENIED. This is the gradeable core.
- **D6** — the ACL/policy edit that did it (a permit→deny flip on the mgmt path).
- **D1 / D2 (data plane)** — may be 0 (the production sessions and prefixes are
  untouched). That is exactly why it slips review — the data-plane blast looks empty.
- **Recovery-time blast (qualitative, not a Batfish dim)** — the multiplier on MTTR;
  worth flagging in scenario prose because it is *the* reason this class matters, even
  though the static oracle scores only the D3 mgmt-path reachability.

## Batfish modellability
**GOOD — this is one of the cleanest gradeable blasts, because it reduces to a
specific reachability query.** Batfish's `reachability` / `traceroute` with a fixed
source (the jump-host IP/subnet) and destination (the device mgmt-IP and SSH/NETCONF
port) deterministically returns ACCEPTED vs DENIED/NO_ROUTE pre/post. The ACL flip is
visible via `testFilters` / `searchFilters` (D6). No live state needed.
- **Modeling requirement:** the snapshot must actually include the management
  addressing, the jump-host source, and the OOB/mgmt path (or its in-band path) — many
  lab snapshots omit mgmt interfaces entirely, in which case there is nothing to grade.
  Annotate the jump-host source and mgmt-IP/port as scenario spec.
- **What Batfish does NOT capture:** the cross-dependency on internal DNS / auth / MFA
  (the AWS and FB amplifiers) and the recovery-time multiplier — those are
  service/operational, not forwarding. Score the forwarding reachability of the mgmt
  path; note the dependency amplifier in prose.

## Why this is NOT redundant
- Distinct from generic reachability loss (Pattern 1/3): here the *only* destination
  that matters is the management address, and the data-plane blast can be empty. The
  scenario tests whether a model recognizes that "I only broke the mgmt subnet, no
  customer prefixes" is itself a top-severity finding — the opposite of the usual
  "count the customer prefixes" reasoning.
- It is the gradeable core of the OOB lessons that the FB/Rogers/Cloudflare files
  state only as a *lesson*; this file turns "OOB must be independent" into a concrete
  jump-host→mgmt-IP reachability oracle.

## Key lessons
1. A change that breaks the management path is a top-severity blast even if **zero**
   customer prefixes are affected — because it removes the ability to recover.
2. OOB must be *independent* of the production control plane, internal DNS, and auth —
   FB (2021), AWS (2021), Rogers (2022) all failed because management shared a
   dependency with the thing that broke.
3. Grade it as a fixed-source reachability query (jump-host → mgmt-IP/port), separate
   from the data-plane blast.

## References
- [AWS — Summary of the Dec 7 2021 US-EAST-1 Event](https://aws.amazon.com/message/12721/)
- [Meta Engineering — More details about the October 4 outage](https://engineering.fb.com/2021/10/05/networking-traffic/outage-details/)
- [CRTC / Xona — Rogers outage assessment](https://crtc.gc.ca/eng/publications/reports/xona2024.htm)
- Cross-refs (internal): `./facebook_bgp_outage_oct2021.md`,
  `./cloudflare_dc_outage_jun2022.md`, `./rogers_canada_outage_jul2022.md`,
  `../batfish/blast_radius_patterns.md` (Pattern 3 recursive next-hop, Pattern 4
  filter change).
