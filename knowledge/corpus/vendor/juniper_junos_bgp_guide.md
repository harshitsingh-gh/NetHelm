# Juniper JunOS BGP Configuration Guide — NOC Reference

## Overview
JunOS uses a hierarchical configuration model in set notation or curly-brace format. Key difference from IOS: all configuration changes are staged in a `candidate` config and only applied on `commit`. Active config is called `running`, candidate is uncommitted changes. This makes rollback trivial (`rollback 1`).

## Configuration Structure
```
[edit]
set protocols bgp group EBGP type external
set protocols bgp group EBGP peer-as 65002
set protocols bgp group EBGP neighbor 10.0.0.2
set protocols bgp group EBGP export EXPORT-POLICY
set protocols bgp group EBGP import IMPORT-POLICY
set protocols bgp local-as 65001
set routing-options router-id 1.1.1.1
set routing-options autonomous-system 65001
```

## Policy Framework (JunOS)
JunOS uses a `policy-options` hierarchy instead of route-maps and prefix-lists:
```
set policy-options prefix-list INBOUND-PREFIXES 10.0.0.0/8
set policy-options prefix-list INBOUND-PREFIXES upto /24

set policy-options policy-statement IMPORT-POLICY term ACCEPT from prefix-list INBOUND-PREFIXES
set policy-options policy-statement IMPORT-POLICY term ACCEPT then local-preference 200
set policy-options policy-statement IMPORT-POLICY term ACCEPT then accept
set policy-options policy-statement IMPORT-POLICY term REJECT then reject
```

## Communities
```
set policy-options community CUSTOMER_TAG members 65001:100
set policy-options policy-statement TAG-ROUTES term 1 then community add CUSTOMER_TAG
set policy-options policy-statement TAG-ROUTES term 1 then accept
```

## Export Policy
```
set policy-options policy-statement EXPORT-CUSTOMER term NETS from route-filter 192.168.1.0/24 exact
set policy-options policy-statement EXPORT-CUSTOMER term NETS then accept
set policy-options policy-statement EXPORT-CUSTOMER term REJECT then reject
```

## Commit and Rollback
```
# Stage + verify + apply:
commit check   # validate only; no apply
commit         # apply staged config
rollback 1     # revert to previous committed config (up to 50 rollbacks stored)
rollback 0     # discard uncommitted changes

# Show diff between candidate and committed:
show | compare
```

## Verification Commands
```
show bgp summary
show bgp neighbor 10.0.0.2
show bgp neighbor 10.0.0.2 routes   # received routes
show bgp neighbor 10.0.0.2 advertised-routes
show route protocol bgp
show route 192.168.1.0/24 detail
show route advertising-protocol bgp 10.0.0.2
```

## JunOS vs IOS Key Differences (NOC Interview)
| Concept | IOS | JunOS |
|---|---|---|
| Config model | Active immediate | Candidate + commit |
| Rollback | `copy run start` → manual | `rollback N` |
| Route policy | route-map + prefix-list | policy-statement (unified) |
| BGP grouping | peer-groups | groups (stronger abstraction) |
| Import/export | `route-map X in/out` on neighbor | `import/export` on group |
| Communities | `ip community-list` | `community` in policy-options |
| MPLS/VPN | IOS-XR or MPLS config | Native JunOS L3VPN |

## Route Policy Terms (JunOS Evaluation Order)
JunOS policies are evaluated term-by-term within a policy, then policy-by-policy in import/export chains:
1. Terms are evaluated top-to-bottom
2. First match wins (like Cisco ACL)
3. If no term matches: default action is REJECT for export, ACCEPT for import (verify this per context)
4. `then accept` / `then reject` are terminal
5. `then next term` / `then next policy` continue evaluation

## iBGP with Route Reflectors
```
set protocols bgp group IBGP type internal
set protocols bgp group IBGP local-address 1.1.1.1
set protocols bgp group IBGP cluster 1.1.1.1      # this router is RR
set protocols bgp group IBGP neighbor 2.2.2.2
set protocols bgp group IBGP neighbor 3.3.3.3
```

## BFD
```
set protocols bgp group EBGP bfd-liveness-detection minimum-interval 300
set protocols bgp group EBGP bfd-liveness-detection multiplier 3
```

## Common JunOS Pitfalls for IOS Engineers
1. Forgetting `commit` — changes are not live until committed
2. `then accept` is not the default — must explicitly accept in each term
3. Import policy: JunOS default is to accept all (no implicit deny); export policy: default is to reject all
4. Policy chain order matters: policies are evaluated in the order listed; first accept/reject wins
5. `upto /N` in prefix-list means "match this prefix and any more-specific up to length N"
