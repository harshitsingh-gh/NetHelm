# Authoring Topologies & Scenarios — Step-by-Step Recipe

> **Audience:** a human OR a smaller/cheaper LLM that needs to add a **new
> network topology** and **new test scenarios** to NetBrace *reliably*, without
> understanding the whole codebase.
>
> **The promise:** if you follow the numbered steps and pass every **GATE**, the
> result is correct. If a GATE fails, **stop and fix it — do not continue.** The
> GATEs are what make this safe for a weak model: you cannot ship a broken
> topology because Batfish and containerlab will reject it first.
>
> **Architecture overview lives in [`project_guide.md`](project_guide.md)** —
> read §1–§4 there once for the big picture, then come back here to *build*.
> Oracle/Batfish details live in [`batfish_oracle_runbook.md`](batfish_oracle_runbook.md).

---

## 0. The mental model (read once)

A "scenario" in NetBrace is built from two things:

1. A **baseline topology** — a set of router config files that form a *converged*
   network (all BGP sessions up, all routes present). This is the "before" state.
2. A **change** — a small unified-diff patch applied to one config. This is the
   proposed edit whose *blast radius* (what breaks) the model must predict.

Ground truth comes from **Batfish**: it reads the baseline configs and the
patched configs, and diffs the BGP sessions / routes. Whatever Batfish says
breaks **is** the right answer. You never hand-write the answer.

There are **two config artifacts for every router** and you must produce both:

| Artifact | Path | Format | Consumed by |
|---|---|---|---|
| Batfish snapshot config | `runs/<snap>/snapshot/configs/<node>.cfg` and embedded in `baseline_square4.py` | `<hostname>` header line + `frr version` line + full FRR config | **Batfish oracle** (the grader) |
| Live lab config | `harness/lab/<topo>/configs/<node>/frr.conf` + `daemons` | *pure* FRR running-config (no header line) | **containerlab** (live verification) |

They contain the **same routing config**; only the wrapper differs (see §3).
The reference example for both is the `square4` topology — study it before
building your own:

- Batfish form: `runs/2026-05-27_batfish_frrsq/snapshot/configs/r1.cfg`
- Live form: `harness/lab/frr_square/configs/r1/frr.conf` + `.../r1/daemons`
- containerlab wiring: `harness/lab/frr_square.clab.yml`

---

## 1. The deterministic addressing scheme (DO NOT improvise)

Reliability comes from **never inventing IPs**. Every address is computed from a
fixed rule. For a full-mesh of `N` routers `r1..rN`:

### 1a. Loopbacks and router-ids
```
node rX  →  loopback = 10.0.0.X/32  →  bgp router-id = 10.0.0.X
```

### 1b. Point-to-point links (use the 192.0.2.0/24 documentation block)
List the links in a **fixed order** (lower node number first). Link number `i`
counts from **0**:

```
link i  →  subnet 192.0.2.(4*i)/30
           first  endpoint (lower-numbered node)  = 192.0.2.(4*i + 1)
           second endpoint (higher-numbered node) = 192.0.2.(4*i + 2)
```

Example for the `square4` full mesh (6 links, `r1..r4`):

| i | link | subnet | low IP | high IP |
|---|---|---|---|---|
| 0 | r1–r2 | 192.0.2.0/30 | r1 = .1 | r2 = .2 |
| 1 | r1–r3 | 192.0.2.4/30 | r1 = .5 | r3 = .6 |
| 2 | r1–r4 | 192.0.2.8/30 | r1 = .9 | r4 = .10 |
| 3 | r2–r3 | 192.0.2.12/30 | r2 = .13 | r3 = .14 |
| 4 | r2–r4 | 192.0.2.16/30 | r2 = .17 | r4 = .18 |
| 5 | r3–r4 | 192.0.2.20/30 | r3 = .21 | r4 = .22 |

### 1c. Interface names
On each node, name interfaces `eth1, eth2, eth3, …` in the order links appear
for that node (scanning the link list top to bottom). `lo` is always the
loopback.

### 1d. Static routes (the backup path — keep this!)
Every node gets a static route to **each other loopback**, pointing at the
*far-side IP of the direct link* to that node:
```
ip route 10.0.0.Y/32 <IP of rY on the rX–rY link>
```
This is intentional: it means loopback **reachability** survives a BGP session
drop, which is exactly the subtlety we test models on. Keep it.

### 1e. iBGP full mesh
Single AS `65000`. Every node peers with every other node **via loopback IP**:
```
neighbor 10.0.0.Y remote-as 65000
neighbor 10.0.0.Y update-source lo
neighbor 10.0.0.Y next-hop-self
```
Each node originates its own loopback: `network 10.0.0.X/32`.

> **DO NOT** use other IP ranges, skip `next-hop-self`, peer on interface IPs
> instead of loopbacks, or omit the static routes. Each of these silently
> changes ground truth.

---

## 2. The Batfish config template (`<node>.cfg`)

Copy this verbatim and fill the `{{...}}` slots using §1. This is `r1` of
`square4`; the only per-node differences are the hostname, the loopback, the
interface IPs, the static routes, the neighbor list, and the originated network.

```
{{NODE}}

# This file describes the network interfaces
auto lo
iface lo inet loopback
    address 10.0.0.{{X}}/32

auto eth1
iface eth1 inet static
    address {{ETH1_IP}}/30
# ... repeat one auto/iface block per interface ...

# ports.conf --

frr version 10.6.1
frr defaults traditional
hostname {{NODE}}
service integrated-vtysh-config
!
ip forwarding
!
interface lo
 ip address 10.0.0.{{X}}/32
!
interface eth1
 ip address {{ETH1_IP}}/30
!
# ... one interface block per eth ...
!
ip route 10.0.0.{{Y}}/32 {{FARSIDE_IP}}
# ... one static route per OTHER loopback ...
!
router bgp 65000
 bgp router-id 10.0.0.{{X}}
 neighbor 10.0.0.{{Y}} remote-as 65000
 neighbor 10.0.0.{{Y}} update-source lo
 neighbor 10.0.0.{{Y}} next-hop-self
 # ... one 3-line neighbor block per OTHER node ...
 !
 address-family ipv4 unicast
  network 10.0.0.{{X}}/32
 exit-address-family
!
line vty
!
```

> **Critical for Batfish:** the **first line must be the bare hostname**
> (`{{NODE}}`) and the **`frr version 10.6.1`** + **`hostname {{NODE}}`** lines
> must be present. Batfish's FRR parser keys off these. Omitting them makes the
> file fail to parse → the oracle errors.

---

## 3. The live containerlab config (`frr.conf` + `daemons`)

The live form is **the same config minus the top wrapper**. Take the Batfish
`.cfg` and **delete everything above `frr defaults traditional`** (i.e. drop the
bare-hostname line and the `# This file describes the network interfaces` Debian
`auto/iface` block and the `# ports.conf --` line, and the `frr version` line).
What remains — from `frr defaults traditional` down to the final `!` — is
`frr.conf`.

`daemons` (identical for every node in a BGP-only lab):
```
zebra=yes
bgpd=yes
staticd=yes
# (all other daemons = no)
```
Copy `harness/lab/frr_square/configs/r1/daemons` and keep only these three `=yes`.

### The containerlab topology file `harness/lab/<topo>.clab.yml`
```yaml
name: <topo>            # short, no spaces, e.g. "triangle3"

topology:
  defaults:
    kind: linux
    image: quay.io/frrouting/frr:10.6.1
  nodes:
    r1:
      binds:
        - /home/harshitsingh/projects/NetHelm/harness/lab/<topo>/configs/r1/daemons:/etc/frr/daemons
        - /home/harshitsingh/projects/NetHelm/harness/lab/<topo>/configs/r1/frr.conf:/etc/frr/frr.conf
    # ... one node block per router ...
  links:
    - endpoints: ["r1:eth1", "r2:eth1"]   # MUST match the link order/intf names from §1c
    # ... one line per link ...
```

> **DO NOT** use relative bind paths — containerlab resolves binds relative to
> its own runtime, so binds **must be absolute**. (This was a real bug; see the
> "fix clab bind paths" commit.) The interface names in `links:` **must** match
> the `eth` numbers you assigned in §1c, or the live lab will not converge.

---

## 4. The verification GATES (this is the whole point)

Run these in order. **Each must pass before the next.** A weak model that stops
at the first failing gate cannot ship a broken topology.

### GATE 1 — Batfish parses every config (no live containers needed)
```bash
source harness/venvs/nethelm/bin/activate
python - <<'PY'
import pathlib
from pybatfish.client.session import Session
snap = "runs/<your_snapshot>/snapshot"   # dir containing configs/<node>.cfg
bf = Session(host="127.0.0.1"); bf.set_network("authoring_check")
bf.init_snapshot(snap, name="s", overwrite=True)
df = bf.q.fileParseStatus().answer().frame()
print(df[["File_Name","Status"]].to_string())
assert (df["Status"] == "PASSED").all(), "GATE 1 FAILED: a config did not parse"
# Converged? every iBGP session should be ESTABLISHED in the baseline:
s = bf.q.bgpSessionStatus().answer(snapshot="s").frame()
print(s["Established_Status"].value_counts().to_string())
assert (s["Established_Status"] == "ESTABLISHED").all(), "GATE 1 FAILED: a session is not ESTABLISHED"
print("GATE 1 PASS")
PY
```
A full mesh of `N` nodes has `N*(N-1)` directional sessions, all ESTABLISHED.

### GATE 2 — containerlab deploys and converges (the live truth)
```bash
sudo clab deploy -t harness/lab/<topo>.clab.yml
# wait ~30s for BGP to converge, then check one router:
docker exec clab-<topo>-r1 vtysh -c "show ip bgp summary"
# GATE 2 PASS = every neighbor shows a numeric uptime (not "Active"/"Connect"/"Idle")
```
This must agree with GATE 1. If Batfish says ESTABLISHED but the live router does
not, the **live lab** is the tie-breaker — investigate before trusting the oracle.

### GATE 3 — oracle is deterministic on this topology
After wiring the topology into the generator (§5) and generating tasks:
```bash
netbrace safety oracle   --suite tasks/safety/<new> --host 127.0.0.1
netbrace safety validate --suite tasks/safety/<new> --require-oracle
```
Every task must end with `oracle.status="ready"` and `deterministic=True`. A
non-deterministic task is **quarantined, not shipped** — it means Batfish gave
different answers across repeated runs and the ground truth is untrustworthy.

> **If any GATE fails:** the most common causes, in order — (1) missing
> `frr version`/`hostname` header (GATE 1 parse fail); (2) a typo'd IP that
> breaks a /30 pair (GATE 1 session not ESTABLISHED); (3) relative bind path or
> wrong `eth` name (GATE 2 won't converge); (4) you edited the IP scheme by hand
> (any gate). Re-derive every address from §1 — do not patch ad-hoc.

---

## 5. Wiring a new topology + new scenarios into NetBrace

Once GATE 1/2 pass, make the topology a first-class suite source. Mirror the
`square4` pattern exactly — copy, don't redesign.

### 5a. Add a baseline module
Create `netbrace/tasks/safety/baseline_<topo>.py` modeled on
`baseline_square4.py`. It must export:
- `NODES` — list of node names
- `LOOPBACK_IP` — `{node: "10.0.0.X"}`
- `WATCHED_PREFIXES` — the loopback /32s that count for route scoring
- `LINKS` — `[(a_node, a_intf, b_node, b_intf), ...]` in §1 order
- `baseline_configs()` — returns a fresh `{node: <Batfish .cfg text>}` dict

> Paste the **GATE-1-verified** `.cfg` text in as the config strings. Once
> verified, treat this file as frozen (see `project_guide.md` §10).

### 5b. Add new scenario *intents* (this is "new scenarios")
A scenario type is just a **pure `str -> str` mutation** of one config plus an
entry in the generator. In `netbrace/tasks/safety/generator.py` the two existing
intents are the template:

```python
def _mutate_shut_neighbor(config: str, peer_ip: str) -> str: ...   # removes a neighbor → session drops
def _mutate_remove_network(config: str, prefix: str) -> str: ...   # removes origination → prefix drops
```

To add an intent (example `deny_prefix`, or a **trap** like `change_local_pref`
where nothing actually breaks):

1. Write `_mutate_<intent>(config, **params) -> str` — a small pure function.
   Keep it boring; ~10 lines.
2. Add a combo loop for it in `_combos()` so generation enumerates it
   deterministically.
3. Add an `elif intent == "<intent>":` branch in `_build_task()` that sets
   `after`, a human `desc`, and a `change_id`.
4. The generator **self-checks** every patch round-trips
   (`apply_unified_diff(before, patch) == after`); if your mutation is sane this
   passes automatically.

You do **not** write the expected answer — the Batfish oracle computes it. For a
**trap** scenario (correct answer = "nothing breaks"), set the task's `meta`
trap flag so a model that predicts impact is scored as a `false_alarm`.

### 5c. Generate, oracle, and run
```bash
netbrace safety generate --count <N> --out tasks/safety/<new>   # NOTE: generator currently hardcodes square4 baseline;
                                                                #       point it at baseline_<topo> for a new topology
netbrace safety oracle   --suite tasks/safety/<new> --host 127.0.0.1   # GATE 3
netbrace safety validate --suite tasks/safety/<new> --require-oracle
netbrace eval fake       --suite tasks/safety/<new> --run-id check_<new>   # zero-API sanity: oracle mode → F1 1.0
netbrace report          --run runs/check_<new> --figures paper/figures
```

> The generator's `_build_task()` currently calls `sq4.baseline_configs()`
> directly. To use a new topology, parameterize that call on the chosen baseline
> module (smallest possible change — pass the module in `GenerationSpec`). This
> is the one code edit a new topology needs; everything downstream is
> topology-agnostic.

---

## 6. Running scenarios with a real model (GPT-4o **or Claude**)

Yes — any provider Inspect AI supports works. The model is just a CLI flag.

```bash
pip install -e ".[eval]"          # installs inspect-ai

# OpenAI
export OPENAI_API_KEY=sk-...
netbrace eval run --suite tasks/safety/<new> --model openai/gpt-4o --limit 1 --run-id smoke_gpt4o

# Anthropic / Claude  ← same command, different --model + key
export ANTHROPIC_API_KEY=sk-ant-...
netbrace eval run --suite tasks/safety/<new> --model anthropic/claude-sonnet-4-6 --limit 1 --run-id smoke_claude
# other ids: anthropic/claude-opus-4-8, anthropic/claude-haiku-4-5-20251001
```

`--model` format is `provider/model-id`. Always do `--limit 1` first and confirm
cost < $10 before a full run (project rule — ask a human before larger spend).
Grade + report are identical regardless of model:
```bash
netbrace report --run runs/smoke_claude --figures paper/figures
```

---

## 7. One-screen checklist

```
[ ] Derived ALL ips from §1 — invented none
[ ] Wrote <node>.cfg for every node (hostname header + frr version present)
[ ] Wrote frr.conf + daemons for every node (pure running-config)
[ ] Wrote <topo>.clab.yml with ABSOLUTE bind paths, links match eth names
[ ] GATE 1: Batfish parses all + all sessions ESTABLISHED
[ ] GATE 2: clab deploys + live `show ip bgp summary` all up
[ ] baseline_<topo>.py exports NODES/LOOPBACK_IP/WATCHED_PREFIXES/LINKS/baseline_configs()
[ ] (new intents) pure _mutate_* fn + _combos + _build_task branch
[ ] GATE 3: oracle ready + deterministic=True for every task
[ ] eval fake (oracle mode) → macro_f1 = 1.0
[ ] (optional) eval run --model ... --limit 1, cost < $10
```

If every box is checked, the scenario is publishable-grade ground truth.
</content>
</invoke>
