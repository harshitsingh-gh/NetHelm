# Route-Map First-Match Shadowing: a "cleanup" deletion that quietly reroutes off the waypoint

## The documented mechanism: first-match / implicit-deny semantics in FRR

A route-map is an **ordered list of clauses evaluated in strict sequence-number
order, first-match wins**, and **the default action when no clause matches is
DENY** — i.e. a route-map behaves as if it ends in an empty deny that matches all
routes. This is the current, verified FRR semantics:

- FRR routemap.rst: "Route maps are an ordered list of route map entries." …
  "The default action of a route-map, if no entries match, is to deny. I.e. a
  route-map essentially has as its last entry an empty _deny_ entry, which matches
  all routes. To change this behaviour, one must specify an empty _permit_ entry
  as the last entry in the route-map."
  Source: https://docs.frrouting.org/en/latest/routemap.html

Because matching is first-match top-down, **which clause a given prefix lands on is
a function of clause ORDER, not just the match conditions.** Delete or re-sequence
a clause and a prefix that used to match clause 10 can fall through to a later
clause (or to the terminal catch-all) and pick up a *different* set-action —
including a different LOCAL_PREF — with **no value edited anywhere on any path.**

## Why this is its own cause class (not "community LP" and not "more-specific leak")

This is the **config-text precedence** failure: the steered prefix loses its
preferred LOCAL_PREF not because any LP value changed and not because a new
more-specific route appeared, but because it **stopped reaching the clause that set
its high LP**. Mapping to the curated quiet-half family:

- vs `cloudflare_bgp_leak_jun2019.md` (more-specific leak): that changes the
  **route set** (a new /25); here the route set, specificity, and origin are
  unchanged — only clause traversal order changes.
- vs `community_driven_localpref_silent_reroute.md`: there a community **value**
  changes and a separate policy reacts; here the communities are **fixed** and the
  **clause structure** the prefix traverses changes (delete / re-sequence).
- vs `med_driven_quiet_reroute.md` / `drain_undrain_localpref_restore.md`: those
  are attribute-value diffs a model can compare; here the decisive attribute
  (the alternate's LP) is **byte-identical pre and post** — the winner emerges
  purely from fall-through.

Root-cause taxonomy: this is the SIGCOMM'02 "poor understanding of configuration
semantics" / route-map-filter class (below), instantiated as a quiet D4+D10.

## Real-world grounding (verified; confidence labelled — do not overstate)

1. **SIGCOMM'02, "Understanding BGP Misconfiguration" (Mahajan, Wetherall,
   Anderson).** First quantitative study of BGP misconfiguration. Two findings
   directly underwrite the quiet-half thesis, quoted from the paper:
   - "we find connectivity to be surprisingly robust; **only 4% of the bad
     announcements disrupt connectivity.**" => ~96% of real misconfigurations are
     QUIET (reachability preserved) — the paper's empirical justification that the
     quiet half is the *common* case, not an edge case.
   - causes include "involuntary slips," "router initialization bugs," and "**a
     poor understanding of configuration semantics on the part of operators**";
     and "Route maps are the most popular form of filtering." A clause-order /
     first-match mistake is precisely a "configuration-semantics" slip on the most
     common filtering construct.
   - Confidence: **documented** (peer-reviewed, verified by direct quote).
   - Sources: https://dl.acm.org/doi/10.1145/633025.633027 ;
     https://conferences.sigcomm.org/sigcomm/2002/papers/bgpmisconfig.pdf

2. **The mandated waypoint this breaks is real, standard operations: DDoS
   scrubbing-center diversion via BGP routing policy.** Operators steer a
   customer /24 INTO a scrubbing center (the mandated inspection waypoint) using
   LOCAL_PREF / community / route-map policy and a GRE/IPsec return path; when the
   steering policy stops applying, traffic silently bypasses the scrubber while
   still reaching the customer.
   - Confidence: **documented** that scrubbing diversion is implemented this way
     (Radware, ThousandEyes, Noction, FastNetMon); **analogous** for the specific
     "a route-map clause edit silently un-diverted us" sequence.
   - Sources: https://support.radware.com/app/answers/answer_view/a_id/1018551/ ;
     https://www.thousandeyes.com/blog/using-bgp-reroute-traffic-ddos ;
     https://www.noction.com/blog/ddos-scrubbing

3. **A single named public post-mortem** of "deleted/re-sequenced a route-map
   clause and traffic silently left the scrubber/firewall/DPI/LI path": **NOT
   found.** Treat the end-to-end incident as **war_story / analogous**, anchored to
   the documented SIGCOMM'02 class + the documented scrubbing-diversion design,
   exactly as `community_driven_localpref_silent_reroute.md` and
   `drain_undrain_localpref_restore.md` are anchored. **Do not fabricate a
   citation** — this is the Rogers-reconstruction error we already had to fix.

## Why this is PURE-QUIET (D4 + D10 only) — verified live by the oracle-engineer

- **D1 = empty** — a route-map edit triggers a soft inbound re-evaluation
  (route-refresh), never an eBGP FSM reset (RFC 4271 attribute/policy change, not a
  session event). Sessions 8 -> 8.
- **D2 = empty / D9 = empty** — the /24 stays BEST in src's RIB throughout (via the
  alternate post-change). The oracle-engineer verified LIVE that deleting the
  steering clause keeps src main-RIB count at 7 and the /24 BEST via alt. NOTE:
  the original proposal claimed the terminal catch-all clause is load-bearing for
  D2 (that without it the way route is "withdrawn" and D2 fires). **That claim is
  FALSE** — the non-best way route was never a separate installed RIB row, so the
  catch-all is NOT required for purity. Authoring prose must not assert it.
- **D3 = empty / D7 = empty** — the alternate delivers; full end-to-end reachability
  holds. PRE trace src->way->dst ACCEPTED; POST trace src->alt->dst ACCEPTED.
- **D5 = empty** — REQUIRES a strict LOCAL_PREF ladder in BOTH snapshots
  (300>200 pre, 200>100 post) => exactly one best path each snapshot, no equal-cost
  ECMP tie, `maximum-paths` default 1. An equal-LP outcome would fire D5 or decide
  on a fragile router-id tie-break (kills determinism).
- **D4 + D10** — the only damage: traffic silently stops transiting the mandated
  waypoint, breaking the path-policy invariant.

## Modeling / authoring notes (NetBrace oracle + generator)

- **Batfish-gradeable in the FRR dialect, no vendor config needed.** Batfish models
  `bgp community-list`, `match community`, multi-clause strict first-match
  ordering, the terminal catch-all set-action, and the LP200>LP100 best-path flip.
  Verified LIVE: POST shows LP=200 via alt, BEST. Corroborated by Batfish's own
  "Validating the validator" blog (FRR route-maps with community-list matching).
- **Ship DELETE and RE-SEQUENCE variants ONLY.** Drop the `on-match next` /
  `continue` sub-variant from v1 — set-action layering across a `continue` was NOT
  verified live and Batfish may model it differently from FRR.
- **Distinctness gate (non-negotiable, else it collapses into `lp_drop_way`):** the
  diff must be a clause DELETE or RE-SEQUENCE with **zero value edits on any path**,
  and src must run **ONE multi-clause route-map** applied to BOTH upstream sessions
  (seeing both community-tagged paths) — NOT two separate per-neighbor maps (which
  would *be* the value-diff lp_drop_way). Only then is the cause evaluation-ORDER
  shadowing rather than a value diff a model can compare.
- **Generator hygiene:** per-seed randomize ASNs, addressing, names, AND the
  community VALUES (e.g. `<src_asn>:NNN` for VIA_WAY/VIA_ALT) so the trap is
  structural, not a memorizable literal. Per-seed Batfish pre-check that POST best
  path is via alt with strict LP gap, or quarantine the instance.
- **Build gate:** re-run the >=10x byte-identical determinism gate
  (`ExtendedOracle.compute_checked runs=10`) on the PINNED `batfish/allinone:nethelm`
  (sha256:09817554db90...), not `:latest`, before shipping
  (per `oracle_determinism_spec_v1.md`). Expected to pass by construction (strict LP
  gaps => single best path), but must be confirmed on the pin.

## References
- SIGCOMM'02 Understanding BGP Misconfiguration (4% connectivity loss; route-maps
  most common filter; config-semantics slips):
  https://conferences.sigcomm.org/sigcomm/2002/papers/bgpmisconfig.pdf
- FRR route-map first-match / implicit-deny semantics:
  https://docs.frrouting.org/en/latest/routemap.html
- RFC 4271 BGP-4 decision process (9.1.1 LOCAL_PREF; policy vs session events):
  https://www.rfc-editor.org/rfc/rfc4271.html
- DDoS scrubbing diversion via BGP policy (the mandated waypoint this breaks):
  https://support.radware.com/app/answers/answer_view/a_id/1018551/ ;
  https://www.thousandeyes.com/blog/using-bgp-reroute-traffic-ddos
- Cross-ref same quiet-D4 signature, DIFFERENT cause:
  `noc/cloudflare_bgp_leak_jun2019.md` (more-specific leak),
  `noc/community_driven_localpref_silent_reroute.md` (community-value coupling),
  `noc/med_driven_quiet_reroute.md`, `noc/drain_undrain_localpref_restore.md`,
  `noc/rr_bestpath_hiding.md`
