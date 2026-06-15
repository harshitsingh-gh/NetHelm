# Cross-Protocol RIB Arbitration — Redistribution + Administrative-Distance Shadow Reroute

## Summary
One of the oldest and most under-recognized silent-reroute classes: the *same*
destination prefix is reachable two ways on a router — via the intended BGP path and,
after a redistribution change, via a redistributed IGP copy of the same prefix. The
router's RIB does NOT use the BGP best-path decision to choose between them; it uses
**administrative distance (AD)**, a per-protocol trust ranking applied in zebra/the RIB
*after* each protocol has already selected its own best route. Because **OSPF (AD 110)
beats iBGP (AD 200)**, the redistributed IGP route silently wins the FIB and traffic
stops transiting the BGP-path node — while reachability is fully preserved. The BGP route
remains "best" in the BGP RIB the whole time; the operator who verifies BGP sees nothing
wrong.

This is a textbook *quiet* failure: nothing is withdrawn, no session drops, the
destination is still in the RIB and still reachable. Only the *path* changed, and only a
path/waypoint-aware check can see it. It is the cross-protocol analogue of the
more-specific-leak (Cloudflare/Verizon 2019), but the decisive arbiter is AD across
protocols, not longest-prefix-match within BGP.

## The Administrative-Distance Asymmetry (the root of most redistribution accidents)
When a router has the same prefix from two protocols, it installs the one with the lowest
administrative distance. The dangerous asymmetry:

| Source | Default AD (Cisco/FRR) |
|---|---|
| Connected | 0 |
| Static | 1 |
| eBGP | 20 |
| OSPF (intra/inter/external) | 110 |
| IS-IS | 115 |
| RIP | 120 |
| iBGP | 200 |

- **eBGP (20) BEATS OSPF (110)** — redistributing a destination into OSPF will NOT steal
  it from an eBGP-learned router.
- **iBGP (200) LOSES to OSPF (110)** — redistributing a destination into OSPF WILL steal
  it from a router that learned it over iBGP.

That single asymmetry — iBGP loses, eBGP wins — is the source of most redistribution
accidents. The waypoint/inspection scenario only fires when the protected path is learned
over **iBGP**, which is exactly the common case inside a single AS where a scrubbing /
firewall / DPI / LI node advertises the customer prefix into iBGP.

Verified against FRR docs: zebra selects the lowest-AD route at FIB-install time,
independent of each protocol's own best-path logic
(https://docs.frrouting.org/en/latest/zebra.html). Confirmed default distances per
FRR/Cisco and Wikipedia's AD table (https://en.wikipedia.org/wiki/Administrative_distance).

## The Mechanism (NetBrace `redistribute-ad-shadow-reroute`)
- **PRE**: `src` reaches customer prefix `203.0.113.0/24` only via the iBGP best path
  through `way` (the mandated waypoint). AD 200, single RIB route, installed.
- **DIFF**: `redistribute connected route-map RC_CUSTOMER` (or `redistribute static`)
  added under `router ospf` on `alt` — the bypass-side router that *also* has connected
  reachability into the customer space. Framed in the change ticket as a **redundancy
  improvement** ("add a second path to the customer").
- **POST**: `src` now has the iBGP route (AD 200) AND a redistributed OSPF external Type-5
  route (AD 110, the SAME /24). Zebra installs the OSPF route. `src` forwards via `alt`,
  bypassing `way` entirely. Reachability preserved; the waypoint invariant is broken.

**Critical: this requires equal prefix length (/24 vs /24).** If the redistributed copy
were a more-specific (/25), the arbiter would be longest-prefix-match and it would
degenerate into the Cloudflare-style leak. Here both routes are /24, so AD — not LPM — is
the decider. That is what makes it a structurally distinct mechanism.

## Why It Is Quiet (maps to D4 + D10 only)
- **D1 (sessions)**: empty. `redistribute` under `router ospf` resets no BGP FSM and no
  OSPF adjacency.
- **D2 (prefixes)**: empty. `203.0.113.0/24` is present in `src`'s RIB before and after —
  re-sourced ibgp→ospfE2, not lost. A whole-network `routes()` set-diff is empty.
- **D3 / D7 (reachability / forwarding)**: empty. `src→203.0.113.1` is ACCEPTED pre and
  post; `alt` genuinely delivers (this is the falsification gate — if `alt` cannot
  actually deliver, D3+D7 fire and the scenario is correctly disqualified as LOUD).
- **D5 (redundancy)**: empty. Installed-next-hop count is 1 before and 1 after; the
  surface reading is even "redundancy gain."
- **D9 (BGP best-path)**: empty. The iBGP route is still `BEST` in the BGP RIB — BGP is
  unaware it lost the RIB contest to another protocol.
- **D4 + D10**: FIRE. The winning RIB route moved from BGP-via-`way` to IGP-via-`alt`;
  traffic stops transiting the mandated node and the intent invariant breaks.

## Real-World Grounding
- **Documented mechanism (war-story grade)**: "Asymmetric routing caused by unfiltered
  redistribution," netquirks (2016). A dual-homed breakout site through a firewall: CE2
  redistributes eBGP routes into OSPF unfiltered; CE1 learns them via OSPF (AD 110) and
  installs the OSPF path over its own iBGP-redistributed copy (AD 200). Traffic is still
  delivered but takes an asymmetric path — the iBGP-200-loses-to-OSPF-110 contest is the
  exact decider described here.
  https://netquirks.co.uk/2016/10/16/asymmetric-routing-caused-by-unfiltered-redistribution/
- **Modern analogue (documented, cloud)**: "Top asymmetric routing issues and unexpected
  firewall bypass in Azure," S. Eyskens, Microsoft Azure (Medium). System routes (VNET
  peering / gateway propagation) silently win over the user-defined route-table path that
  forces traffic through the firewall/NVA; traffic still reaches the destination but
  bypasses the mandated firewall — "traffic passed through the firewall while it didn't."
  Same *signature* (delivery preserved, mandated inspection node silently bypassed by a
  route-preference contest the operator did not expect), different routing substrate.
  https://medium.com/microsoftazure/top-asymmetric-routing-issues-and-unexpected-firewall-bypass-in-azure-7456a1c1a9ff
- **Vendor confirmation that the asymmetry is the known footgun**: Cisco redistribution
  guidance and community Q&A repeatedly flag the eBGP-20-beats-OSPF-110 /
  iBGP-200-loses-to-OSPF-110 trap as the canonical redistribution accident
  (https://www.cisco.com/c/en/us/support/docs/ip/enhanced-interior-gateway-routing-protocol-eigrp/8606-redist.html).

Confidence note: unlike the Cloudflare leak, there is no single famous *carrier-scale
named outage* for the AD-shadow-reroute — it shows up as internal-enterprise asymmetry /
firewall-bypass incidents and audit findings, which are rarely published with the company
named. The mechanism itself is documented and vendor-acknowledged; the specific
"bypassed-the-mandated-inspection-node" framing is best supported by the Azure
firewall-bypass write-up (analogous substrate) plus the netquirks redistribution case
(same AD contest).

## Key Lessons for NetBrace
1. **Cross-protocol RIB arbitration is invisible to a BGP-only reasoner.** A model (or
   engineer) that checks "is the BGP route still best?" answers correctly — and is still
   wrong about forwarding. The decisive step lives in a different protocol's namespace.
2. **"Add redundancy" changes can silently re-source delivery.** The surface action is the
   opposite of a steering edit, which is exactly why it slips review.
3. **The iBGP-vs-OSPF AD asymmetry is the load-bearing invariant** for the generator:
   the protected path MUST be iBGP (AD 200), and the redistributed copy MUST be the same
   prefix length, or the mechanism does not fire / degenerates into the leak.

## Related
- `cloudflare_bgp_leak_jun2019.md` — the in-BGP more-specific analogue (LPM, not AD).
- `rr_bestpath_hiding.md` — another quiet, path-only reroute (RR best-path hiding).
- `drain_undrain_localpref_restore.md` — quiet LOCAL_PREF path moves.
