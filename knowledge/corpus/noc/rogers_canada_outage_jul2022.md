# Rogers Canada National Outage — July 8, 2022

## Summary
On July 8, 2022, Rogers Communications (Canada's largest telecom) suffered a ~19-hour
nationwide outage affecting millions of customers. Internet, wireless, cable TV, and
911 were disrupted. **Per the CRTC / Xona Partners assessment (executive summary
released July 2024), the root cause was a maintenance change in which Rogers staff
REMOVED an Access Control List (ACL) policy filter from the distribution routers,
which caused an abnormal FLOOD of IP routing information into the core network. The
flood exceeded the core routers' capacity and crashed them within minutes.** The
missing safeguard was an overload/route-limit on the core routers.

> ACCURACY NOTE (2026-06-08): An earlier version of this file described Rogers as an
> "internal route distribution collapse" in which a policy *denied* the routes the
> backbone needed, silently withdrawing them while sessions stayed up. **That is
> wrong** — it is roughly the OPPOSITE of what happened. The CRTC/Xona finding is a
> filter *removal* causing a route *flood* and a resource *overload/crash*, not a
> silent withdrawal. Corrected per the sources below. The silent-withdrawal pattern
> is a real failure mode, but it was NOT the Rogers mechanism — it is documented
> separately at the end of this file and grounded in operational lore, not Rogers.

## What Happened (corrected)

### The Maintenance Change
Rogers was deploying a configuration change to its IP core as part of a multi-phase
upgrade. In the relevant phase, staff **deleted an ACL/policy filter on the
distribution routers** that had been constraining which routing information those
routers passed toward the core.

### The Failure Chain
1. With the filter removed, the distribution routers forwarded an abnormally large
   volume of IP routing information into the core network.
2. The core routers received this flood and **exceeded their processing/memory
   capacity** — they were not configured with an overload limit on the amount of
   routing data they would accept.
3. The overloaded core routers **failed/crashed within minutes**, taking the IP core
   down.
4. With the core down, the entire Rogers network (wireless, internet, cable, 911)
   lost connectivity nationally.
5. Recovery required out-of-band access and careful staged restoration — the OOB
   management depended on the same infrastructure, complicating recovery.

### The Fix Rogers Implemented
Rogers added **overload protection** to the core routers: a configured limit on the
maximum amount of IP routing data a router will accept, so a future flood is dropped
rather than crashing the device. (This is the same class of safeguard as a BGP
`maximum-prefix` limit / a FIB/RIB resource budget.)

### Regulatory Consequence
Because 911 was affected, the CRTC opened an investigation and commissioned Xona
Partners to assess Rogers' network. The executive summary (July 2024) attributed the
outage to human error (the filter removal) compounded by the absence of overload
protection and by management/process deficiencies that prolonged recovery.

## Blast Radius Analysis (corrected)
- **D8 (Scale / resource overflow)** — THIS IS THE PRIMARY DIMENSION. A change
  multiplied the routing-information volume past a device's (implicit) capacity
  limit. Rogers is the flagship real-world grounding for the **scale/overload class**
  (cf. de-aggregation / FIB-TCAM overflow / BGP `maximum-prefix`).
- **D1 (Sessions)** — sessions/adjacencies were lost as a *consequence* of the core
  routers crashing (not as the trigger).
- **D2 / D3 (Prefixes / Reachability)** — total loss, cascading from the core
  failure.
- The triggering change was a **filter removal (a D6-class edit)** whose unintended
  effect was a scale overload — i.e., a D6 change with a D8 blast.

**NetHELM implication:** Rogers grounds the **D8 scale/overload class** (a change that
pushes routing volume past a resource limit → cascade). Model it with a per-device
route/resource budget annotation (Batfish gives the route count; the limit is a
spec). The runtime crash itself is LIVE/spec-dependent — score the count-vs-limit
threshold, not which specific routes a device evicts.

## A RELATED BUT DISTINCT failure class (NOT the Rogers mechanism): silent policy withdrawal
This is a real and important blast-radius class — it is just **not what happened at
Rogers**. It is grounded in operational lore and the "implicit deny-all" maintenance
pattern (see `maintenances_that_caused_outages.md`, Maintenance Type 2), and at the
*prefix* level it resembles parts of the Facebook Oct-2021 withdrawal (though that
incident also took BGP/the backbone fully down).

**Scenario**: A routing policy (route-map / prefix-list) is applied to iBGP peers and
inadvertently denies routes the data plane needs (e.g., the engineer adds an outbound
filter and forgets the final `permit any`, so a prefix is silently filtered).

**Result**:
- The affected prefixes are withdrawn from downstream peers' RIB/FIB.
- BGP sessions can stay ESTABLISHED (the filter affects advertised NLRI, not the
  session, whose next-hop resolves via IGP/static) — so the network "looks fine."
- Reachability collapses for the withdrawn prefixes that lack a static/IGP backup.

**Batfish modellability**: Batfish detects this deterministically — `bgpSessionStatus`
shows ESTABLISHED; the prefix leaves `bgpRib` (BEST set) and `routes()` (FIB) on the
downstream node; `traceroute` returns NO_ROUTE. This is the basis for NetHELM
**Class 1 (internal routing-policy silent withdrawal)** — grounded here as operational
lore + maintenance-Type-2, explicitly **not** as a reproduction of the Rogers cause.

## Key Lessons
1. **Resource/overload limits are essential.** The single missing safeguard at Rogers
   was a cap on accepted routing data. Changes that multiply routing volume
   (de-aggregation, filter removal, add-path) are blast-radius-critical.
2. **A "filter removal" can be as dangerous as a filter addition** — removing a
   constraint can flood downstream devices.
3. **Test changes in simulation/staging first**; a single PoP rollout would have
   contained it.
4. **OOB management must be independent** of the production control plane.

## References
- [CRTC — Assessment of Rogers Networks (Xona Partners), exec summary, Jul 2024](https://crtc.gc.ca/eng/publications/reports/xona2024.htm)
- [CRTC — Rogers 8 July 2022 outage assessment](https://crtc.gc.ca/eng/publications/reports/xonarp2023.htm)
- [CBC — Human error caused 2022 Rogers outage, system deficiencies made it worse](https://www.cbc.ca/news/politics/rogers-outage-human-error-system-deficiencies-1.7255641)
- [2022 Rogers Communications outage — Wikipedia](https://en.wikipedia.org/wiki/2022_Rogers_Communications_outage)
- Doug Madory (Kentik) BGP analysis; RIPE NCC routing data for AS812 (Rogers).
