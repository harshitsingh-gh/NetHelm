# RSVP-TE and Traffic Engineering — Reference and Blast Radius

## Overview
RSVP-TE (Resource ReSerVation Protocol - Traffic Engineering, RFC 3209) extends RSVP to signal explicitly-routed MPLS LSPs (Label Switched Paths) with bandwidth guarantees. It was the dominant TE mechanism before Segment Routing but remains widely deployed.

## RSVP Signaling
**PATH message**: sent from ingress to egress along the ERO (Explicit Route Object). Establishes soft-state at each hop.
**RESV message**: sent from egress back to ingress along the path, confirming bandwidth allocation and distributing labels.
**RESV tear** / **PATH tear**: explicit cleanup messages.
**RSVP soft state**: PATH/RESV state must be refreshed periodically (default every 30s) or it expires. Missing refresh → state torn down.

## ERO (Explicit Route Object)
The ERO specifies the exact path for the TE tunnel as a list of strict/loose hops:
- **Strict hop**: must be directly connected to the previous hop
- **Loose hop**: intermediate hops may exist between this hop and the previous one

```
tunnel mpls traffic-eng path-option 1 explicit name PATH_A
  ip explicit-path name PATH_A enable
    next-address strict 10.0.0.1   ! R1
    next-address strict 10.0.0.2   ! R2 (must be directly connected to R1)
    next-address loose  10.0.0.5   ! R5 (can have intermediate hops)
```

## RSVP-TE Blast Radius Patterns

### Pattern: TE Tunnel Head-End to Tail-End Path Failure
**Trigger**: A link in the ERO fails.
**Chain**:
1. RSVP PATH message can no longer reach next strict-hop
2. RSVP sends PathErr (path error) back to ingress
3. Ingress attempts failover to secondary path-option (if configured)
4. If no secondary path: tunnel goes down; traffic falls back to IGP (if fallback configured)

**D-dimensions**:
- D3: Traffic on failed tunnel disrupted until failover (seconds to minutes)
- D7: Path changes to secondary (fallback) path
- D5: If only one path-option, redundancy lost completely

### Pattern: RSVP State Expiry (Refresh Failure)
**RSVP soft state** requires periodic refresh. If PATH/RESV refresh fails:
- Default refresh interval: 30s
- Default timeout: 3.5× refresh interval (~105s)
- 3.5 minutes without refresh → RSVP state torn down → tunnel down

**Trigger**: CPU overload, queue congestion, or packet loss on the RSVP signaling path causes refresh packets to be dropped.
**Blast radius**: tunnel goes down → traffic on that tunnel drops or falls to IGP.
**RSVP Summary Refresh (RFC 2961)**: reduces refresh overhead by summarizing multiple state entries.

### Pattern: Bandwidth Oversubscription
**Trigger**: Multiple TE tunnels compete for bandwidth on a link. CSPF (Constrained Shortest Path First) computes paths considering bandwidth constraints. If a new tunnel request cannot be accommodated, it fails (ADMISSION CONTROL).
**Effect**: New tunnels can't be established; existing tunnels unaffected.
**D8 (Scale)**: this is the TE equivalent of the scale dimension — resource (bandwidth) exhaustion.

### Pattern: CSPF Database Inconsistency
CSPF uses TE-LSA/TE-LSP data from IS-IS/OSPF TE extensions. If this data is stale (slow LSA propagation), CSPF computes a path based on old bandwidth/availability → RSVP signaling fails (ADMISSION FAILURE at a downstream node).
**Effect**: Tunnel fails to establish or flaps.

### Pattern: TE Preemption (Priority-Based Eviction)
TE tunnels have setup priority and hold priority (0=highest, 7=lowest). A higher-priority tunnel can preempt (evict) a lower-priority tunnel from a link's bandwidth.
**Trigger**: New high-priority tunnel requested on an already-full link.
**Effect**: Lower-priority tunnel is evicted → torn down → traffic drops or finds alternate path.
**D1** (tunnel-level session): 1 tunnel torn down. **D3**: traffic on evicted tunnel disrupted.

---

## FRR (Fast Reroute) for RSVP-TE

### Facility Backup (Make-Before-Break)
Pre-computes a bypass tunnel around each potential failure point:
- **Node protection**: bypass tunnel skips the protected node entirely
- **Link protection**: bypass tunnel skips the protected link

**Trigger**: link or node failure detected (BFD sub-second or RSVP hello)
**Recovery time**: ~50ms with pre-computed bypass tunnel
**Blast radius with FRR**: D3 transient (50ms), D7 (path changes to bypass)

### Limitations of RSVP-TE FRR vs SR-TE TI-LFA
| Feature | RSVP-TE FRR | SR TI-LFA |
|---|---|---|
| Setup | Pre-signaled bypass tunnels | Pre-computed segments in IGP |
| State per node | Yes (bypass tunnel state) | No (source-routing) |
| Configuration | Complex (per-tunnel protection) | Simple (enable TI-LFA in IGP) |
| Coverage | Link and node | Any topology |

---

## OSPF TE Extensions (RFC 3630) and IS-IS TE Extensions (RFC 5305)
TE-aware IGPs distribute link TE attributes:
- Maximum bandwidth
- Maximum reservable bandwidth
- Unreserved bandwidth (per priority level, 0–7)
- TE metric (may differ from IGP metric)
- Administrative group (color/affinity)
- SRLG (Shared Risk Link Group)

**SRLG (Shared Risk Link Group)**: group of links that share a physical risk (same fiber, same duct, same DWDM wavelength). If you don't want both the primary and backup path to share an SRLG, you must configure SRLG-disjoint path computation.

**Blast radius of SRLG failure**: if primary and backup tunnels share an SRLG and the underlying failure affects the entire SRLG, both paths fail simultaneously. This eliminates intended redundancy. D5 (redundancy) goes to zero.

---

## TE Tunnel Types and NetHELM Relevance

| Tunnel Type | Mechanism | Batfish Modellable? |
|---|---|---|
| RSVP-TE explicit path | RSVP signaling | Partially (config only) |
| SR-TE policy | SR segment list | No |
| LDP-based LSP | LDP label distribution | No |
| Static MPLS label | Manual label config | No |
| IP-IP tunnel | IP encapsulation | Yes (forwarding analysis) |
| GRE tunnel | GRE encapsulation | Yes |

**Key takeaway**: Batfish can analyze the blast radius of GRE and IP-IP tunnels correctly. RSVP-TE and SR-TE require live testing or specialized tools (e.g., Cisco WAE, Juniper NorthStar).
