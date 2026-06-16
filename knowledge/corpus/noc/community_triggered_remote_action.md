# Community-Triggered Remote Action — Weaponizing Your Own Latent Policy

## What it is

A BGP **action community** is a tag a network publishes so that *neighbors* can
remotely steer how that network treats their routes: lower LOCAL_PREF, add MED,
AS-path prepend, or trigger Remote-Triggered Blackholing (RTBH). The action is
performed by the **receiving** AS's own, pre-existing inbound route-map — the
sender only attaches a 16:16 tag.

The security problem: BGP communities carry **no origin authentication** (RFC 1997
defines no validation). If an AS does not scrub inbound communities, a **remote /
non-customer party** can attach an action community that the victim AS honors,
triggering a routing change *inside a policy the victim wrote long ago and never
touched*. This is action-at-a-distance: the offending config edit is on a node the
victim does not control; the consequence fires in the victim's untouched route-map.

## Why it matters for blast radius (quiet half: D4 + D10)

Most documented abuse is RTBH (a **loud** D3/D7 blackhole — traffic dropped). But
the IMC 2018 measurement explicitly lists **"change the local preference / MED"**
and **AS-path prepend** as abusable actions. These are **reachability-preserving
reroutes**: the route stays in every RIB, the best-path flips to an alternate that
still delivers, and the only thing that changes is *which path traffic takes*.

If the de-preferred path was the one steered through a **mandated waypoint**
(DDoS scrubbing center, DPI/inspection node, lawful-intercept tap, mandated transit
AS), the result is a pure **quiet-half** event:

- D1 (sessions) ∅ — a community is an attribute; it never touches the FSM.
- D2 (prefixes) ∅ — prefix present on both paths in every RIB; only LP changes.
- D3 (reachability) ∅ / D7 (forwarding) ∅ — the alternate genuinely delivers.
- D5 (redundancy) ∅ — strict LP gap → single best path both snapshots, no ECMP flip.
- **D4 (waypoint) VIOLATED + D10 (intent) VIOLATED** — the delivered trace no longer
  transits the mandated node.

This is the exact damage signature of a more-specific route leak, reached by a
**different cause**: a community-string match firing a latent LP clause, not LPM.

## Operational reality

- **Scrubbing-center diversion is community-controlled and on-demand** — standard
  practice (FastNetMon, Radware, Noction, NANOG). Traffic is steered to the scrubber
  by a community-tagged announcement; LP decides scrubber-path vs. direct-path. A
  party that learns the community list can **suppress/de-pref the scrubber steering**
  and ride the direct path — bypassing inspection while traffic still arrives.
- **Propagation is wide enough to be remote, not just adjacent:** the IMC 2018 study
  found **14% of transit ASes (≈2.2k of 15.5k) forward received communities onward**,
  so a tag set several hops away can reach and trigger a distant victim's policy.
- **Operators are explicitly told to defend against this** — RFC 7454 §11 ("BGP
  Community Scrubbing") says admins **SHOULD scrub inbound communities carrying their
  own ASN in the high-order bits**, allowing only customer/peer signaling communities.
  The very existence of this guidance is proof the default-open posture is a real,
  recognized foot-gun, and that plenty of networks have not closed it.

## Detection / why a model misses it

The model-visible diff is on the **foreign** node (an additive `set community` +
`send-community` on the peer's egress). There is **no `set local-preference` line in
the diff**. The operative LP-lowering clause lives in the victim's *unchanged*
baseline config on a *different* node. To predict the blast radius a model must:
(1) parse a 16-bit community added at the peer, (2) cross-reference the victim's
community-list and ingress route-map shown only as background, (3) see that the term
now matches where it previously fell through, (4) re-run best-path. Strictly more
indirect than an explicit LOCAL_PREF edit (`lp_waypoint`, caught at 1.00 recall).

## References

- Streibelt, Lichtblau, Beverly, Feldmann, Pelsser, Smaragdakis, Bush,
  **"BGP Communities: Even more Worms in the Routing Can," ACM IMC 2018**
  (IRTF Applied Networking Research Prize 2019).
  <https://gsmaragd.github.io/publications/IMC2018-Communities-attacks/>
- RIPE Labs, **"BGP Communities — A Weapon for the Internet (Part 1 & 2)"** —
  "14% of transit providers are propagating received communities … 2.2k out of
  15.5k ASes"; abusable actions: "path prepending, … change the local preference /
  MED or … RTBH."
  <https://labs.ripe.net/author/florian_streibelt/bgp-communities-a-weapon-for-the-internet-part-2/>
- **RFC 7454 §11 — BGP Operations and Security, "BGP Community Scrubbing"**:
  admins SHOULD scrub inbound communities with their own number in the high-order
  bits. <https://www.rfc-editor.org/rfc/rfc7454#section-11>
- **RFC 1997 — BGP Communities Attribute** (no origin validation defined).
  <https://www.rfc-editor.org/rfc/rfc1997>
- DDoS scrubbing diversion is community/BGP-controlled and on-demand (operational
  context). <https://www.noction.com/blog/ddos-scrubbing>
