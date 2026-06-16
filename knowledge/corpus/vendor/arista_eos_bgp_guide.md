# Arista EOS BGP Configuration Guide — NOC Reference

## Overview
Arista EOS (Extensible Operating System) is Linux-based with a Cisco IOS-like CLI. Key differences from IOS: uses `vrf default` explicitly in some contexts, supports `switchport` and routing on the same switch, has a programmable API (eAPI) and state streaming (TerminAttr → Streaming Telemetry).

## Basic BGP Configuration
```
router bgp 65001
   router-id 1.1.1.1
   no bgp default ipv4-unicast
   neighbor 10.0.0.2 remote-as 65002
   neighbor 10.0.0.2 description eBGP_to_R2
   neighbor 10.0.0.2 update-source Loopback0
   !
   address-family ipv4
      neighbor 10.0.0.2 activate
      network 192.168.1.0/24
```
**Note**: `no bgp default ipv4-unicast` is Arista best practice — explicitly activate per address-family.

## Route Maps and Prefix Lists
```
ip prefix-list INBOUND_PREFIXES
   seq 10 permit 10.0.0.0/8 le 24
   seq 20 deny 0.0.0.0/0 le 32

route-map SET_LOCALPREF permit 10
   match ip address prefix-list INBOUND_PREFIXES
   set local-preference 200

route-map SET_LOCALPREF permit 20

router bgp 65001
   neighbor 10.0.0.2 route-map SET_LOCALPREF in
```

## BGP Peer Groups (Arista)
```
router bgp 65001
   neighbor IBGP peer group
   neighbor IBGP remote-as 65001
   neighbor IBGP update-source Loopback0
   neighbor IBGP send-community
   neighbor 1.1.1.2 peer group IBGP
   neighbor 1.1.1.3 peer group IBGP
```

## Community Configuration
```
router bgp 65001
   neighbor 10.0.0.2 send-community extended
   !
   route-map TAG_ROUTES permit 10
      set community 65001:100
```

## ECMP and Load Balancing
```
router bgp 65001
   maximum-paths 8 ecmp 8   ! up to 8 equal-cost paths
```

## Verification Commands
```
show ip bgp summary
show ip bgp neighbors 10.0.0.2
show ip bgp 192.168.1.0/24
show ip route bgp
show bgp evpn summary         ! EVPN for DC fabric
show ip bgp community 65001:100
```

## EOS vs IOS Differences (NOC Interview Context)
| Feature | IOS | Arista EOS |
|---|---|---|
| Default IPv4 activation | Auto | `no bgp default ipv4-unicast` required |
| Peer groups | Supported | Supported; preferred for scale |
| EVPN | IOS-XE/NX-OS only | Native EOS support for DC fabric |
| Config format | `router bgp; neighbor` | Same, but indentation matters |
| API | No native REST | eAPI (JSON-RPC over HTTPS) |
| Streaming telemetry | No | TerminAttr → OpenConfig or gNMI |

## Arista-Specific: EVPN-VXLAN BGP Configuration
```
! For DC fabric (spine/leaf)
router bgp 65001
   neighbor EVPN-PEERS peer group
   neighbor EVPN-PEERS remote-as 65000
   neighbor EVPN-PEERS ebgp-multihop 3
   neighbor EVPN-PEERS send-community extended
   !
   address-family evpn
      neighbor EVPN-PEERS activate
   !
   vlan 10
      rd 1.1.1.1:10010
      route-target import export 1:10010
      redistribute learned
```

## BFD for Fast Failover
```
router bgp 65001
   neighbor 10.0.0.2 bfd
```

## Common Arista Pitfalls
1. Forgetting `no bgp default ipv4-unicast` → IPv4 peer may not activate correctly under address-family
2. Using `neighbor activate` in global BGP context instead of under `address-family ipv4`
3. Missing `send-community` → communities not forwarded to peers
4. Multipath not enabled → traffic not load-balanced across ECMP paths
