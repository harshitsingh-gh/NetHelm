# BFD Cascade Failures and False Positives — Blast Radius Patterns

## What BFD Is
BFD (Bidirectional Forwarding Detection, RFC 5880) is a subsecond failure detection protocol. It runs between two endpoints and sends control packets at a configured interval (e.g., every 300ms). If a configurable number of consecutive packets are missed (typically 3), BFD declares the path down and notifies the routing protocol (BGP, OSPF, IS-IS, etc.), which then takes the failure action (withdraw routes, tear down session).

**Purpose**: Default BGP/OSPF hold timers are 180s/40s respectively. BFD enables sub-second detection regardless of which upper-layer protocol is used.

## BFD Parameters
```
bfd interval <tx_interval_ms> min_rx <rx_interval_ms> multiplier <N>
```
- `tx_interval`: how often to send BFD packets (milliseconds)
- `min_rx`: minimum receive interval accepted from peer
- `multiplier`: number of missed packets before declaring failure
- **Detection time** = `max(tx_interval, min_rx) × multiplier`
- Example: `interval 300 min_rx 300 multiplier 3` → detects failure in 900ms

## BFD False Positive Scenarios (High Blast Radius Risk)

### Scenario A: CPU Overload Causing BFD Packet Drops
**Trigger**: Router CPU under high load (e.g., large BGP table processing, BGP route reflector churn, OSPF SPF storm)
**Mechanism**: BFD packets are normally high-priority but can be delayed or dropped under extreme CPU load on certain platforms.
**Effect**: BFD detects "failure" on all sessions simultaneously because no BFD packets are processed.
**Result**: All BGP/OSPF adjacencies using BFD are torn down simultaneously.
**Blast radius**: D1 = ALL sessions, D2 = ALL prefixes, D3 = complete reachability loss.

**Why this is a cascade**: BFD tears down BGP sessions → BGP re-convergence → CPU spike from BGP processing → BFD continues to false-positive → sessions come up → routes install → CPU spike again → loop.

### Scenario B: Asymmetric BFD Interval Configuration
**Trigger**: Peer A configured with `multiplier 3`, Peer B with `multiplier 10`. Or mismatched tx_interval.
**Mechanism**: BFD session negotiates to the higher value, but one side may not correctly honor the negotiation.
**Effect**: Intermittent BFD session failures under marginal link conditions.

### Scenario C: BFD in Virtualized Environments
**Trigger**: BFD running on VMs or container-based routers (FRR in docker/containerlab).
**Mechanism**: VM scheduling jitter causes BFD packet delays. The host hypervisor may not schedule the VM container frequently enough to send/receive BFD packets within the interval.
**Effect**: BFD false positives in lab environments. This is a known issue with FRR in containerlab.

**NetHELM implication**: Do NOT use BFD in the frr_square lab unless specifically testing BFD failure scenarios. BFD is unreliable in containerized environments.

### Scenario D: BFD Single-Hop vs. Multi-Hop Mismatch
**Trigger**: eBGP neighbor over multiple hops uses single-hop BFD mode (sbfd not configured).
**Mechanism**: Single-hop BFD fails if TTL < 255; multi-hop BGP often has TTL > 1.
**Effect**: BFD session fails immediately or sporadically.
**Fix**: Use `bfd multihop` for eBGP peers over more than 1 hop.

## BFD-Triggered BGP Blast Radius
When BFD tears down a BGP session:
1. BGP session enters Idle state immediately (not the normal Hold Timer expiry process)
2. All routes from that session are immediately withdrawn from the RIB
3. BGP sends NOTIFICATION to the peer (Cease) if the TCP connection is still up
4. The fast withdrawal means the blast radius is realized immediately, without the 3-minute buffer of hold timer expiry

**Blast radius compared to Hold Timer expiry**:
- Hold timer: 180s to detect failure; routes withdrawn at ~180s mark
- BFD: <1s to detect failure; routes withdrawn within 1s
- From an impact perspective: BFD gives faster recovery (if failure is real) but if false positive, causes unnecessary disruption faster

## BFD for OSPF
BFD on OSPF links shortens the failure detection from 40s (4× 10s dead interval) to sub-second.
**Blast radius when BFD false-fires on OSPF**:
- OSPF neighbor torn down immediately
- LSA update triggered
- SPF re-run
- BGP next-hop re-evaluated
- If BGP next-hop was resolved via the now-torn-down OSPF adjacency: BGP prefixes withdrawn from FIB
- D1: BGP sessions using OSPF-resolved next-hops affected
- D2: All prefixes whose next-hops resolved via the failed OSPF adjacency

## BFD Echo Mode
BFD echo mode: the sending router sends echo packets, the receiving router loops them back. The sender uses this to test bidirectional path quality without requiring the remote end to process BFD control packets at high frequency.

**Blast radius implication**: Echo mode failures are asymmetric — one end detects the failure, the other doesn't. This can cause one-sided route withdrawal while the other side still believes the session is up.

## Platform-Specific Notes
- **Cisco IOS/IOS-XE**: BFD offloaded to hardware on high-end platforms; not susceptible to CPU-induced false positives. Lower-end platforms (ISR routers): software BFD, CPU-sensitive.
- **Arista EOS**: BFD supported on all platforms; generally hardware-assisted.
- **Juniper**: BFD integrated with routing engine; can be moved to microkernel (distributed BFD) on high-end platforms.
- **FRR**: Software BFD only; susceptible to container scheduling jitter.

## NetHELM Scenario: BFD-Triggered Global Failure
A valid NetHELM scenario class:
- Pre: All BGP sessions up with BFD enabled
- Change: BFD minimum interval reduced from 300ms to 50ms with multiplier 3 (detection time 150ms)
- Expected blast radius: sessions are now fragile — any CPU spike or link jitter will cause 150ms of missed packets → session teardown → D1/D2/D3 impact
- LLM task: identify that this change increases blast-radius risk even though no sessions are currently down
