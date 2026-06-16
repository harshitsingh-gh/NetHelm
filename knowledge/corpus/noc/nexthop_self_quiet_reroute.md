# Next-Hop-Self Removal → Quiet Egress Reroute (Win-by-Elimination)

## Why a dedicated file
This is a high-value, low-prediction blast-radius class for iBGP networks where a
border re-advertises eBGP-learned prefixes into the core. Removing the next-hop
rewrite (`next-hop-self`, or an explicit outbound `set ip next-hop <loopback>`
route-map) on ONE of two equal-attribute borders does NOT lose the prefix when a
second border still advertises it with a resolvable next-hop. Instead the affected
path becomes **invalid by next-hop unresolvability**, and the survivor border wins
the best-path by **elimination**. Reachability is preserved; the egress silently
moves off the mandated inspection node (scrubber / firewall / DPI / LI tap).

This is the QUIET cousin of the classic "next-hop-self killer" (the LOUD version,
where the prefix goes inactive and traffic drops). The difference is solely whether
a resolvable survivor path exists.

## The mechanism (RFC-grounded)
- iBGP preserves the BGP NEXT_HOP attribute. An eBGP-learned route injected into
  iBGP carries the **external** next-hop (the eBGP link /30) unless the border
  rewrites it to its own loopback (`next-hop-self` / outbound `set ip next-hop`).
- **RFC 4271 §9.1.2.1**: "the local BGP speaker [must] determine whether the route
  is reachable" — a path whose NEXT_HOP is NOT resolvable in the IGP/RIB is **not a
  candidate** for the decision process. It is marked invalid/inactive.
  (https://www.rfc-editor.org/rfc/rfc4271.html#section-9.1.2.1)
- When the rewrite is removed, the core nodes try to resolve the raw external /30.
  Provider cores normally do NOT carry external link subnets in the IGP (by design,
  to keep the core clean). So that path becomes unresolvable → invalid → dropped
  from best-path. If another border still advertises the SAME prefix with a
  loopback (resolvable) next-hop, that path is now the sole best path.

## Documented grounding (the failure MODE, not the quiet outcome)
- **Cisco — "Troubleshoot Flapping BGP Routes (Recursive Routing Failure)"**, doc
  19167. The named failure mode: a recursively resolved BGP next-hop becomes
  unresolvable and the path is withdrawn from forwarding.
  https://www.cisco.com/c/en/us/support/docs/ip/border-gateway-protocol-bgp/19167-bgp-rec-routing.html
- **Cisco — "Next-Hop Mismatch and BGP Inactive Routes"**, doc 116146: a path with
  an inaccessible next-hop is marked inactive and excluded from best-path; the fix
  is advertise-via-IGP, a static, or `next-hop-self`.
  https://www.cisco.com/c/en/us/support/docs/ip/border-gateway-protocol-bgp/116146-config-bgp-next-hop-00.html
- **FRR issue #15535 / #10303**: FRR marks a path "(inaccessible) … invalid,
  external" and excludes it from best-path when the next-hop is not resolvable —
  the exact behavior the oracle relies on in the FRR/Batfish dialect.
  https://github.com/FRRouting/frr/issues/15535
- The **quiet** outcome (survivor delivers, reachability preserved, inspection node
  bypassed) is a WAR STORY / ANALOGOUS class, not a named public postmortem — when
  nothing visibly breaks, nobody writes it up. Same reason the leak's quiet variant
  lacks a dedicated postmortem. Do NOT cite a fabricated incident for it.

## Blast radius (get this right in the oracle)
- **D1 = 0** — next-hop-self / the outbound rewrite is a per-prefix advertisement
  attribute, not a session attribute. Removal does NOT reset eBGP or iBGP.
  (Common LLM error: claiming the session drops.)
- **D2 = 0** — the /24 is still present in every RIB via the survivor border.
- **D3 = 0, D7 = 0** — the survivor delivers; no blackhole, no loop.
- **D5 = 0** — IF AND ONLY IF the PRE baseline had a STRICT single best path
  (not ECMP). See the trap below.
- **D4 + D10 = VIOLATED** — egress moved off the mandated waypoint; intent broken.

## The determinism / purity trap (load-bearing)
If the two borders advertise the prefix with **identical** BGP attributes (equal
LOCAL_PREF / AS-path / MED / origin), FRR/Batfish installs them as **ECMP** —
router-id is only the final tie-break and does NOT suppress multipath. Consequences:
1. The waypoint is ALREADY violated PRE (half the traces take the non-waypoint
   border), so D4 cannot "newly fire."
2. The 2→1 next-hop collapse FIRES D5 — the LOUD half.

To get pure-quiet D4+D10, the PRE baseline MUST have a genuine strict best-path
discriminator on the SURVIVOR/loser path (e.g. the survivor border tags its own
iBGP advertisement with a WORSE MED, or a longer prepend, or lower LOCAL_PREF).
That makes the waypoint border strictly preferred PRE (1 path), and POST the
survivor wins by elimination (1 path) — D5 stays empty. The discriminator is a
BASELINE steering attribute, NOT part of the change; the change is purely the
removal of the next-hop rewrite.

## Calibration control (the no-op)
If the external /30 IS carried in the core IGP/static, removing the rewrite is
INERT — the raw external next-hop still resolves, the path stays valid, nothing
moves. Ground truth = EMPTY. This is the mandatory negative/control instance.

## Distinctness from other quiet mechanisms
- **vs more-specific leak (leak_ms / Cloudflare 2019)**: the leak ADDS a more
  specific to win at longest-prefix-match. This INVALIDATES one of two
  equal-specificity paths via next-hop resolvability; the win is by elimination.
  Decisive variable = iBGP next-hop validity, absent from the leak.
- **vs RR best-path hiding (RFC 4456)**: no reflection; both borders reach the
  source directly. The hidden variable is next-hop resolvability, not RR position.
