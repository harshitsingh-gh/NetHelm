# NOC Interview Scenarios — BGP/OSPF Troubleshooting

## How to Use This Document
These are common network operations center interview questions and scenarios. Each covers a failure pattern that a senior NRE should be able to diagnose from symptoms and `show` command output.

---

## Scenario 1: BGP Session Won't Come Up
**Symptoms**: `show ip bgp summary` shows neighbor in "Active" state for several minutes.

**Checklist (in order)**:
1. TCP 179 connectivity: `telnet <peer-ip> 179` from router; if fails → L3 or ACL issue
2. Routing to peer: `show ip route <peer-ip>` — is next-hop reachable?
3. Source IP: if using `update-source Loopback0`, is loopback reachable from peer?
4. AS number match: peer's `remote-as` must match local AS
5. Authentication: if MD5 configured, keys must match exactly (including trailing spaces)
6. TTL: eBGP default TTL=1; if peering over multiple hops, need `ebgp-multihop <N>`
7. MTU: large BGP updates can fail if MTU inconsistent (rare but real)
8. ACL: check if ACL on interface blocks TCP 179

**Batfish analogy**: If Batfish shows NOT_ESTABLISHED after session should be up, check the config for the above.

---

## Scenario 2: Routes Learned but Not Installed in RIB
**Symptoms**: `show ip bgp` shows prefix; `show ip route` doesn't.

**Checklist**:
1. Next-hop reachability: `show ip bgp <prefix>` → check Next Hop; then `show ip route <next-hop>`; if no route → next-hop unreachable
2. `next-hop-self` missing: for iBGP, if NEXT_HOP is an eBGP peer's address, it must be reachable via IGP, or `next-hop-self` needed on the iBGP session
3. Duplicate route: if another protocol has same prefix with lower AD, BGP loses; check AD (BGP=20 eBGP, 200 iBGP)
4. Maximum prefix exceeded: if threshold hit, session drops or stops installing routes
5. Route dampened: `show ip bgp dampening dampened-paths` — if flapping, route may be suppressed

---

## Scenario 3: BGP Routes Suddenly Withdrawn (Flap)
**Symptoms**: `show ip bgp summary` shows "Flaps" counter incrementing; routes disappear and return.

**Checklist**:
1. Hold timer: if keepalives not sent within hold time (default 60s), session resets; check CPU utilization
2. Interface flap: underlying interface going up/down causes BGP session reset
3. MD5 key rotation: if key changed on one side before the other, authentication failure
4. Memory pressure: router drops BGP update processing under memory stress
5. BFD misconfiguration: if BFD detects false failures, it triggers BGP to reset
6. MTU: asymmetric MTU can cause large UPDATE messages to be dropped

---

## Scenario 4: OSPF Neighbor Stuck in EXSTART/EXCHANGE
**Symptoms**: `show ip ospf neighbor` shows state EXSTART or EXCHANGE for minutes without reaching FULL.

**Cause**: Almost always MTU mismatch between neighbors.
- One interface has MTU 1500, neighbor has MTU 9000 (jumbo)
- OSPF DBD packets exceed MTU; dropped at receiver
- Session stays in EXSTART trying to negotiate

**Fix**: Set matching MTU (`ip mtu 1500` on both), or use `ip ospf mtu-ignore` (Cisco — masks the problem)

**Other causes**:
- Duplicate router-IDs: two routers with same RID; DBD sequence number conflict
- Authentication mismatch: one side has auth, other doesn't
- Area mismatch: different area IDs configured on same link

---

## Scenario 5: OSPF Neighbor in 2-WAY (Not FULL)
**Symptoms**: `show ip ospf neighbor` shows state 2-WAY for some neighbors on a broadcast segment.

**This is expected for DROthers**. On a broadcast segment, only DR and BDR form FULL adjacency with other routers. Non-DR/BDR routers only reach 2-WAY with each other.

**When it's a problem**: if the router you expect to be DR/BDR is not, and priority=0 was inadvertently set.

**Fix**: Set `ip ospf priority 255` on the intended DR; `clear ip ospf process` to re-trigger election.

---

## Scenario 6: Route Exists but Traffic Black-Holes
**Symptoms**: `show ip route 10.1.1.1` shows a route; `ping 10.1.1.1` fails (or ICMP returns but no application traffic).

**Checklist**:
1. RPF check: if source IP doesn't have reverse route, uRPF may drop it
2. Next-hop ARP: `show arp <next-hop>` — if no ARP entry, L2 problem
3. ACL on outbound interface: `show ip interface <int>` → check outbound ACL
4. Policy-based routing: `show route-map` for PBR; may redirect differently than RIB
5. Recursive next-hop broken: BGP route depends on IGP next-hop that exists in RIB but has no valid L2 path
6. CEF (Cisco Express Forwarding): `show ip cef 10.1.1.1` — if CEF and RIB disagree, `clear ip cef`

---

## Scenario 7: BGP Table Has Correct Route but Traffic Goes Wrong Way
**Symptoms**: Expected path A→B; traffic actually going A→C.

**This is a D4/D7 scenario** (waypoint violation / forwarding path change).

**Checklist**:
1. Verify actual path: `traceroute` to destination
2. Check all BGP paths: `show ip bgp <prefix>` — are multiple paths present? Which is best?
3. LOCAL_PREF: higher LOCAL_PREF wins; check if someone set LP=200 on a different path
4. AS_PATH: shorter AS_PATH wins; check if alternate path has fewer hops
5. Weight (Cisco-specific): per-neighbor weight overrides LOCAL_PREF; check `neighbor X weight`
6. MED: if comparing routes from same AS, lower MED wins; check `bgp always-compare-med`

---

## Scenario 8: Entire Network Loses Internet (Default Route Gone)
**Symptoms**: All internal hosts can't reach Internet; internal routing fine.

**Checklist**:
1. Default route in BGP: `show ip bgp 0.0.0.0` — is default present?
2. Default route in RIB: `show ip route 0.0.0.0`
3. Upstream session: `show ip bgp summary` — is upstream ISP session ESTABLISHED?
4. Upstream not advertising default: ISP may have stopped advertising; call them
5. Route-map blocking default: check inbound route-map for policy that denies 0/0
6. Maximum-prefix: if prefix limit hit, session down → default lost

---

## Scenario 9: OSPF Route Flapping
**Symptoms**: Routes appear/disappear in OSPF RIB every few seconds.

**Cause checklist**:
1. Interface flap: `show interface` — Line protocol flapping?
2. BFD false positive: BFD detecting false link failure; check `show bfd neighbors`
3. CPU overload: SPF being throttled; `show ip ospf statistics`
4. Duplicate RID: two routers with same router-ID causes LSA conflict and flapping
5. LSA timer: someone set aggressive LSA retransmit (very rare)

---

## Scenario 10: BGP Convergence Very Slow After Failover
**Symptoms**: After a link failure, BGP takes 3–5 minutes to converge (instead of seconds).

**Root cause**: BGP minimum route advertisement interval (MRAI) — default 30s for eBGP, 0s for iBGP.

**Fix**:
```
router bgp 65001
 neighbor 10.0.0.2 advertisement-interval 0  ! or lower value
```

**Also check**: BFD for subsecond detection. Without BFD, BGP relies on hold timer (default 180s) → 3-minute convergence is correct behavior if hold timer expires.
