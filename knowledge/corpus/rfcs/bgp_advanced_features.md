# BGP Advanced Features — RFC Reference

## Add-Path (RFC 7911)
Allows BGP speaker to advertise multiple paths for the same prefix to a peer. Prevents BGP best-path hiding problem in route reflector deployments.

**Problem it solves**: In classic iBGP RR design, RR only reflects the best path. If the best path goes down, backup path has to be learned fresh → slow convergence. With ADD-PATH, backup path is already known.

**Capability**: negotiated in OPEN message; both peers must support.
**FRR config**: `neighbor X addpath-tx-all-paths` or `neighbor X addpath-tx-bestpath-per-AS`

**Blast radius implication**: With ADD-PATH, D5 (redundancy) improves — multiple paths already present before failure.

---

## BGP Graceful Restart (RFC 4724)
Allows BGP peer to maintain forwarding state during a BGP restart (e.g., control plane reboot). The restarting router signals its peers to retain forwarding state; peers become "helpers" and do not withdraw routes during the restart window.

**Key timers**:
- Restart time: how long helper should maintain forwarding state (announced in OPEN)
- Selection_Deferral_Timer: helper defers best-path selection until EOR (End of RIB) received

**Blast radius implication**: With GR, a control plane restart causes D1 (session temporarily down) but D3 (reachability) may be unaffected if GR completes within restart time.

**FRR config**:
```
router bgp 65001
 bgp graceful-restart
 bgp graceful-restart restart-time 120
 bgp graceful-restart stalepath-time 360
```

---

## BGP Route Dampening (RFC 2439)
Suppresses flapping prefixes. A prefix accumulates a penalty each time it flaps; when penalty exceeds `suppress-limit`, route is suppressed for a period. Penalty decays exponentially.

**Default values (Cisco)**:
- Half-life: 15 minutes (time for penalty to decay by half)
- Reuse: 750 (penalty below which route is unsuppressed)
- Suppress: 2000 (penalty above which route is suppressed)
- Max-suppress: 60 minutes

**Blast radius implication**: Dampening is a safety mechanism that limits blast radius propagation of flapping routes. But it also introduces a delay in restoring legitimately-recovered routes.

**Modern consensus**: RIPE-378 recommends NOT using dampening for prefixes ≤/24 from peers. Can suppress legitimate recovery.

---

## BGP NEXT_HOP Tracking (RFC-compliant behavior)
BGP routers continuously track whether the next-hop for BGP routes is reachable via the IGP. If the next-hop becomes unreachable, BGP withdraws the route from the RIB.

**Next-hop tracking scan timer**: how often BGP checks next-hop reachability (default 5s on most platforms)

**Why this matters for blast radius**:
- Removing an OSPF/static route that is the next-hop resolver for BGP → BGP prefix withdrawn from FIB within 5s
- The BGP session itself stays ESTABLISHED (TCP connection not affected)
- This is the "recursive resolution failure" scenario (Pattern 3 in blast_radius_patterns.md)

---

## Multiprotocol BGP — MP-BGP (RFC 4760)
Extends BGP to carry non-IPv4 NLRI using MP_REACH_NLRI (type 14) and MP_UNREACH_NLRI (type 15) attributes.

**Address families**: IPv6 unicast, VPNv4, VPNv6, L2VPN EVPN, FlowSpec, etc.
**Each address family has independent**: RIB, route-map application, neighbor activation

**Key AFI/SAFI values**:
- AFI=1 (IPv4), SAFI=1 (unicast)
- AFI=2 (IPv6), SAFI=1 (unicast)
- AFI=1, SAFI=128 (VPNv4)
- AFI=25, SAFI=70 (L2VPN EVPN)

---

## BGP FlowSpec (RFC 5575)
Distributes packet filter rules (traffic classifiers + actions) via BGP. Used for DDoS mitigation.

**NLRI components**: destination prefix, source prefix, protocol, port, packet length, DSCP
**Actions**: rate-limit, redirect, traffic-mark, discard
**Used by**: service providers for automated DDoS response

---

## RPKI (RFC 6480 + RFC 6811)
Resource Public Key Infrastructure. Cryptographic attestation of prefix-to-AS origin authorization.

**ROA (Route Origin Authorization)**: signed object saying "AS X is authorized to announce prefix P/len"
**ROV (Route Origin Validation)**: BGP speaker validates received routes against ROA database
**Validation states**: valid, invalid, not-found (not notfound)
**Recommended action**: drop invalid; prefer valid over not-found; accept not-found

**Blast radius**: RPKI ROV prevents route leaks from propagating (Cloudflare Jun 2019 outage would have been stopped). Does not affect correctness of already-valid routes.

---

## BGP Large Communities (RFC 8092)
Extended community format: GlobalAdministrator:LocalData1:LocalData2 (all 32-bit).
Total: 96 bits. Allows any AS to use full 32-bit ASN as the global administrator.

**Use cases**: tagging by origin AS, geography, customer type, traffic engineering action
**Format in IOS**: `ip large-community-list standard X permit 65001:100:200`

---

## Confederations (RFC 5065)
Alternative to route reflectors for iBGP scaling. Divides an AS into multiple sub-ASes (confederation members). Routes between sub-ASes use eBGP-like rules but appear as iBGP to the outside world.

**AS_PATH**: confederation sub-ASes appear in AS_CONFED_SEQUENCE (stripped at border)
**Complexity**: harder to operate than route reflectors; not commonly deployed in new networks
