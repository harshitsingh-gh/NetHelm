# Multicast Routing — PIM, IGMP, and Blast Radius

## Overview
Multicast delivers traffic from one source to multiple receivers efficiently — one copy in the network, replicated only at branch points. Key protocols: PIM (Protocol Independent Multicast) for router multicast routing, IGMP/MLD for host membership signaling.

## Multicast Address Space
- IPv4: 224.0.0.0/4 (Class D). Reserved ranges:
  - 224.0.0.0/24: link-local scope (OSPF hello 224.0.0.5, EIGRP 224.0.0.10, etc.)
  - 224.0.1.0/24: internet-scope
  - 232.0.0.0/8: SSM range
  - 239.0.0.0/8: administratively scoped (RFC 2365 — organization-local)
- IPv6: ff00::/8. Scope bits in the address (link, site, global)

## IGMP — Internet Group Management Protocol
IGMP (RFC 3376, version 3) runs between hosts and their directly-attached router:
- Host sends `IGMP Join` (Membership Report) to join a group
- Router maintains membership state and sends multicast to the segment while members exist
- Router sends periodic `IGMP General Query` to discover if any members remain
- **IGMP v1**: basic join/leave; last member leaves → router waits for query timer
- **IGMP v2**: adds explicit Leave messages; reduces leave latency
- **IGMP v3**: adds source filtering (SSM — joins specify both group AND source)

**Blast radius of IGMP query failure**: if the querier goes silent (router failure), members may eventually time out and leave the group. Traffic stops flowing after the membership timer expires.

## PIM-SM (Sparse Mode — RFC 7761)
PIM-SM is the most widely deployed multicast routing protocol. It builds distribution trees rooted at:
- **Shared tree (RP tree)**: (*,G) — all traffic flows from sources via the RP (Rendezvous Point) to receivers
- **Shortest path tree (SPT)**: (S,G) — direct source-to-receiver tree, triggered by first packet or threshold

### PIM-SM Key Mechanisms
1. **RP (Rendezvous Point)**: central coordination point; all sources register with RP; receivers join via RP
2. **PIM Join/Prune**: routers send Join toward RP to build (*,G) tree; Prune to remove from tree
3. **Register**: first-hop router sends unicast Register to RP when source sends; RP joins back
4. **SPT switchover**: last-hop router switches from (*,G) to (S,G) when bandwidth threshold exceeded (default: first packet)
5. **BSR (Bootstrap Router)**: dynamic RP discovery mechanism (RFC 5059)
6. **Auto-RP**: Cisco proprietary RP discovery

### PIM-SM Blast Radius Patterns

#### Pattern: RP Failure
**This is the canonical high-blast-radius multicast scenario.**
- **Trigger**: RP router fails or becomes unreachable
- **Chain**:
  1. New sources cannot register (Register message has no destination)
  2. Receivers on (*,G) trees lose their path (tree rooted at RP is broken)
  3. Receivers with established (S,G) SPTs may continue (SPT doesn't pass through RP)
  4. New receivers cannot join (cannot reach RP to send Join)
- **D3**: All multicast groups that had only (*,G) receivers lose traffic immediately; (S,G) groups survive
- **D5**: If Anycast RP or MSDP provides redundancy, failover occurs (typically 10–60s)

#### Pattern: RP Address Misconfiguration
- **Trigger**: RP address changed on one router but not all; some routers join via old RP, others via new RP
- **Effect**: Two separate multicast islands; sources registered at one RP are invisible to receivers at another
- **D3**: Intermittent multicast delivery; receivers may or may not receive traffic depending on which RP they use
- **Hard to diagnose**: data-plane delivery works for some receivers but not others; routing tables look correct

#### Pattern: PIM Neighbor Adjacency Loss
- **Trigger**: PIM hello timer expires (link failure or misconfiguration)
- **Chain**: PIM neighbor removed → all (S,G) and (*,G) entries that used that neighbor as RPF (Reverse Path Forwarding) neighbor are pruned → traffic stops
- **RPF (Reverse Path Forwarding)**: multicast uses the unicast RIB to determine the "correct" upstream interface. If a multicast packet arrives on the RPF interface, it's accepted and forwarded; otherwise dropped.
- **Blast radius**: all multicast flows that had RPF via the failed neighbor

#### Pattern: RPF Failure (Unicast Route Change)
- **Trigger**: Change to unicast routing (OSPF cost change, BGP prefix withdrawal) changes the RPF interface for a multicast source
- **Chain**: RPF interface changes → PIM Prune sent on old interface → PIM Join sent on new interface → multicast reconverges to new path
- **D7**: Multicast path changes (different tree path)
- **Transient D3**: During reconvergence (seconds)
- **This links multicast blast radius to unicast routing changes** — an OSPF cost change can affect multicast delivery even if unicast reachability is unaffected

## PIM-SSM (Source-Specific Multicast — RFC 4607)
SSM (range 232.0.0.0/8) eliminates the RP concept entirely:
- Receivers join (S,G) directly — specify both source AND group
- No (*,G) tree; no RP; no registration
- Simpler, more secure (no spoofed sources; only explicit source joins)
- Requires IGMP v3 support on hosts

**Blast radius**: SSM failure modes are simpler — no RP to fail. Primary failure: RPF failure (same as PIM-SM pattern above).

## PIM-DM (Dense Mode — RFC 3973)
PIM-DM floods multicast traffic everywhere, then prunes branches without receivers. NOT scalable for the Internet; used only in small LANs.
**Blast radius**: all routers receive all multicast traffic initially; prune state can be accidentally lost causing re-flooding.

## MSDP (Multicast Source Discovery Protocol — RFC 3618)
MSDP connects multiple PIM-SM domains by sharing source information between RPs. Used for inter-domain multicast (e.g., between different ASes).

**Blast radius of MSDP session failure**:
- Sources registered at the local RP become invisible to receivers in other domains
- Remote RP loses SA (Source Active) cache for sources in the failed domain
- All cross-domain multicast stops for sources in the affected domain

## Multicast and Batfish
Batfish has **NO multicast routing support**:
- PIM configuration is not parsed
- IGMP state is not modeled
- Multicast routing tables (MRIB) are not available
- **For NetHELM**: multicast blast radius scenarios require live lab testing or a dedicated multicast simulator; they cannot be graded by Batfish

## Common Multicast Misconfiguration Patterns

| Misconfiguration | Effect |
|---|---|
| RP address inconsistent | Multicast islands; some receivers can't receive |
| PIM sparse mode but no RP | Multicast completely fails for groups without explicit (S,G) SPT |
| IGMP snooping enabled but mis-applied | Multicast traffic flooded or dropped incorrectly on VLAN |
| RPF failure (route removed) | (S,G) entry deleted; traffic stops |
| PIM hello not enabled on interface | No PIM neighbor; no Join/Prune exchange; traffic stops at that link |
| TTL scoping too aggressive | Multicast contained within wrong boundary |
| SSM configured but IGMP v3 not on hosts | Hosts can't join SSM groups; no traffic |
