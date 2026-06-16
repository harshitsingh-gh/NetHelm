# HSRP, VRRP, and GLBP — First-Hop Redundancy Protocols

## Overview
First-Hop Redundancy Protocols (FHRPs) provide a virtual default gateway IP address shared between two or more routers. End hosts use the virtual IP as their default gateway; the active/master router responds to ARP for the virtual IP.

| Protocol | Standard | Virtual MAC |
|---|---|---|
| HSRP v1 | Cisco proprietary (RFC-like) | 0000.0c07.acXX (XX = group) |
| HSRP v2 | Cisco proprietary | 0000.0c9f.fXXX |
| VRRP v2 | RFC 3768 (IPv4) | 0000.5e00.01XX (XX = VRID) |
| VRRP v3 | RFC 5798 (IPv4+IPv6) | 0000.5e00.01XX or 0000.5e00.02XX |
| GLBP | Cisco proprietary | Up to 4 virtual MACs; load balances |

## HSRP (Hot Standby Router Protocol)
**States**: Initial → Learn → Listen → Speak → Standby → Active

**Active router**: responds to ARP for virtual IP, forwards traffic.
**Standby router**: monitors active via hellos; takes over if active fails.
**Priority**: higher wins (default 100). Preemption enabled with `standby N preempt`.

**Hello/Dead timers**: default 3s hello, 10s holdtime. With `standby N timers msec 200 msec 750` → subsecond failover.

### HSRP Blast Radius Patterns

#### Pattern: Active Router Failure
**Trigger**: Active router crashes or loses link.
**Chain**:
1. Standby router misses 3 hellos (10s with default timers, 750ms with msec timers)
2. Standby transitions to Active; starts responding to ARP for virtual IP
3. Gratuitous ARP sent to update switch CAM tables

**D3**: Traffic disruption for 10s (default) or 750ms (with msec timers). D5: redundancy eliminated (now running single active).

#### Pattern: HSRP Split Brain
**Trigger**: Link between active and standby router fails, but both still have connectivity to end hosts.
**Effect**: Both routers believe they are active and respond to ARP for the virtual IP. Two MACs → ARP table flapping → packet duplication, intermittent forwarding errors.

**Prevention**: use a dedicated HSRP keepalive interface or track objects to force one router to step down if it loses connectivity to upstream.

#### Pattern: HSRP Object Tracking Misconfiguration
**Config**: `standby N track OBJECT decrement 60` — if tracked object fails, priority drops by 60 (typically from 110 to 50), allowing standby (priority 100) to become active.
**Trigger**: tracked object (e.g., interface, IP SLA) fails while network is intact.
**Effect**: unintended HSRP failover; active becomes standby; traffic briefly disrupted during transition.
**D4**: Traffic takes different path after failover (via new active router). **D7**: Forwarding path changes.

### VRRP vs HSRP Key Differences
- VRRP: open standard (works on multi-vendor); lower administrative overhead
- VRRP master: responds to virtual IP ARP; sends advertisement multicast to 224.0.0.18
- VRRP uses the real IP of the master router on some platforms (not a separate virtual IP) as its source
- VRRP v3: supports IPv6, subsecond timers

### GLBP (Gateway Load Balancing Protocol)
GLBP distributes traffic across multiple active gateways using:
- One **AVG (Active Virtual Gateway)**: responds to ARP with different virtual MACs for each host (round-robin, weighted, or host-dependent)
- Multiple **AVFs (Active Virtual Forwarders)**: each has its own virtual MAC; each handles a subset of host traffic

**Blast radius of AVF failure**: hosts that were assigned the failed AVF's virtual MAC lose their gateway; AVG re-assigns them to surviving AVF. Disruption: 1 hello period (default 3s).

## FHRP and Batfish
Batfish does NOT model HSRP/VRRP/GLBP:
- Virtual IPs are not part of the routing table analysis
- ARP/FHRP state is not modeled
- Failover behavior is not simulated
- **For NetHELM**: FHRP blast radius requires live lab testing; cannot be graded by Batfish
