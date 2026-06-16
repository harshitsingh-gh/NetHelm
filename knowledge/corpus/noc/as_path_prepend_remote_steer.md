# AS_PATH Prepend as a Remote / Cross-Domain Path Steer (quiet waypoint bypass)

## Why this matters for blast radius

AS_PATH length is RFC 4271 §9.1.2.2 decision step (after WEIGHT and LOCAL_PREF).
When LOCAL_PREF is equal across candidate paths, **the AS that wins is the one with
the shorter AS_PATH** — and that length is set by *foreign* ASes you do not control.
A prepend added (or removed) in another administrative domain therefore changes which
egress *your* router selects, with **no session change, no prefix withdrawal, and no
loss of reachability** — the prefix is still best, still installed, still delivered,
just via a different next-hop. This is the textbook "quiet half" signature: a path
shifts off a mandated waypoint while everything an alarm watches (D1 sessions, D2
prefixes, D3 reachability, D5 redundancy, D7 forwarding) stays clean.

This maps to NetBrace **D4 (waypoint/path-policy violation) + D10 (intent invariant
broken)** with all other dimensions empty.

## Mechanism (the cross-domain locus is the point)

- A self-owned inbound prepend (you prepend on YOUR uplink to deprefer one of YOUR
  paths) is the *normal* inbound-TE technique and is reasoned about locally.
- A **far-AS / outbound** prepend is different: a *downstream* AS (a customer, a
  multihomed origin) prepends on its announcement toward ONE of its upstreams. That
  upstream re-advertises the now-longer AS_PATH; several ASes away, an operator's
  step-2 tie-break flips to the *other* egress. The operator never sees the config
  that caused it — the cause is outside the trust boundary.
- Adversarial variant: a peer who knows your topology can deliberately lengthen your
  inspection/scrubber path from outside, steering your traffic off your mandated
  waypoint without ever touching your network.

## Real-incident grounding

### China Telecom routing leak, April 2010 (analogous; documented)
~50,000 prefixes leaked. The two most-propagated leaked US routes (12.4.196.0/22,
12.5.48.0/21, origin AS12163) propagated *because* their legitimate announcements
carried an excessively prepended AS_PATH ("...12163 12163 12163 12163 12163 12163"):
the shorter leaked path beat the long legitimate one on AS_PATH length, so global
traffic shifted onto the leak. Demonstrates that **third-party AS_PATH length governs
which path remote ASes pick**, and that prepending is a self-inflicted steering lever.
Source: APNIC, "Excessive BGP AS-PATH prepending is a self-inflicted vulnerability"
(2019-07-15) — https://blog.apnic.net/2019/07/15/excessive-bgp-as-path-prepending-is-a-self-inflicted-vulnerability/

### Country Financial / AS10511 prepend typo, Oct 2014 (analogous; documented)
During a provider change, an engineer prepending to *raise the cost* of a path
mistyped the AS number (15011 Jaguar Communications instead of the intended 10511).
The malformed AS_PATH steered traffic onto the wrong upstream; availability dipped for
over an hour. Shows a single AS_PATH edit, no session/prefix loss, produces a path
change with operational impact — and that prepend effects are *global and indirect*
(you must inspect multiple routers to find the cause).
Source: ThousandEyes, "When Routes Go Wrong: Solving BGP AS-Path Prepending Errors"
(Oct 2014) — https://www.thousandeyes.com/blog/solving-bgp-path-prepending-errors

### BGP poisoning at scale (analogous; documented research)
Smith, Birkeland, McDaniel, Schuchard, "Withdrawing the BGP Re-Routing Curtain"
(NDSS 2020) captured 1,400+ real instances of one AS deliberately inserting remote AS
numbers into AS_PATHs to **steer the return paths of upstream networks onto different
paths while keeping destinations reachable** — the exact "path moves, reachability
preserved" property the quiet half depends on.
Source: https://www.ndss-symposium.org/ndss-paper/withdrawing-the-bgp-re-routing-curtain-understanding-the-security-impact-of-bgp-poisoning-through-real-world-measurements/

### IMC 2020 measurement of prepending in the wild (analogous; documented)
Cunha et al., "AS-Path Prepending" (ACM IMC 2020) measured prepending across the
Internet and found it routinely shifts which path remote ASes select — and often
fails to (local peering/LOCAL_PREF overrides length), confirming prepend steering is
real, common, and *not always effective*, which is why operators get it wrong.
Source: https://dl.acm.org/doi/10.1145/3419394.3423642

## Blast-radius bookkeeping (get the oracle right)

- **D1 = 0.** An AS_PATH attribute change does not reset the BGP FSM (RFC 4271 §8).
  Common LLM error: claiming the session drops. It does not.
- **D2 = 0.** Same prefix stays BEST and installed at the observer; only AS_PATH
  length and chosen next-hop change.
- **D3 = 0.** Destination still reachable via the other egress.
- **D5 = 0** *only if* the length gap is strict (no equal-length tie → no ECMP). If
  the prepend creates an equal-length tie, you get multipath/ECMP and a
  nondeterministic best-path — that would be a different (louder, non-deterministic)
  scenario; the quiet version must keep a strict one-hop gap in both directions.
- **D4 = 1, D10 = 1.** The mandated waypoint is bypassed; the "must transit Y"
  invariant is broken silently.

## Detection note

BGP-level counters give NO signal (Telekom Malaysia 2015 lesson: session count and
prefix count are flat; only path/forwarding inspection sees it). RPKI ROAs do NOT help
— the origin is legitimate and the prefix is unchanged; this is a path-length steer,
not an origin hijack. This is precisely why it is a quiet miss.
