# Community-Driven LOCAL_PREF and the Silent Reroute When a Tag Stops Being Set

## The documented mechanism: community -> LOCAL_PREF mapping is the dominant ISP TE product

Letting a downstream router translate a BGP **community tag into a LOCAL_PREF
value** is not an academic construct — it is *the* standard way the commercial
Internet does customer-driven traffic engineering. The customer (or an internal
edge) tags a prefix with a community; a **separate, pre-existing route-map on the
receiving router** matches that community and sets LOCAL_PREF. The LP change is
never written by the party that edits the tag — it lives in someone else's policy.

Documented, verifiable provider examples (the right-hand field encodes the LP tier
the provider's ingress route-map will set):

- **Lumen / Level 3 (AS3356)** publishes `3356:70` and `3356:80` as customer
  traffic-engineering communities that **set LOCAL_PREF below peer routes**
  ("Set BGP Local Pref to 70 (less than peer routes)"), with `3356:90` in the same
  family. Confirmed on bgp.tools' AS3356 community registry.
  Source: https://bgp.tools/communities/3356
- The "community = AS:local-pref-tier" pattern is taught as the canonical TE design
  (e.g. providers map `3356:70/80/90` to descending LOCAL_PREF tiers; NTT, Cogent,
  Telia/Arelion, Hurricane Electric all run equivalent schemes).
  Source: https://networklessons.com/bgp/bgp-communities-explained
- AWS Direct Connect exposes the same model to customers (`7224:7100/7200/7300`
  set LOCAL_PREF low/medium/high inside AWS).
  Source: https://docs.aws.amazon.com/directconnect/latest/UserGuide/routing-and-bgp.html

The load-bearing property for NetBrace: **the community is the visible knob; the
LOCAL_PREF decision is an emergent reaction of an unchanged policy on a *different*
device.** A change ticket that edits a community tag contains **no LOCAL_PREF
token at all**, yet flips best-path selection at the receiver.

## The failure mode: a tag that stops being set (silent reroute, full reachability)

Two well-known, recurring operational events make the tag stop matching downstream
— both leave reachability fully intact and only change *which* egress carries the
flow:

1. **send-community missing / communities stripped on re-advertisement.** BGP
   communities are NOT propagated by default on every implementation, and are
   stripped on announcement unless `send-community` (or `set community additive`)
   is configured. A "community-scheme cleanup / standardization" change that drops
   or rewrites the tag — or a re-advertising router that fails to carry it — means
   the downstream `match community -> set local-preference` clause **no longer
   fires**, the path falls through to the default LP tier, and best-path flips to
   the alternate. Documented as a standard footgun: "Without send-community,
   communities are stripped before the update is sent ... breaking the ability to
   influence traffic engineering decisions."
   Sources:
   https://oneuptime.com/blog/post/2026-01-30-bgp-community-configuration/view ;
   https://iparchitechs.com/bgp-communities-part-3-customer-bgp-traffic-engineering-communities/
2. **Tag rewritten to a value the downstream map no longer matches** (renumbering
   to a new community scheme, or normalizing `65000:200` -> `65000:201`). Same
   result: the LP-setting clause stops matching, LP falls to default, path flips.

Confidence labelling (do not overstate in the paper):
- That community->LOCAL_PREF mapping is the real TE mechanism, and that a stripped/
  unset community silently changes path selection: **documented** (provider
  registries + vendor docs above).
- That this *specific* "operator removed our own egress tag and traffic silently
  left the inspection/scrubber/LI path" sequence has a single named public
  post-mortem: **not found** — treat the end-to-end incident as **war_story /
  analogous**, anchored to the documented mechanism, exactly as
  `drain_undrain_localpref_restore.md` is. Do not fabricate a citation.

## Why this is PURE-QUIET (D4 + D10 only)

When the alternate egress is a genuine delivery path:
- **D1 = ∅** — a community/LOCAL_PREF change is an UPDATE refresh; the eBGP FSM is
  never reset (RFC 4271 attribute change, not a session event).
- **D2 = ∅ / D9 = ∅** — the /24 is never withdrawn; it stays BEST in the receiver's
  RIB throughout, only its next-hop/LP change. Purer than a more-specific leak,
  which perturbs the covering route.
- **D3 = ∅ / D7 = ∅** — the alternate delivers; full end-to-end reachability holds.
- **D5 = ∅** — REQUIRES a strict LOCAL_PREF gap post (untagged path strictly below
  the alternate). An equal-LP outcome would install ECMP (D5 fires) or decide on a
  fragile router-id tie-break.
- **D4 + D10** — the only real damage: traffic silently stops transiting the
  mandated waypoint (scrubber / firewall / DPI / lawful-intercept tap / mandated
  transit AS), breaking the path-policy invariant.

This is the same quiet D4 signature as a more-specific leak that still delivers
(`cloudflare_bgp_leak_jun2019.md`) and the drain-restore trap
(`drain_undrain_localpref_restore.md`), but the **cause is distinct**: a
community<->policy coupling split across two devices. No specificity, no LPM, no
origination, and no LOCAL_PREF token in the diff.

## Modeling note (NetBrace oracle authors)

- Batfish models `match community -> set local-preference` and community
  propagation across eBGP deterministically (`testRoutePolicies` / steady-state
  best-path). Verified live by the oracle-engineer on the all-eBGP `generator_lp`
  scaffold: pre LP=200 via waypoint, post LP=100 (untagged) strictly below the
  alternate's 150 -> best-path flips, 10x byte-identical.
- **Ship the STRICT-LP construction only.** Do NOT use the "untagged LP == alt,
  MED breaks the tie" variant: way and alt are distinct upstream ASes, so default
  MED comparison never fires (RFC 4271 9.1.2.2), and an equal-LP result is decided
  by router-id (fragile) or installs ECMP under `maximum-paths>1` (fires D5).
- **Generator hygiene gate (verified, non-optional):** if the origin also tags the
  /24, or an `additive` set re-adds the community elsewhere, removing the
  re-advertiser's tag is a true no-op and D4 stays empty. The generator MUST run a
  Batfish pre-check that the advertised route's community set is genuinely empty
  post AND that LP fell strictly below the alternate, per seed, or quarantine the
  instance. Per-seed randomize the community VALUE itself (no fixed `65000:200`
  literal to memorize).

## References
- Lumen/Level3 AS3356 community registry (3356:70/80 set LP below peer):
  https://bgp.tools/communities/3356
- BGP communities -> LOCAL_PREF TE design (provider tiering):
  https://networklessons.com/bgp/bgp-communities-explained
- AWS Direct Connect LOCAL_PREF communities (7224:7100/7200/7300):
  https://docs.aws.amazon.com/directconnect/latest/UserGuide/routing-and-bgp.html
- send-community / stripping footgun:
  https://oneuptime.com/blog/post/2026-01-30-bgp-community-configuration/view
- Customer TE communities + propagation caveats:
  https://iparchitechs.com/bgp-communities-part-3-customer-bgp-traffic-engineering-communities/
- RFC 4271 (decision process 9.1.2, MED 9.1.2.2): https://www.rfc-editor.org/rfc/rfc4271.html
- Cross-ref same quiet-D4 signature, different cause:
  `noc/cloudflare_bgp_leak_jun2019.md`, `noc/drain_undrain_localpref_restore.md`,
  `noc/rr_bestpath_hiding.md`
