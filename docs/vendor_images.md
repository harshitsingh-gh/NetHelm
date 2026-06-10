# Vendor images — what NetHELM needs, why, and what to skip

> Decision context (2026-06-08): we are finishing the **blast-radius axis first**.
> This doc says exactly which device images to acquire now vs. defer. Bottom line:
> **acquire Arista cEOS-lab now; everything else defers.**

## Key insight: Batfish parses config *text*, not images

For **static blast-radius grading (D1–D8 via Batfish)** you mostly need **config
dialects**, not running containers. Batfish ingests Cisco IOS / Arista EOS /
Juniper Junos / Nokia / FRR **configuration text** directly and models RIB/FIB,
BGP policy, and ACL reachability without booting any device. So the D6 (filter)
blocker is really a *config-dialect* problem, not strictly an *image* problem.

You need **running images** only for: (a) live-emulator / hybrid scenarios that
Batfish can't model (PMTUD blackholes, BFD cascades, microloops, runtime FIB
overflow), and (b) the **commercial-agent baseline** (junos-mcp-server needs a real
Junos device).

## What each dimension actually requires

| Need | Image required? | Cheapest path |
|---|---|---|
| D1–D5, D7 (current live oracle) | No | FRR (already have) |
| **D6 filter (permit↔deny)** | **No image needed for static grading** — Batfish models **IOS/Arista/Juniper ACLs** as packet filters | Author an **Arista EOS** or **Cisco IOS** config snapshot with an ACL on an interface; grade via Batfish `searchFilters` differential. cEOS image only needed if we also want it *running*. |
| D8 scale (FIB/RIB/TCAM overflow) | No (static count) / Yes (runtime behavior) | Static: Batfish route count + a resource-budget annotation. Runtime: needs a real device. |
| Live-emulator hybrids | Yes | containerlab + vendor image |
| Commercial-agent baseline | Yes (Junos) | cRPD or vSRX + junos-mcp-server |

## The acquire-now / defer list

### ✅ Acquire now — Arista cEOS-lab
- **Why:** unblocks **D6 (filter)** with a Batfish-modeled ACL dialect AND gives a
  real **second vendor** (reviewers reject single-vendor benchmarks). Also runnable
  in containerlab if we want live validation.
- **Cost/gating:** **Free** with a registered arista.com account.
- **How:** download `cEOS-lab-<ver>.tar.xz` → `docker import cEOS-lab.tar.xz ceos:<ver>`
  → reference as a `ceos` kind in containerlab. For pure Batfish grading you can
  even skip the import and just feed EOS config text.

### ⏸️ Defer until the agent-baseline / hybrid phase
- **Juniper cRPD or vSRX** — needed for the `Juniper/junos-mcp-server` commercial
  baseline. cRPD (containerized routing) is the lightest; vSRX adds firewall/filter.
  Gating: a support.juniper.net account; cRPD needs a (often free-tier) license.
  **Defer** — it's a measurement-phase, not build-phase, dependency.
- **Nokia SR Linux** — free, containerlab-native, good optional 3rd vendor for
  breadth. Nice-to-have, not required for the first paper.
- **Cisco IOSv / CSR1000v / cat8000v** — only if we want *running* Cisco; for static
  Batfish grading, IOS **config text** suffices with no image. Image acquisition is
  license-gated (CML / employer). **Defer**; use IOS config text if a Cisco dialect
  is wanted for D6.

### ❌ Not needed / out of scope for v1
- Cisco DNM (that's the model-under-test moat, handled separately — build the demo
  first, then make the access case; see CLAUDE.md).
- Juniper Marvis (partner-program-gated API; v2).
- Arista EOS AI agent (public details thin; v2).

## One-line answer to "what images do you need?"

**Right now: just Arista cEOS-lab (free, arista.com account)** — and even that is
optional if we grade D6 from EOS/IOS config text rather than a running device.
**Later (measurement phase): Juniper cRPD or vSRX** for the commercial-agent
baseline. Everything else is optional breadth.
