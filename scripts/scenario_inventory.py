#!/usr/bin/env python
"""Emit a HUMAN-READABLE review CSV of every NetHELM scenario — full sentences, not
jargon. Each row explains: what the network is, the change made, what an engineer
would expect, what actually happens (with the live Batfish ground truth translated
into English), why it matters, and what it tests.

Usage:  python scripts/scenario_inventory.py [--out paper/refs/scenario_inventory.csv]
        (needs Batfish on 9997 for the live ground truth of hand-authored scenarios)
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from netbrace.tasks.safety import scenarios
from netbrace.tasks.safety import generator_ipc as gen
from netbrace.tasks.safety import generator_leak as genleak
from netbrace.tasks.safety import generator_lp as genlp
from netbrace.tasks.safety import generator_scale as genscale


def humanize_key(k: str) -> str:
    """Translate one oracle ground-truth key into a plain-English sentence."""
    p = dict(re.findall(r"(\w+)=([^|]+)", k))
    if k.startswith("session"):
        return f"router {p.get('node','?')}'s BGP session to {p.get('peer_ip', p.get('peer','?'))} goes DOWN"
    if k.startswith("route|"):
        return f"router {p.get('node','?')} loses the route to {p.get('prefix','?')} from its routing table"
    if k.startswith("reach"):
        return f"{p.get('src','?')} can no longer deliver traffic to {p.get('dst','?')}"
    if k.startswith("waypoint"):
        return (f"traffic from {p.get('src','?')} to {p.get('dst','?')} no longer passes "
                f"through the required inspection node '{p.get('via','?')}'")
    if k.startswith("redundancy"):
        return f"{p.get('node','?')} loses a redundant/equal-cost path to {p.get('dst', p.get('prefix','?'))} (resilience cut, still reachable)"
    if k.startswith("anomaly"):
        kind = k.split("|")[1] if "|" in k else "drop"
        return f"traffic to {p.get('dst','?')} is silently {kind.replace('_',' ')} at router {p.get('node','?')}"
    if k.startswith("scale"):
        return f"router {p.get('node','?')}'s forwarding table exceeds its {p.get('resource','fib').upper()} capacity budget"
    if k.startswith("bgp_withdrawn"):
        return (f"the BGP advertisement for {p.get('network','?')} is withdrawn from {p.get('node','?')} "
                f"(a backup keeps it reachable, so only a control-plane monitor would notice)")
    if k.startswith("intent"):
        return (f"a {p.get('kind','policy')} intent for {p.get('dst','?')} from {p.get('src','the network')} "
                f"is broken (it still reaches, but not the way the design intended)")
    return k


def humanize_gt(keys: list[str]) -> str:
    if not keys:
        return "Nothing changes (this is a no-op / negative control)."
    return "; ".join(humanize_key(k) for k in keys) + "."


# --- Rich, curated, plain-English explanations for the hand-authored scenarios ---
# Each: (title, category, setup, change, expectation, why_it_matters, what_it_tests, caveats)
RICH = {
    "ipc": (
        "Cleanup filter silently strands a customer prefix (FLAGSHIP)",
        "Hand-authored flagship. Mechanism: internal routing-policy silent withdrawal.",
        "A 3-router ISP-style network: a route reflector (r1) with two client routers (r2, r3). r3 originates a customer network (203.0.113.0/24) that has NO backup path — it is reachable only via BGP.",
        "An engineer adds an outbound 'cleanup' filter on r1 toward r2 to stop advertising internal noise. The filter permits the infrastructure prefixes but, by omission, drops the customer prefix — the classic 'forgot the final permit-any.'",
        "Looks like a routine, low-risk advertisement tidy-up. The BGP session stays up and the loopbacks are still advertised, so the network 'looks fine.'",
        "This is the single most common shape of change-induced outage (the 'implicit deny-all' maintenance trap; the prefix-level shape of the Facebook Oct-2021 outage).",
        "Whether the model knows a policy edit can strand a prefix WITHOUT dropping the session — i.e. it does not reflexively predict a session loss, and it does catch the silent withdrawal.",
        "Ground truth computed live by Batfish; deterministic. Tier A (faithful minimal instance).",
    ),
    "ipc_static": (
        "Same filter, but a static backup hides the damage (the discriminator)",
        "Hand-authored. Mechanism: same withdrawal, but control-plane-only.",
        "Identical to the flagship, except client r2 ALSO has a static backup route to the customer prefix.",
        "The same outbound cleanup filter on r1 toward r2.",
        "Looks identical to the flagship — and to a no-op. Nothing in the data plane changes.",
        "Tests whether a monitor that only checks reachability is fooled: the BGP advertisement is genuinely gone (a real control-plane change you'd want to know about), but the static route keeps traffic flowing.",
        "Whether the model can tell 'the BGP route was withdrawn but a backup saved reachability' apart from 'nothing happened.' This is why we score a separate control-plane dimension.",
        "Live Batfish; deterministic. Tier A. Its whole value is that the control-plane (bgp_withdrawn) dimension is scored and reported.",
    ),
    "ipc_fanout": (
        "The cleanup filter is pushed to ALL clients at once (multi-node blast)",
        "Hand-authored. Mechanism: the same withdrawal, applied fabric-wide.",
        "A larger route reflector with several client routers, all serving the same customer prefix.",
        "The same cleanup filter, but applied as a template to every client at once (how operators actually roll out policy).",
        "Same 'routine cleanup' expectation — but now the mistake is replicated everywhere.",
        "Realistic: operators template their client policy, so one bad template strands the prefix on every client simultaneously.",
        "Whether the model enumerates the FULL set of affected routers (correct cardinality), not just one — does it realize the blast is multi-node?",
        "Live Batfish; deterministic. Tier A. This is a cardinality variant of the flagship, not a new mechanism — labeled as such.",
    ),
    "ipc_aggregate": (
        "Dropping specific routes while a summary route survives (reachable, but TE broken)",
        "Hand-authored. Mechanism: aggregate masks the loss of more-specifics.",
        "A network advertising both a summary route (a /24) and more-specific routes (two /25s) that pin traffic for traffic-engineering reasons.",
        "The cleanup filter drops the two specific /25 routes but keeps the covering /24 summary.",
        "Coarse reachability still works (the /24 covers everything), so a ping test passes and it looks fine.",
        "A pernicious real trap: reachability survives, but the traffic-engineering/multihoming the specifics provided is silently broken (RFC 4632 de-aggregation pitfall).",
        "Whether the model sees that 'still reachable' is NOT 'still correct' — it must flag that the specific routes are gone AND that the design intent they served is violated, even though no destination became unreachable.",
        "Live Batfish; deterministic. Tier A. This is the case that justifies a first-class 'intent' dimension.",
    ),
    "leak_ms": (
        "A more-specific route leak pulls traffic into a black hole (a route is ADDED, nothing is lost)",
        "Hand-authored. Mechanism: route leak / longest-prefix-match hijack.",
        "Three networks (autonomous systems) in a chain: a victim that owns a prefix, a transit in the middle, and a 'leaker.'",
        "The leaker starts advertising a MORE-SPECIFIC piece of the victim's address space (a /25 of the victim's /24) that it cannot actually deliver.",
        "A change that only ADDS a route looks harmless — no session drops, no route is lost; a 'count what disappeared' view sees nothing.",
        "This is the Cloudflare-2019 / Telekom-Malaysia-2015 mechanism: longest-prefix-match pulls the victim's traffic to the leaker, where it is dropped. Session and prefix counts give zero signal.",
        "The core argument for multi-dimensional scoring: whether the model sees that adding a route can cause a blackhole — the damage is purely in the data plane.",
        "Live Batfish; deterministic. Tier A. (We model the leaker's no-path as a discard/blackhole — the worst case; the real incident was congestion-based degradation.)",
    ),
    "lp_waypoint": (
        "A LOCAL_PREF tweak reroutes traffic off a mandatory inspection node",
        "Hand-authored. Mechanism: BGP attribute change shifts the path.",
        "An internal network where traffic to a customer must pass through an inspection node ('way'); there is also a bypass path ('alt').",
        "An engineer raises the LOCAL_PREF on the bypass path (a one-line attribute edit, e.g. for cost reasons).",
        "Tempting wrong answer: 'changing BGP config will drop a session.' It won't — and the destination stays perfectly reachable.",
        "The documented LLM failure mode (models wrongly predict a session drop on an attribute change). The real harm is a security/compliance one: traffic now bypasses the inspection node while everything still pings.",
        "Whether the model avoids the session-loss reflex AND catches the second-order effect (a required waypoint is now skipped), with no reachability loss to tip it off.",
        "Live Batfish; deterministic. Tier B — the iBGP next-hop is resolved with static routes (a Batfish modeling workaround), which is non-idiomatic; an eBGP idiomatic twin is queued.",
    ),
    "clos_summary": (
        "Summarizing a data-center fabric blackholes half the traffic to one server",
        "Hand-authored. Mechanism: DC underlay summarization hides a missing path.",
        "A small data-center 'Clos' fabric: 2 spine switches and 3 leaf switches. One spine (spine2) has no direct path to the leaf that hosts a server.",
        "An operator 'optimizes' the leaf forwarding tables by summarizing the underlay on the spines (advertise one big block instead of every subnet) and suppressing the specific server route.",
        "Looks like a pure efficiency win (smaller tables). The summary makes every spine appear to have the route, so prefix-presence checks pass.",
        "RFC 7938 warns summarization in a Clos causes blackholing. Because traffic is load-balanced across both spines, HALF the traffic to the server is silently dropped at the spine that can't reach it — while dashboards stay green.",
        "Whether the model catches a PARTIAL (half-of-traffic) blackhole that a simple 'is it reachable?' check misses, and sees that the summary is masking a real loss.",
        "Live Batfish; deterministic (scored as 'a blackhole path exists,' not which flow hashes where). Tier A, but note: this is a FIXED-asymmetry instance of the RFC 7938 hazard, not the dynamic link-failure version (that upgrade is queued).",
    ),
    "scale_deagg": (
        "De-aggregation floods a router past its forwarding-table limit",
        "Hand-authored. Mechanism: scale / FIB-TCAM overflow.",
        "An edge router that learns a single summary route (a /16) from upstream and has a limited forwarding-table budget.",
        "Upstream removes the summary and instead advertises all the constituent more-specific routes (de-aggregation), multiplying the route count the edge must install.",
        "Again a change that only ADDS routes — nothing is withdrawn, so a 'count what's lost' view sees nothing.",
        "This is the Rogers-2022 / '512k day' mechanism: the device's forwarding hardware (e.g. TCAM) overflows its capacity, after which behavior is undefined. Routers crash or silently drop.",
        "Whether the model reasons about a RESOURCE limit (counts the routes vs the device's budget) rather than just connectivity — a different axis entirely.",
        "Live Batfish gives the route count; the capacity limit is a stated spec annotation. Tier D (spec-annotated) — we score 'does it cross the budget,' not which routes get evicted (hardware-dependent).",
    ),
    "mgmt_lockout": (
        "A cleanup locks the NOC out of a device — zero customer prefixes touched",
        "Hand-authored. Mechanism: management-plane / out-of-band lockout.",
        "A network with a normal customer data path AND a NOC 'jump host' that reaches each device's management address over the network (in-band management).",
        "A cleanup filter on the core router omits the device management subnet when advertising toward the jump host (again, by omission).",
        "The tempting wrong answer: 'no customer prefixes are affected, so this is safe.' That conclusion is exactly backwards.",
        "This is the recovery-path failure in Facebook-2021, AWS-2021, Rogers-2022, Cloudflare-2022: the change severs the tools you need to fix it. Zero customer impact, top severity.",
        "Whether the model recognizes that breaking the management path is catastrophic even though no customer route changed — inverted-severity reasoning.",
        "Live Batfish; deterministic. Tier A. NOTE: built but NOT yet through the noc-veteran/red-team review gate.",
    ),
    "blackhole": (
        "Removing a 'redundant' static route silently black-holes a destination",
        "Hand-authored. Mechanism: recursive next-hop failure.",
        "A 4-router mesh where one router's BGP route to a destination depends on a static route to resolve its next-hop.",
        "An engineer removes that static route, believing it is redundant.",
        "Looks like cleaning up an unused route.",
        "Classic silent killer: removing the static makes the BGP next-hop unresolvable, so traffic to the destination is silently dropped (not an error — just gone).",
        "Whether the model follows the recursive next-hop chain (static → BGP next-hop → reachability) rather than treating the static as isolated.",
        "Live Batfish; deterministic. Tier A. This also covers the 'next-hop-self / recursive-resolution' class.",
    ),
    "ecmp": (
        "Removing one of two equal-cost paths halves redundancy (still reachable)",
        "Hand-authored. Mechanism: redundancy / ECMP reduction.",
        "A router with two equal-cost paths to a destination (for resilience).",
        "One of the two equal-cost routes is removed.",
        "Reachability is completely unaffected, so a connectivity test sees nothing.",
        "Capacity/resilience is cut in half — the kind of 'nothing broke' change that removes your safety margin before the next failure.",
        "Whether the model reports a redundancy/resilience loss even when reachability is intact. (Deliberately simple — a sanity anchor, not a hard case.)",
        "Live Batfish; deterministic. Tier A. The most obvious scenario in the set — kept as a baseline anchor.",
    ),
    "waypoint": (
        "A static-route change reroutes traffic off a required inspection node",
        "Hand-authored. Mechanism: path/waypoint shift via static route.",
        "A network where traffic from a source to a destination must transit an inspection node ('way'), with an alternate path available.",
        "A static route on the source is changed so traffic takes the alternate path instead.",
        "The destination stays reachable, so it looks fine.",
        "A compliance/security regression with no availability symptom: the mandated inspection node is bypassed.",
        "Whether the model catches an intent/waypoint violation with no reachability loss. (Companion to the LOCAL_PREF version, but driven by a static route rather than a BGP attribute.)",
        "Live Batfish; deterministic. Tier A.",
    ),
}


def gen_sentence(spec) -> str:
    """A readable description of one generated Class-1 variant."""
    who = (f"toward one client" if spec.filtered == "one"
           else f"toward all {spec.k} clients")
    direction = "outbound on the route reflector" if spec.direction == "out" else "inbound on a client"
    n = 1 if spec.filtered == "one" else spec.k
    if spec.prefix == "plain":
        effect = (f"It withdraws a customer prefix that has no backup, so {n} "
                  f"client(s) lose the route and can no longer reach it.")
    elif spec.prefix == "static":
        effect = (f"It withdraws the BGP route for a prefix that DOES have a static "
                  f"backup, so the advertisement is lost on {n} client(s) but traffic "
                  f"still flows — only a control-plane monitor would catch it.")
    else:
        effect = (f"It drops the specific /25 routes while a covering /24 summary "
                  f"survives, so traffic still reaches but the traffic-engineering "
                  f"intent those specifics served is broken on {n} client(s).")
    difficulty = {"implicit": "the filter forgets a final permit-any (implicit deny-all)",
                  "explicit_deny": "the filter explicitly denies the prefix",
                  "wrong_le": "the filter uses a wrong prefix-length bound that misses it"}[spec.match]
    return (f"A route reflector with {spec.k} client routers. A 'cleanup' route-map is "
            f"applied {direction} {who}. {effect} Variant: {difficulty}. The AS numbers "
            f"and IP addressing are randomized per seed, so each generated instance is "
            f"novel even though the failure mechanism is publicly documented.")


# --- plain-English sentences for the three NEW generator families ---------- #
def leak_sentence(spec) -> str:
    scope = {"low_half": "the lower half", "high_half": "the upper half",
             "both_halves": "both halves"}[spec.leak_scope]
    if spec.leak_kind == "ms_blackhole":
        effect = (f"The leaker advertises a more-specific piece ({scope}) of the "
                  f"victim's address block that it CANNOT actually deliver, so traffic "
                  f"for those addresses is pulled to the leaker and silently dropped "
                  f"(a blackhole). Nothing is withdrawn — a route is ADDED — so a "
                  f"'count what's lost' view sees zero.")
    else:
        effect = (f"The leaker advertises a more-specific piece ({scope}) of the "
                  f"victim's block AND can deliver it — so the traffic still arrives, "
                  f"but via the wrong network, bypassing the legitimate origin "
                  f"(a route hijack/impersonation, the AS7007 / Pakistan-YouTube shape). "
                  f"Everything still pings; only the path/intent is violated.")
    return (f"A 3-network chain (victim — transit — leaker), eBGP, freshly renumbered "
            f"per seed. {effect}")


def lp_sentence(spec) -> str:
    knob = {"lp_raise_alt": "raises LOCAL_PREF on the bypass path",
            "lp_drop_way": "lowers LOCAL_PREF on the inspection path",
            "prepend_way": "adds AS-path prepending on the inspection path"}[spec.knob]
    if spec.effect == "bypass":
        return (f"A source dual-homed to two upstreams — a required inspection path "
                f"('way') and a bypass ('alt'), all eBGP with no static-route crutch. "
                f"The change {knob}, flipping the best path OFF the inspection node "
                f"onto the bypass. Sessions stay up and the destination stays "
                f"reachable — but the mandatory inspection node is now skipped "
                f"(a security/compliance regression with no availability symptom).")
    return (f"Same dual-homed eBGP topology. The change {knob}, BUT applied where it "
            f"does NOT change the best path — a genuine no-op. The correct answer is "
            f"'nothing breaks': a calibration trap that catches a model inventing "
            f"damage that isn't there.")


def scale_sentence(spec) -> str:
    margin = {"over_clear": "comfortably exceeds the device's forwarding-table budget "
                            "(clear overflow)",
              "over_marginal": "exceeds the budget by exactly one route (the model must "
                               "actually COUNT, not guess)",
              "under": "stays UNDER the budget — no overflow (a trap for models that "
                       "pattern-match 'de-aggregation = overflow')"}[spec.margin]
    fate = ("and the covering summary route is ALSO withdrawn (the summary is genuinely lost)"
            if spec.supernet_fate == "withdrawn"
            else "while the covering summary stays advertised (reachability is fine; this is "
                 "pure forwarding-table pressure)")
    return (f"An upstream–edge eBGP pair, freshly renumbered per seed. Upstream "
            f"de-aggregates a summary into many more-specific routes so the installed "
            f"route count {margin}, {fate}. Budget magnitudes are anchored to public "
            f"hardware ceilings (e.g. the 16,384-entry ECMP-group table), scaled down.")


def _gen_block(label, category, what, builder, spec):
    return {
        "scenario": f"generated: {label}",
        "title": f"Auto-generated variant — {category}",
        "category": category,
        "what_the_network_is": what,
        "the_change_made": builder(spec),
        "what_an_engineer_expects": "A routine, safe-looking change.",
        "what_actually_happens (live ground truth, in plain English)":
            "(intended structure as described in 'the_change_made'; verified live "
            "against Batfish at sweep time — all 60 instances 10×-determinism-gated)",
        "why_it_matters (real-world grounding)":
            "Mass-produced with randomized addressing/ASNs so models can't win by "
            "memorizing a public incident — the contamination-controlled split.",
        "what_it_tests_about_the_model":
            "The same mechanism reasoning at scale on never-before-seen numbering.",
        "how_we_verified_it / caveats":
            "Generator deterministic per seed; full suite 10×-determinism-gated. Tier A.",
        "is_it_a_trap": "YES — the safe-looking answer is wrong",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="paper/refs/scenario_inventory.csv")
    ap.add_argument("--no-live", action="store_true")
    args = ap.parse_args()

    rows = []
    for name in sorted(scenarios.REGISTRY):
        scn = scenarios.build(name)
        title, cat, setup, change, expect, why, tests, caveats = RICH.get(
            name, (name, "(uncatalogued)", "", "", "", "", "", ""))
        if args.no_live:
            actual = "(live ground truth skipped)"
        else:
            try:
                from netbrace.batfish.extended_oracle import ExtendedOracle
                truth = ExtendedOracle().compute(scn)
                keys = sorted(k for s in truth.key_sets().values() for k in s)
                actual = humanize_gt(keys)
            except Exception as e:  # noqa: BLE001
                actual = f"(ERROR computing ground truth: {e})"
        rows.append({
            "scenario": name,
            "title": title,
            "category": cat,
            "what_the_network_is": setup,
            "the_change_made": change,
            "what_an_engineer_expects": expect,
            "what_actually_happens (live ground truth, in plain English)": actual,
            "why_it_matters (real-world grounding)": why,
            "what_it_tests_about_the_model": tests,
            "how_we_verified_it / caveats": caveats,
            "is_it_a_trap": "YES — the safe-looking answer is wrong" if scn.is_trap else "no",
        })

    # Generator family 1 — Class-1 silent withdrawal (ipc): 96 axis combos.
    for spec in gen.enumerate_specs():
        rows.append({
            "scenario": f"generated: ipc/{spec.dims_label()}",
            "title": "Auto-generated variant of the 'cleanup filter silently withdraws a prefix' class",
            "category": "Generated — Class 1 (silent withdrawal). One of 96 axis combinations.",
            "what_the_network_is": f"A route reflector with {spec.k} client routers and an origin, freshly renumbered for this instance.",
            "the_change_made": gen_sentence(spec),
            "what_an_engineer_expects": "A routine advertisement cleanup that looks safe.",
            "what_actually_happens (live ground truth, in plain English)": "(intended structure as described in 'the_change_made'; verified live against Batfish at sweep time — all 60 instances 10×-determinism-gated)",
            "why_it_matters (real-world grounding)": "Same maintenance trap as the flagship, mass-produced with randomized addressing so models can't win by memorizing a public incident.",
            "what_it_tests_about_the_model": "Same reasoning as the flagship, at scale and on never-before-seen numbering — the core of the contamination-controlled test set.",
            "how_we_verified_it / caveats": "Generator is deterministic per seed; full suite oracle-verified + 10×-determinism-gated. Tier A.",
            "is_it_a_trap": "YES — the safe-looking answer is wrong",
        })
    # Generator family 2 — Class-2 route leak (leak): 6 structural combos.
    for spec in genleak.enumerate_specs():
        rows.append(_gen_block(
            f"leak/{spec.dims_label()}", "Generated — Class 2 (route leak / LPM hijack), 1 of 6 combos",
            "A 3-network eBGP chain (victim, transit, leaker), freshly renumbered per instance.",
            leak_sentence, spec))
    # Generator family 3 — Class-5 attribute path-shift (lp): 6 combos incl. no-op trap.
    for spec in genlp.enumerate_specs():
        rows.append(_gen_block(
            f"lp/{spec.dims_label()}", "Generated — Class 5 (BGP-attribute path-shift), 1 of 6 combos",
            "A source dual-homed (all-eBGP, no static crutch) to an inspection path and a bypass, renumbered per instance.",
            lp_sentence, spec))
    # Generator family 4 — Class-8 de-aggregation overflow (scale): 6 combos.
    for spec in genscale.enumerate_specs():
        rows.append(_gen_block(
            f"scale/{spec.dims_label()}", "Generated — Class 8 (de-aggregation table overflow), 1 of 6 combos",
            "An upstream-edge eBGP pair with an annotated forwarding-table budget, renumbered per instance.",
            scale_sentence, spec))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    n_hand = sum(1 for r in rows if not r["scenario"].startswith("generated"))
    print(f"wrote {out} — {len(rows)} rows ({n_hand} hand-authored with live ground "
          f"truth + {len(rows) - n_hand} generated variants)")


if __name__ == "__main__":
    main()
