# ORIGIN-Code Quiet Reroute — when an innocuous origination-method change silently moves your traffic

## Mechanism (blast-radius relevant)

ORIGIN (RFC 4271 §4.3 / §5.1.1) is a well-known mandatory BGP path attribute with
three values, ranked **IGP < EGP < INCOMPLETE** (lowest wins). It is consulted in the
best-path decision at **RFC 4271 §9.1.2.2 (b)** ("Breaking Ties (Phase 2)"): step (a)
removes routes that are not tied for the shortest AS_PATH, step **(b) removes routes that
do not have the lowest Origin number**, and only then step (c) compares MED. So ORIGIN is
a *genuine* tie-break — it decides the best path whenever weight, LOCAL_PREF, and AS_PATH
length are all equalized across two copies of a prefix.

The treachery is that **the ORIGIN code is set implicitly by the origination method**,
not by an explicit operator decision:

- A prefix originated by a **`network <prefix>`** statement carries **ORIGIN = IGP**.
- A prefix injected by **`redistribute static` / `redistribute connected` /
  `redistribute <igp>`** carries **ORIGIN = INCOMPLETE** — "we have no idea how the
  prefix appeared in the BGP table" (ipSpace, "The BGP ORIGIN Attribute"). Unless an
  operator adds a route-map `set origin igp` to the redistribute, redistributed routes
  are stamped incomplete.

This makes ORIGIN a **silent** lever. Re-originating a customer prefix from `network` to
`redistribute static` (or vice-versa) — an edit that looks like routine "tune how this
prefix is originated into BGP" housekeeping — changes the prefix's ORIGIN code, which can
flip the best path at a downstream router where two equal-attribute copies meet.

Key mechanics that make it a *quiet* (D4 waypoint + D10 intent only) blast-radius event:

1. **ORIGIN decides only after AS_PATH (§9.1.2.2 (a)) ties.** For the lever to bite, the
   two copies of the prefix must reach the decision point equalized on LOCAL_PREF
   (§9.1.2.1 degree of preference) and AS_PATH length (§9.1.2.2 (a)). This is exactly the
   dual-origin case: two egresses in the same AS each *originate* the customer prefix, so
   both copies arrive with AS_PATH = `[that AS]`, length 1. (ipSpace cautions that because
   ORIGIN sits below AS_PATH it is "rarely decisive" — which is precisely why an
   ORIGIN-driven reroute is a *surprising* one when the conditions DO line up.)
2. **An origination-method change is an attribute UPDATE, not a session event.** The BGP
   FSM (RFC 4271 §8) leaves Established only on NOTIFICATION, hold-timer expiry, or TCP
   teardown — never on a `network`/`redistribute` edit. So the change produces **zero D1**
   (no session loss). Common LLM error: predicting a session drop here.
3. **The prefix stays BEST in every RIB** — both copies remain valid, only *which* copy
   wins at the decision point changes → **D2 = ∅**; the other egress delivers the prefix
   exactly as the first did → **D3 = ∅, D7 = ∅**. A strict downstream discriminator
   (here a MED gap, see below) yields a single best path → **D5 = ∅** (no ECMP to lose).
   The ONLY casualty is *which egress / inspection node the traffic transits* → **D4
   (waypoint) + D10 (intent invariant)**.

## The two-attribute subtlety (be precise: ORIGIN vs the latent MED)

Collapsing the ORIGIN tie does not by itself name a winner — it *ungates the next step*.
Once step (b) ORIGIN ties, the decision falls through to **§9.1.2.2 (c) MED**. So an
honest account of a dual-origin ORIGIN flip is **two attributes deep**:

- **PRE:** the two copies differ at step (b) ORIGIN (one IGP, one incomplete). IGP wins;
  the waypoint egress is selected. A latent MED difference at step (c) is never consulted.
- **POST (the flip):** both copies become incomplete (or both IGP). Step (b) now TIES, and
  the **MED step (c) is the real discriminator** — the lower-MED egress wins. The waypoint
  moves *because of the MED*, after the ORIGIN flip removed the gate that hid it.

Do not say "ORIGIN is decisive POST." PRE the ORIGIN step decides; POST the ORIGIN step
ties and the MED step decides. The lever is an **ORIGIN flip that ungates a latent MED**.

## Why this is a distinct CAUSE from the MED-driven reroute

The MED reroute (`med_driven_quiet_reroute.md`) moves traffic by *editing the MED itself*
while ORIGIN/AS_PATH are already equal. The ORIGIN reroute leaves the MED untouched — it
moves traffic by *collapsing an ORIGIN inequality that was masking* a pre-existing,
unchanged MED gap. Same quiet D4 damage signature; structurally different cause and
different diff (a `network`↔`redistribute` origination-method swap, not a `set metric`
edit). The two are sibling quiet-reroute mechanisms that a config reader must tell apart.

## Real-world grounding

**This is a MECHANISM-GROUNDED card, not an incident-grounded one.** I did not find a
single named public outage attributed specifically to a `network`-vs-`redistribute`
ORIGIN flip (ORIGIN-driven reroutes are quiet by nature and rarely make public postmortems
— which is itself the point of this benchmark). It is grounded honestly in the RFC tie-break
and in vendor / operator documentation of the exact behavior:

- **RFC 4271 §9.1.2.2 (b)** makes ORIGIN a real tie-break (lowest Origin wins), sitting
  directly below AS_PATH (a) and above MED (c): https://www.rfc-editor.org/rfc/rfc4271
- **FRR documents the ORIGIN best-path step explicitly**: "Origin check — Prefer the
  lowest origin type route. That is, prefer IGP origin routes to EGP, to Incomplete
  routes." https://docs.frrouting.org/en/latest/bgp.html
- **`network` ⇒ IGP, `redistribute` ⇒ INCOMPLETE is documented vendor-neutral behavior**:
  ipSpace, "The BGP ORIGIN Attribute" — routers set ORIGIN=IGP for `network`-originated
  prefixes and INCOMPLETE for redistributed prefixes "unless administrators apply a
  route-map to explicitly set origin to igp"; and the operator caution that ORIGIN
  "should generally be left alone" precisely because it is a low, easily-overlooked
  tie-break: https://blog.ipspace.net/2023/12/bgp-origin-attribute/
  NetworkLessons, "BGP Origin Code Attribute explained" (network=i / redistribute=?):
  https://networklessons.com/bgp/bgp-origin-code-attribute-explained
- **The remediation knob (`set origin`) is real**: redistributed routes can be re-stamped
  IGP with a route-map `set origin igp`, which is exactly how an operator would make a
  redistributed prefix win like a `network`-originated one — and exactly the
  best-path-NEUTRAL construct the calibration twin uses.

## Determinism / oracle notes (load-bearing)

- **`set origin igp|incomplete` IS modeled by the pinned Batfish FRR digest**
  (`batfish/allinone:nethelm` @ `sha256:09817554db90`, live-verified 2026-06-15): a
  customer-prefix origination swapped `network`→`redistribute static` with the
  redistribution route-map carrying `set origin igp` produces a byte-identical EMPTY
  oracle (the ORIGIN is pinned to its PRE value → best path unchanged), whereas the same
  swap WITHOUT the pin flips the waypoint. This is what lets the calibration (no_op) twin
  re-originate the *same customer prefix* (defeating a syntactic "does the patch touch the
  customer prefix?" heuristic) while remaining provably best-path-neutral.
- **MED comparability caveat (do NOT overstate the RFC gate).** RFC 4271 §9.1.2.2 (c)
  compares MED only between same-neighbor-AS routes, and the dual-origin topology DOES
  satisfy that gate (both copies arrive from the same egress AS) — so the mechanism is
  RFC-faithful. BUT the Batfish oracle does not depend on the gate: its comparator
  compares MED **unconditionally** (`BgpRib.java:209`, a bare `Long.compare`, no
  same-leftmost-AS check — see `../batfish/batfish_verified_facts.md` ~line 140).
  `bgp deterministic-med` / `bgp always-compare-med` PARSE-and-DROP in the FRR dialect and
  are deliberately not emitted. Do not claim Batfish honors a same-AS MED gate; it does
  not.

## Blast-radius mapping

- **D1 = ∅** — origination-method update, no session reset.
- **D2 = ∅** — prefix stays best in every RIB (only which copy wins moves).
- **D3 = ∅, D7 = ∅** — the other egress delivers the prefix; reachability preserved.
- **D5 = ∅** — strict downstream (MED) gap → single best path, no ECMP set to lose.
- **D4 = fires** — traffic stops transiting the mandated inspection/egress node.
- **D10 = fires** — "traffic to X MUST transit Y" invariant broken.

This is the pure-quiet signature: nothing lost, nothing withdrawn, full reachability
preserved — only the mandated waypoint silently bypassed, decided by a BGP attribute two
tie-break steps deep that an innocuous origination-method edit quietly perturbed.

## References
- RFC 4271 §4.3/§5.1.1 (ORIGIN), §8 (FSM), §9.1.2.1–§9.1.2.2 (decision process /
  Breaking Ties Phase 2 — (a) AS_PATH, (b) ORIGIN, (c) MED):
  https://www.rfc-editor.org/rfc/rfc4271
- FRR BGP route selection (ORIGIN check): https://docs.frrouting.org/en/latest/bgp.html
- ipSpace, "The BGP ORIGIN Attribute": https://blog.ipspace.net/2023/12/bgp-origin-attribute/
- NetworkLessons, "BGP Origin Code Attribute explained":
  https://networklessons.com/bgp/bgp-origin-code-attribute-explained
- Sibling quiet-reroute card: `med_driven_quiet_reroute.md`
- Oracle MED-comparator fact: `../batfish/batfish_verified_facts.md` (~line 140)
