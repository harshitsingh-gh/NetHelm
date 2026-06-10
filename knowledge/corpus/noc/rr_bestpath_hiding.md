# Route-Reflector Best-Path Hiding — Partial Path Visibility (RFC 4456)

## Why a dedicated file
This is one of the highest-value, *least-predicted* blast-radius classes for iBGP
networks: a change that flips an RR's best-path selection (or that toggles whether
the RR advertises additional paths) can **strand a backup path that clients never
see**, with **D1=0 and D2 looking fine at the RR**. Sessions stay up, the prefix is
present — but a whole layer of redundancy that operators *think* exists is invisible
to clients. The trap is structural to RFC 4456, so it is not vendor-specific and not
a toy. Dimensions per `../batfish/blast_radius_patterns.md` (D1–D8).

## The mechanism (the rule, verbatim)
RFC 4456 §11: *"One of the key components of the route reflection approach in
addressing the scaling issue is that the RR summarizes routing information and only
reflects its best path."*
[RFC 4456 §11](https://www.rfc-editor.org/rfc/rfc4456.html)

This inherits BGP's base rule (RFC 4271 §9.1): a speaker selects ONE best path and
advertises only that. In a full iBGP mesh every router sees every other router's
best path, so a client can compute its own backup. **Under route reflection the
client sees only the RR's single chosen best path** — the alternates the RR also
holds are *not* propagated. RFC 4456 §11 acknowledges the consequence: *"with certain
route reflection topologies the route reflection approach may not yield the same
route selection result as that of the full IBGP mesh approach."*

Two distinct ways the RR hides a path the client needs:
1. **Best-path computed from the RR's IGP location, not the client's.** The RR breaks
   the best-path tie on IGP cost to the BGP next-hop *from where the RR sits*. The
   path that is optimal for the RR can be suboptimal — or a single point of failure —
   for a client in a different IGP location. RR clients "might be better served using
   a different prefix (due to a different position in IGP topology)."
   [ipSpace — BGP Optimal Route Reflection 101](https://blog.ipspace.net/2021/10/bgp-optimal-route-reflection/)
2. **Only ONE path is reflected, so the client has no installed backup.** When the
   RR's chosen exit fails, convergence cannot complete until the RR itself learns of
   the failure, re-runs best-path, and re-advertises. A peer-reviewed measurement
   ("The Effects of iBGP Convergence", arXiv:2503.15249) finds route reflection
   roughly **doubles** the post-failure violation/convergence time versus a full mesh,
   because the RR must replicate the work of both the event originator and the backup
   router before clients hear about the new best path.
   [arXiv:2503.15249](https://arxiv.org/pdf/2503.15249)

## The change → trap → blast
**Change classes that trigger it (all look benign in a session/prefix review):**
- An RR cluster/topology edit, a new RR, or moving a client to a different RR — which
  silently changes which single path each client sees.
- A LOCAL_PREF / MED / weight / IGP-metric change *upstream* that flips the RR's
  best-path so the RR now reflects a different single exit (clients lose the exit they
  were depending on without any session or prefix-count change).
- Removing / failing to enable **add-path** (RFC 7911) or **Optimal Route Reflection**
  (RFC 9107) — the mitigation that would have published the backup. Removing
  `additional-paths send` on an RR collapses clients back to single-path visibility.
  [ipSpace — Optimal path selection with add-paths](https://blog.ipspace.net/2021/12/bgp-multipath-addpath/)

**Trap:** at the RR the prefix is present and best (D2 clean); all iBGP sessions stay
ESTABLISHED (D1=0). A reviewer checking "did any session drop / any prefix disappear"
sees nothing. The damage is to paths the *client* would install — invisible at the RR.

**Blast set (get this right in the oracle):**
- **D1 = 0** — no session change. (Common LLM error: claiming sessions drop. They do
  NOT for an attribute/topology selection change.)
- **D2 (client-side)** — a client that previously had ≥2 usable paths now has 1; if
  the change flips the reflected best to an exit the client cannot use as well (or at
  all in a partitioned topology), the client can lose the prefix entirely while the
  RR still shows it present. The mismatch between "RR has the prefix" and "client has
  a usable path" is the signature.
- **D5 (redundancy degradation)** — THIS IS THE PRIMARY DIMENSION. Path diversity at
  clients collapses N→1; the hot backup is gone. The next failure that ECMP/backup
  would have absorbed instantly now incurs an RR-mediated reconverge.
- **D7 (forwarding-path change)** — clients home to the RR's single chosen next-hop;
  forwarding can become suboptimal ("the RR's best, not mine") even when reachability
  is preserved.
- **D3 (conditional)** — only manifests as reachability loss after the reflected exit
  later fails, during the elongated RR-mediated convergence window.

## Batfish modellability
**GOOD, with care.** Batfish models route reflection (ORIGINATOR_ID/CLUSTER_LIST,
client vs non-client) and computes per-node RIBs, so the oracle can diff the
**per-client installed path set** pre/post and observe the N→1 collapse (D5) and the
next-hop change (D7) directly — these are deterministic on a single snapshot pair.
- Workaround for D3 (the conditional reachability loss): use the two-snapshot pattern
  — snapshot B additionally fails the reflected exit; traceroute from the client
  returns NO_ROUTE / takes the long way during the window. Score the path-set collapse
  as the primary oracle, the conditional reachability as the follow-up.
- What Batfish does NOT capture: the *timing* of convergence (the arXiv ~2× figure is
  a runtime property, not a snapshot property). Do not score convergence seconds;
  score the structural loss of the backup path.
- add-path / RFC 9107 ORR support varies by Batfish version — verify the snapshot
  actually models multiple advertised paths before grading an add-path-removal
  scenario, or the "before" state will already show only one path and the diff
  vanishes.

## Why this is NOT redundant
- Distinct from "RR client removal" (Pattern 7 in `blast_radius_patterns.md`): that
  *removes a client's reflection entirely*. This class **keeps everything established
  and present** and only hides the backup — a strictly subtler, harder-to-detect
  signature.
- Distinct from generic LOCAL_PREF TE (Pattern 2): there the second-order effect is a
  forwarding shift on a flat mesh; here the RR *suppresses information*, so the client
  cannot even compute the alternative.

## Key lessons
1. An RR reflects ONE path. "The prefix is present on the RR" does NOT mean clients
   have a backup.
2. add-path (RFC 7911) and ORR (RFC 9107) are the mitigations; removing/omitting them
   is a redundancy-degradation (D5) change with zero D1/D2 signal at the RR.
3. Attribute/topology changes that flip RR best-path are blast-radius events even
   though nothing drops.

## References
- [RFC 4456 — BGP Route Reflection (§11)](https://www.rfc-editor.org/rfc/rfc4456.html)
- [RFC 4271 — BGP-4 (§9.1 decision process)](https://www.rfc-editor.org/rfc/rfc4271.html)
- [RFC 7911 — Advertisement of Multiple Paths in BGP (add-path)](https://www.rfc-editor.org/rfc/rfc7911.html)
- [RFC 9107 — BGP Optimal Route Reflection (ORR)](https://www.rfc-editor.org/rfc/rfc9107.html)
- [ipSpace — BGP Optimal Route Reflection 101](https://blog.ipspace.net/2021/10/bgp-optimal-route-reflection/)
- [ipSpace — Optimal BGP path selection with add-paths](https://blog.ipspace.net/2021/12/bgp-multipath-addpath/)
- ["The Effects of iBGP Convergence", arXiv:2503.15249](https://arxiv.org/pdf/2503.15249)
- Cross-refs (internal): `../batfish/blast_radius_patterns.md` (Pattern 7),
  `../dc/dc_summarization_ecmp_pitfalls.md` (Part B, add-path collapse).
