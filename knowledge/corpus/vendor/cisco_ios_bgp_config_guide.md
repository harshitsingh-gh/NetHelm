# Cisco IOS BGP Configuration Guide — NOC Reference

## Basic BGP Configuration (IOS)
```
router bgp 65001
 bgp router-id 1.1.1.1
 neighbor 10.0.0.2 remote-as 65002
 neighbor 10.0.0.2 description eBGP_to_R2
 neighbor 10.0.0.2 update-source Loopback0
 !
 address-family ipv4 unicast
  network 192.168.1.0 mask 255.255.255.0
  neighbor 10.0.0.2 activate
  neighbor 10.0.0.2 soft-reconfiguration inbound
 exit-address-family
```

## iBGP with Route Reflector
```
! On Route Reflector:
router bgp 65001
 neighbor 1.1.1.1 remote-as 65001
 neighbor 1.1.1.1 update-source Loopback0
 neighbor 1.1.1.1 route-reflector-client
 neighbor 2.2.2.2 remote-as 65001
 neighbor 2.2.2.2 update-source Loopback0
 neighbor 2.2.2.2 route-reflector-client
```

## Route Maps and Prefix Lists
```
ip prefix-list INBOUND_FILTER seq 5 permit 10.0.0.0/8 le 24
ip prefix-list INBOUND_FILTER seq 10 deny 0.0.0.0/0 le 32

route-map SET_LOCALPREF permit 10
 match ip address prefix-list INBOUND_FILTER
 set local-preference 200
route-map SET_LOCALPREF permit 20

router bgp 65001
 neighbor 10.0.0.2 route-map SET_LOCALPREF in
```

## BGP Communities
```
ip community-list standard CUSTOMER_ROUTES permit 65001:100
!
route-map TAG_CUSTOMER permit 10
 match community CUSTOMER_ROUTES
 set local-preference 300
```

## AS-Path Filtering
```
ip as-path access-list 1 permit ^65002$
ip as-path access-list 2 deny .*

route-map FILTER_ASPATH permit 10
 match as-path 1
route-map FILTER_ASPATH deny 20
 match as-path 2
```

## Maximum Prefix (Safety)
```
router bgp 65001
 neighbor 10.0.0.2 maximum-prefix 1000 90 warning-only
 ! 1000 = limit, 90 = warning threshold %, warning-only = log but don't tear down
 ! Remove "warning-only" to actually tear down session on overflow
```

## BGP Soft Reset
```
clear ip bgp 10.0.0.2 soft in    ! re-apply inbound policy without session reset
clear ip bgp 10.0.0.2 soft out   ! re-advertise all routes outbound
clear ip bgp 10.0.0.2            ! hard reset — tears down and rebuilds session
```

## Verification Commands
```
show ip bgp summary                    ! all neighbors, state, prefixes
show ip bgp neighbors 10.0.0.2        ! full detail for one neighbor
show ip bgp                            ! full BGP table
show ip bgp regexp ^65002$             ! filter by AS-path regex
show ip route bgp                      ! BGP routes in RIB
show ip bgp 192.168.1.0               ! specific prefix detail
debug ip bgp 10.0.0.2 events          ! session events (use carefully in prod)
```

## Common Misconfigurations and Symptoms
| Misconfiguration | Symptom | Fix |
|---|---|---|
| AS number mismatch | OPEN error, session stays Active | Verify `remote-as` matches peer's AS |
| update-source not set for iBGP | Session flaps, Source IP mismatch | Add `update-source Loopback0` |
| Missing `network` statement | Prefix not in BGP table | Add `network` + verify route exists in RIB |
| route-map not applied | Policy not taking effect | Verify `neighbor X route-map Y in/out` |
| next-hop not reachable | Route in BGP table but not RIB | Check IGP for next-hop; `next-hop-self` for iBGP |
| Hold timer mismatch | Session up but flaps | Default: 180s hold, 60s keepalive; must match |
| Missing `soft-reconfiguration inbound` | Can't use `clear ip bgp soft in` | Add under neighbor or use `route-refresh` capability |

## OSPF-BGP Redistribution
```
router ospf 1
 redistribute bgp 65001 subnets   ! inject BGP into OSPF

router bgp 65001
 redistribute ospf 1              ! inject OSPF into BGP (use with care — loop risk)
```

## BFD for BGP Fast Failover
```
interface GigabitEthernet0/0
 bfd interval 300 min_rx 300 multiplier 3

router bgp 65001
 neighbor 10.0.0.2 fall-over bfd
```

## RPKI Configuration (Cisco IOS-XR style)
```
router bgp 65001
 rpki server 192.0.2.1
  transport tcp port 3323
  refresh-time 600
 !
 address-family ipv4 unicast
  bgp origin-as validation signal ibgp
  ! Drop invalid routes:
  neighbor 10.0.0.2 validation
```
