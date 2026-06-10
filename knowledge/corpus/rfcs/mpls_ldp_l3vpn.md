# MPLS, LDP, and L3VPN — Protocol Reference and Blast Radius

## MPLS Fundamentals
MPLS (Multiprotocol Label Switching, RFC 3031) forwards packets based on short fixed-length labels rather than IP destination lookups. Labels are pushed, swapped, and popped at each hop.

**Key roles**:
- **PE (Provider Edge)**: customer-facing router; pushes/pops MPLS labels; runs BGP for VPN routes
- **P (Provider)**: core router; only swaps labels; has no customer routes; runs LDP/RSVP for label distribution
- **CE (Customer Edge)**: customer router; exchanges routes with PE (often via eBGP or static)

**Label stack**: MPLS supports stacked labels (label stack). Bottom-of-stack bit (S=1) marks the innermost label.
**Special labels**: 0 (IPv4 explicit null), 2 (IPv6 explicit null), 3 (implicit null / PHP), 13 (GAL), 14 (OAM alert)

**PHP (Penultimate Hop Popping)**: the router before the egress PE pops the top label, so the egress PE receives an IP packet or inner-labeled packet directly. Reduces lookup overhead at egress.

## LDP (Label Distribution Protocol — RFC 5036)
LDP distributes labels for IP prefixes along the shortest path. It binds a label to each FEC (Forwarding Equivalence Class, typically an IP prefix).

**Session setup**:
1. LDP discovery: sends hellos to 224.0.0.2 (all routers) via UDP port 646
2. TCP session on port 646 between LDP peers
3. Label bindings exchanged for all prefixes in the IP routing table

**LDP modes**:
- **Liberal label retention**: keep all received label bindings, even from non-best-path neighbors (faster reconvergence)
- **Conservative label retention**: only keep bindings from best-path neighbors (memory efficient)
- **Downstream Unsolicited (DU)**: peers advertise labels without being asked (default)
- **Downstream on Demand (DoD)**: labels only sent when requested

**LDP Targeted Sessions**: LDP sessions between non-directly-connected routers (used for AToM / pseudowires)

## LDP Blast Radius Patterns

### Pattern: LDP Adjacency Loss (Link Failure in MPLS Core)
**Trigger**: Physical link between two P routers fails.
**Chain**:
1. LDP hello adjacency drops
2. LDP TCP session tears down (if no alternate path)
3. Label bindings for FECs that went through that link are withdrawn
4. LFIB (Label Forwarding Information Base) updated
5. Traffic using those labels is forwarded via alternate LSP (if LDP reconverges) or dropped

**D-dimensions**:
- D3: Traffic on affected LSPs disrupted during reconvergence
- D7: LSP paths change after reconvergence
- D1/D2: BGP sessions/prefixes unaffected if IP connectivity maintained via alternate path

### Pattern: LDP-BGP Synchronization Failure
**RFC 5443 (LDP-IGP Synchronization)**: prevents traffic from being sent on a link where LDP hasn't fully exchanged labels yet, even if the IGP sees the link as up.

**Without sync**: Link recovers → IGP routes traffic over it → LDP labels not yet distributed → packets forwarded with no label → P routers drop unlabeled packets → black hole until LDP completes (typically 1–5 seconds).

**This is a common cause of brief post-convergence packet loss** even when no net failure occurs — the IP path is up but MPLS forwarding isn't ready.

### Pattern: P Router LDP Restart
**Trigger**: `clear mpls ldp` or daemon restart on a core P router
**Effect**: All LDP sessions from that router torn down; label bindings withdrawn; LSPs through that router lose their labels
**For BGP-free core**: P routers have no BGP routes; if MPLS labels are gone and there's no IP fallback, traffic drops
**For IP+MPLS core**: traffic falls back to IP forwarding (penalizes P router processing)
**D3**: transient or sustained packet loss depending on reconvergence speed

---

## L3VPN (MPLS VPN — RFC 4364)

### Architecture
L3VPN carries customer IP traffic over an MPLS core, isolating customers in separate VRFs (Virtual Routing and Forwarding tables).

**Key concepts**:
- **VRF (VPN Routing and Forwarding)**: per-customer routing table on PE
- **RD (Route Distinguisher)**: 8-byte prepended to VPN routes to make them unique in BGP (64-bit: AS:NN or IP:NN)
- **RT (Route Target)**: BGP extended community controlling VRF import/export
- **MP-BGP VPNv4/v6**: carries VPN routes between PEs using AFI=1, SAFI=128
- **Label stack**: VPN traffic carries inner label (identifies VRF/CE on egress PE) + outer label (identifies egress PE via LDP/RSVP-TE)

### L3VPN Blast Radius Patterns

#### Pattern: PE-CE Link Failure
**Trigger**: Link between PE and CE fails.
**Chain**:
1. CE loses PE adjacency (eBGP, static, or OSPF)
2. PE removes CE routes from the customer VRF
3. PE withdraws VPNv4 routes for the CE's prefixes via MP-BGP
4. Remote PEs remove the withdrawn VPN routes from their VRFs
5. Remote CEs cannot reach the affected CE's prefixes
**D-dimensions**: D2 (VPN prefixes lost), D3 (reachability to that CE lost), D5 (if redundant PE connections existed, redundancy degraded)

#### Pattern: PE Router Failure
**Trigger**: PE router crashes or is rebooted.
**Chain**:
1. All PE-CE sessions on that PE torn down
2. MP-BGP sessions to other PEs torn down
3. All VPN routes that PE was advertising → withdrawn globally
4. All VPN routes that PE was learning → lost (cached for BGP Graceful Restart if configured)
5. All customers homed to that PE lose connectivity
**D1**: ALL BGP sessions (PE-CE and PE-PE VPNv4/v6)
**D2**: ALL VPN routes from all customers on that PE
**D3**: Complete loss for all attached customers

#### Pattern: Route Target Misconfiguration (VRF Import/Export Error)
**Trigger**: RT on a VRF changed to a non-matching value. Customer A PE VRF exports RT=65001:100; customer B PE VRF expects import RT=65001:200.
**Effect**: Customer B cannot receive Customer A's routes. D2 (VPN prefixes appear missing at customer B), D3 (customer B cannot reach customer A), but MP-BGP session stays up. The misconfiguration is silent — no error messages, just missing routes.

#### Pattern: VRF Route Leak (Security Violation)
**Trigger**: Customer A's RT accidentally included in Customer B's import policy.
**Effect**: Customer A routes appear in Customer B's VRF — VPN isolation breach. D4 (waypoint violation — Customer B traffic may route into Customer A's space), D6 (filter policy changed).
**This is a security incident, not just a blast-radius event** — requires immediate remediation.

#### Pattern: MPLS Label Exhaustion
**Trigger**: MPLS label space on a PE or P router exhausted (typically 16 labels per platform minimum, up to 1M on high-end).
**Effect**: New LSPs or VPN routes cannot be allocated labels; new customer VRFs cannot be provisioned; in extreme cases, existing LSPs may be de-allocated.
**D8 (Scale violation)**: This is the primary D8 scenario for MPLS.

---

## LDP vs RSVP-TE for Label Distribution
| Feature | LDP | RSVP-TE |
|---|---|---|
| Path selection | IP shortest path | Explicit ERO (traffic engineered) |
| Setup | Automatic, follows IGP | Explicit signaling |
| Bandwidth reservation | No | Yes |
| FRR (Fast Reroute) | LFA/rLFA | FRR with pre-computed bypass tunnels |
| Scalability | High (O(prefixes)) | Lower (O(tunnels)) |
| Blast radius of path change | IP convergence drives it | Explicit reroute required |

---

## Batfish MPLS/LDP Support
**Current status**: Batfish has LIMITED MPLS/LDP modeling.
- Basic MPLS config parsing for some platforms
- LDP sessions NOT directly modeled
- MPLS forwarding plane (LFIB) NOT available as a question
- L3VPN VRF modeling: partial — VRF route tables may be queryable but VPN label forwarding is not
- **For NetHELM blast-radius testing of MPLS scenarios**: use BGP-level metrics (MP-BGP VPNv4 session status, VPN prefix counts) as proxies; do not rely on MPLS label-level analysis from Batfish
