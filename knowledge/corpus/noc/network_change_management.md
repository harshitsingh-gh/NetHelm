# Network Change Management — NOC Best Practices

## Change Management Principles (Relevant to Blast Radius)

### Pre-Change Verification
Before any config change to a production router:
1. **Capture baseline**: `show ip bgp summary`, `show ip route`, `show interface` — save outputs
2. **Identify dependencies**: which services depend on this router? Which routes are learned exclusively via this path?
3. **Blast radius estimate**: enumerate which prefixes, sessions, or services would be lost if the change fails
4. **Backout plan**: exact commands to undo the change; tested in lab if possible
5. **Maintenance window**: for high-impact changes, schedule window; notify NOC

### Common Change Categories by Risk
| Change Type | Typical Blast Radius | Risk Level |
|---|---|---|
| Add new BGP neighbor | Zero (additive) | Low |
| Remove BGP neighbor | Loss of all routes from that peer | High |
| Modify LOCAL_PREF | Traffic shift; no session/prefix loss | Medium |
| Modify prefix-list | May block routes; prefix loss | Medium-High |
| Interface shutdown | Session loss for peers on that interface | High |
| AS number change | All sessions reset | Critical |
| Remove static route | Potential recursive resolver failure for BGP | Medium-High |
| OSPF cost change | Traffic shift; potential microloop | Medium |
| Route reflector config | May cause iBGP instability | High |

### The Batfish Pre-Change Check Workflow
1. Stage the proposed config change in a test snapshot
2. Run `bgpSessionStatus` on both pre and post snapshots
3. Diff: count lost sessions (D1)
4. Run `bgpRib` and diff prefix counts (D2)
5. Run `traceroute` for critical service IPs (D3)
6. If any D1/D2/D3 losses beyond expected: escalate for review

### Surgical vs Broad Changes
- **Surgical**: change affects only explicitly targeted sessions/routes; blast radius predictable
- **Broad**: change to a route-map applied to 50 eBGP peers; blast radius scales with scope

### The "Planned Outage" vs "Unplanned Impact"
NetHELM's safety axis evaluates whether an LLM can predict the blast radius of a change. This is exactly the pre-change verification step above — the model is acting as an automated NOC analyst.

---

## Common Change Failures (Real-World Patterns)

### Pattern: Route-Map Applied to Wrong Direction
**Change**: `neighbor X route-map POLICY out` intended
**Mistake**: applied `in` instead
**Impact**: affects inbound routes from X rather than outbound; may accept routes that should be filtered

### Pattern: Prefix-List Missing Implicit Permit
**Change**: Add deny clause to prefix-list
**Mistake**: After the deny, there's no explicit permit; IOS applies implicit deny-all at end of list
**Impact**: all prefixes not explicitly permitted are now denied → massive prefix loss

### Pattern: BGP Network Statement Missing Mask
IOS: `network 10.0.0.0` defaults to classful mask (/8); will only advertise if exact /8 route exists in RIB
**Correct**: `network 10.1.2.0 mask 255.255.255.0`

### Pattern: Clearing BGP Session During Peak Hours
`clear ip bgp 10.0.0.1` tears down TCP session; routes withdrawn; convergence time = MRAI + SPF
A soft clear (`clear ip bgp 10.0.0.1 soft`) re-applies policy without session teardown

### Pattern: Filter Change Affecting More Peers Than Expected
A route-map or community-list change applied via a peer-group affects ALL members of the group. 
**Check**: `show ip bgp peer-group <name>` to see all members before modifying

---

## Blast Radius Estimation Heuristics (For LLM Evaluation)

A well-trained NOC engineer would give answers like:
- "If you remove neighbor X and X is the only path to AS65002, you lose all routes in AS65002"
- "If you change LOCAL_PREF from 100 to 200 on peer X and peer Y has LP=150, traffic shifts to X"
- "If you set maximum-prefix 100 on a peer currently advertising 500 routes, the session tears down and you lose all 500 routes"

NetHELM evaluates whether LLMs can reason this precisely.

**Current observed LLM failures (from initial experiments)**:
- Predicting session loss for LOCAL_PREF changes (sessions don't drop on LP changes)
- Missing the recursive-resolver mechanism for static route → BGP cascade
- Not naming specific prefixes lost, only saying "some prefixes may be affected"
- Ignoring iBGP split-horizon (routes not re-advertised between iBGP peers without RR)
- Treating all BGP changes as high-blast-radius regardless of scope
