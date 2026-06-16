# RPKI ROV-invalid silent reroute that bypasses a security waypoint

> Status tags: **[FACT]** = cited to a measurement paper / RFC · **[INFER]** = sound
> design implication · **[SPEC]** = unverified, flagged. Curated by noc-veteran,
> 2026-06-15.

## The one-line mechanism (D4 + D10 quiet-reroute class)

An operator turns on (or tightens) **Route Origin Validation (ROV)** on a border
router — `route-map RPKI ... match rpki invalid -> deny` (or sets a low LOCAL_PREF /
WEIGHT on `invalid`, per RFC 8893 / the NLNOG "reject invalids" guide). The intent is
pure hygiene: "drop routes that fail RPKI." But for a prefix that is **RPKI-invalid on
the *preferred* path and valid (or covered) on a *less-preferred* path**, dropping the
invalid candidate **silently moves the best path onto the surviving path** — which may
no longer transit the scrubbing / inspection / DDoS-mitigation upstream the traffic was
supposed to go through.

- **Sessions:** none drop (D1 = ∅). ROV is a route-map filter, not a session event.
- **Prefixes:** reachability to the destination is **preserved** via the alternative
  path (D2 = D3 = ∅) — this is the whole point, and it is what makes the change "look
  safe."
- **Waypoint / intent:** the mandated transit node is silently bypassed
  (**D4 + D10 fire, everything else empty**) — the signature this benchmark is built on.

This is the **inverse-polarity sibling** of `community_lp` / `med_far_as`: there the
operator *adds* an attribute to move the path; here the operator *deletes a candidate*
(filters the invalid) and the path moves as a second-order consequence. It belongs to
**Family-3 (route-visibility / projection)** — the invalid path **disappears from the
candidate set**, exactly like `agg_collapse` (the /25 disappears) and `rr_bestpath`
(the RR projects one path) — not to the comparator-wedge family.

## Why this is REAL and NECESSARY (not an academic toy)

[FACT] Measurement window **Jan 2023 – Jul 2024**. Verbatim: *"we observe a total of
42,654 unique RPKI-invalid prefixes during the 18-month period"*, and *"there are still
6,802 RPKI-invalid prefixes as of today"* (with 51.3% of Internet routes ROA-covered).
The cascading-impact finding, verbatim: *"hidden misconfigurations reroute traffic onto
unsecured paths — 18.5% of RPKI-invalid routes diverge because ROV-enabled networks drop
them, and 39.2% of the affected prefixes suffer performance degradation."* The security
consequence, verbatim: *"Traffic rerouted through unsecured paths bypasses critical
safeguards like DDoS scrubbing services, exposing networks to volumetric attacks or
man-in-the-middle surveillance"*; and the upstream-bypass mechanism: *"since the upstream
AS is usually the one providing transit services as well as security services like DDoS
protection, if the traffic is diverted to a different upstream AS, it may bypass these
security services."* Source: Tao Wan, Weitong Li, Taejoong Chung, *"Demystifying
RPKI-Invalid Prefixes: Hidden Causes and Security Risks,"* **NDSS 2026** (Virginia Tech /
CableLabs); PDF verified verbatim 2026-06-15. That "reroute-onto-an-unsecured-path-that-
bypasses-the-scrubber" mechanic is exactly this benchmark's D4+D10 thesis, stated by an
independent measurement team.

[NOTE] Earlier drafts of this card paraphrased the above inside quotation marks
("frequently bypassed ... traffic inspection"; "ROV filtering can silently reroute
traffic away from its intended path") — neither was verbatim. Corrected 2026-06-15
against the NDSS camera-ready PDF; only the sentences quoted above appear in the paper.

[FACT] **TORCH (Tian, Li, Yin, Zhang, Shi, Wang, Tsinghua), arXiv:2603.29207, 2026**
corroborates the "reachability persists while the filtering intent is bypassed"
mechanic: invalid prefixes stay reachable at high rates (e.g. Cloudflare's
2606:4700:7000::/48 invalid reachability **consistently exceeds 84%**; a MOAS case
where **89.1% of traffic is steered through the invalid route despite valid
alternatives**), and "local ROV efforts alone are insufficient to prevent collateral
damage" — i.e. the local filter changes *where* the traffic goes, not *whether* it
arrives. That is D4-fires / D3-empty by construction.

[FACT] RFC 6811 (Origin Validation in the BGP Decision Process) places the
valid/invalid/notfound state **into best-path** (typically by influencing LOCAL_PREF or
by outright `deny invalid`). So an ROV policy edit is a *legitimate best-path-moving
edit dressed as a security-hygiene change* — the canonical "looks safe, isn't" shape.

## Operational realism of the trap

The dangerous instance is not "ROV broke reachability" (that is loud — D2/D3 fire, every
operator catches it and it is already covered by the leak/blackhole loud-half). The
dangerous instance is **the prefix that has BOTH an invalid preferred path AND a valid
backup**: turning on ROV is a no-op for reachability and a silent waypoint bypass for
security. A model that reasons "ROV only drops bad routes, reachability is fine, ship
it" scores a perfect pass on a session/prefix grader while missing that the
scrubbing/inspection upstream is now bypassed — the exact pathology NetBrace exists to
catch.

## Gradeability note (oracle engineer must read before building)

[FACT/INFER] **Batfish does NOT natively model RPKI/ROV state** (no ROA/VRP input, no
`rpki` match attribute in its question set — confirmed 2026-06-15, no ROV question or
RPKI attribute in the Batfish model). A generator that writes a literal `match rpki
invalid` line is a **FALSE-QUIET landmine**: the line is unrecognized, the candidate is
NOT actually dropped, and the oracle returns an empty blast radius (committed GT becomes
wrong = blocking). **Do NOT build it that way.**

[INFER] **The gradeable build** renders the ROV outcome as the equivalent, modeled
config Batfish DOES honor: a prefix-list / AS-path-list / community match that drops (or
LOCAL_PREF-deprefs) the invalid-origin path on the deciding border, exactly as an ROV
route-map would after validation. The diff the model reads is the security-policy edit;
the oracle grades the resulting D4+D10 reroute via the same dataplane-traceroute waypoint
check the other Family-3 generators use. The docstring MUST disclose that the literal
`match rpki invalid` is rewritten to a modeled deny/depref (a transparently-documented
gradeability substitution, identical in spirit to the `nexthop_elim` route-map
workaround). Re-verify on any digest bump.

## Blast-radius mapping
- D1 sessions: ∅ · D2 prefixes: ∅ · D3 reachability: ∅
- **D4 waypoint:** FIRES (scrubbing/inspection upstream bypassed)
- D5 redundancy: ∅ · D7 forwarding: ∅ · D9 BGP-RIB: the invalid path *does* leave the
  BGP-best set, so D9 is a deliberate watch-set exclusion (mirror `agg_collapse`: do
  NOT add the invalid prefix to `bgp_watch_prefixes` or the family goes loud on D9)
- **D10 intent:** FIRES (security-transit invariant violated)

## Distinctness from existing families
- vs `agg_collapse` (Family-3): there an *aggregate summary* removes a more-specific
  from LPM; here an *ROV/security filter* removes an invalid *candidate path* from the
  BGP candidate set. Different lever (LPM-visibility vs candidate-set-membership),
  different real failure mode (table hygiene vs origin-validation hygiene).
- vs `community_lp` / `med_far_as` (Family-2): those *add* an attribute at the decision
  point; ROV-reroute is a *subtraction* of a candidate — it sits on the
  subtraction/counterintuitive-polarity axis (with `clause_fallthrough` and
  `remove_dead_prepend`) but with a *security-hygiene* surface action, which is a
  genuinely new "looks-safe" motivation no existing family carries.

## Sources
- Wan, Li, Chung, "Demystifying RPKI-Invalid Prefixes: Hidden Causes and Security
  Risks," NDSS 2026.
  https://weitongli.com/publications/papers/li-2026-demystifying.pdf and
  https://www.cablelabs.com/blog/exploring-the-hidden-causes-and-security-risks-of-rpki-invalid-prefixes
- Tian et al., "TORCH: Characterizing Invalid Route Filtering via Tunnelled
  Observation," arXiv:2603.29207, 2026. https://arxiv.org/html/2603.29207v1
- RFC 6811 (Origin Validation in the BGP Decision Process); RFC 8893; NLNOG "Rejecting
  RPKI Invalid BGP Routes," https://bgpfilterguide.nlnog.net/guides/reject_invalids/
