# Drain / Un-Drain LOCAL_PREF and the "Restore Against Drifted Context" Failure Mode

## What the drain procedure is (documented mechanism)

To take an edge/link/node out of service WITHOUT dropping packets, operators
"drain" it by making its paths less preferred so traffic shifts to an alternate
*before* the link is physically touched. The standard BGP mechanism is to lower
LOCAL_PREF on the routes via the draining edge.

- **RFC 8326 (Graceful BGP Session Shutdown)** defines the GRACEFUL_SHUTDOWN
  well-known community (65535:0). Receiving routers set **LOCAL_PREF to a low value
  (RECOMMENDED 0)** for paths carrying it, so those paths "remain in use while
  alternate paths are selected and propagated" — i.e. reachability is preserved
  throughout the drain. Source: https://www.rfc-editor.org/rfc/rfc8326.html
- **Arista EOS Maintenance Mode** implements exactly this: the default maintenance
  BGP profile applies a route-map with `set community GSHUT additive` and
  `set local-preference 0` to drain a switch before maintenance.
  Source: https://www.arista.com/en/um-eos/eos-maintenance-mode
- Cisco / Juniper / Pluribus / Palo Alto all document GSHUT/graceful-shutdown
  drain via LOCAL_PREF lowering (RFC 8326 implementations).

Throughout a correctly executed drain: **D1=∅** (LOCAL_PREF is an attribute; the
eBGP FSM is never reset), **D2=∅** (the prefix is still advertised on both edges,
never withdrawn), **D3=∅ / D7=∅** (the alternate is a real delivery path),
**D5=∅** (the drained path is kept as a live, lower-preference alternative). The
only thing that changes is *which* edge carries the traffic.

## The restoration gap (why this is a recurring trap)

RFC 8326 specifies the shutdown procedure in detail but is **silent on
restoration** — it does not define how/when to remove the drain or warn that
traffic may not return if you forget. Vendor docs add only a weak reminder ("on
completion of the maintenance window, disabling graceful shutdown is
recommended" — Cisco). That reminder exists *because operators routinely forget*.
Confidence: documented (RFC + vendor docs); the operational frequency is
war-story / analogous, not a single named public post-mortem.

Two distinct restoration failures:

1. **Drain never removed (stale maintenance state).** The LOCAL_PREF-lowering
   route-map / GSHUT tag is left in place after the window closes. Traffic stays
   on the alternate indefinitely. Reachability is fine, so nothing alarms; the
   only symptom is that an intended path (and any inspection/scrubbing/LI node on
   it) is silently bypassed. This is the classic "we found the drain still applied
   weeks later" war story.

2. **Restore-against-drifted-context (the subtle compound).** The drain *is*
   removed and the drained edge's LOCAL_PREF is restored to its documented
   "normal" value — but **the alternate path's preference drifted UP during the
   window** (an unrelated TE re-tiering, a community re-tag, a peering change).
   Restoring the drained edge to its old absolute value no longer makes it win,
   because the *relative* ordering moved. The config looks correctly restored;
   the behavior is not. The harm is in the **composition of two correct-looking
   changes (drain-lower, then restore) against a baseline that moved between
   them** — there is no single offending diff line.

## Blast-radius mapping

Both failures are **pure-quiet (D4 + intent-invariant only)** when the alternate
is a genuine delivery path: no session, prefix, reachability, redundancy, or
forwarding loss — traffic still arrives, it just no longer transits the mandated
waypoint (firewall / DDoS scrubber / DPI / lawful-intercept tap / mandated
transit). This is the same damage signature as a more-specific route leak that
still delivers (Cloudflare/Verizon Jun 2019,
`noc/cloudflare_bgp_leak_jun2019.md`), but the **cause is procedural/stateful**,
not a more-specific.

## Modeling note (for NetBrace oracle authors)

A two-snapshot (pre + single patch) oracle CANNOT express failure mode 2: a
literal "restore the drained edge's LOCAL_PREF to its normal value" line is a
**no-op against the intended baseline** (the value is already normal there), so
the only graded delta is the alternate-side drift — which collapses to a plain
"raise the alternate's LOCAL_PREF" edit (already-caught explicit-bypass class).
Capturing the *procedural* novelty requires a **three-snapshot model**
(baseline -> drained -> restored) so the model under test is shown the composed
drain->un-drain as the visible change. Without that, the scenario is not distinct
from the explicit LOCAL_PREF bump.

## References
- RFC 8326, Graceful BGP Session Shutdown: https://www.rfc-editor.org/rfc/rfc8326.html
- Arista EOS Maintenance Mode: https://www.arista.com/en/um-eos/eos-maintenance-mode
- Cisco BGP Graceful Shutdown: https://www.cisco.com/c/en/us/td/docs/ios-xml/ios/iproute_bgp/configuration/xe-3s/irg-xe-3s-book/irg-grace-shut.pdf
- Cross-ref: `noc/cloudflare_bgp_leak_jun2019.md` (same quiet D4 signature, different cause)
- Cross-ref: `noc/maintenances_that_caused_outages.md` (change-as-cause pattern library)
