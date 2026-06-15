# Batfish Oracle Runbook

Everything you need to run Task C: populate ground-truth blast-radius for the
square4 task suite using a live Batfish instance.

---

## 1. What Batfish does here (one paragraph)

Batfish is a static network analysis tool. It reads device config files (FRR
format here), builds a full control-plane model in memory, and answers questions
like "which BGP sessions are ESTABLISHED?" and "which prefixes appear in the
RIB?". The oracle (`netbrace/batfish/oracle.py`) runs two snapshots — the
**baseline** config set (converged network) and a **post-change** config set
(baseline with one patch applied) — queries each separately, and diffs the
results. The diff is the ground-truth blast radius.

---

## 2. Topology: square4

The task suite uses a **4-node FRR iBGP full mesh** called `square4`.

```
        r1 (10.0.0.1)
       /|  \
      / |   \
     /  |    \
    r2  r3   r4
   (10.0.0.2)(10.0.0.3)(10.0.0.4)
```

### Node facts

| Node | Loopback | BGP router-id | AS    |
|------|----------|---------------|-------|
| r1   | 10.0.0.1/32 | 10.0.0.1  | 65000 |
| r2   | 10.0.0.2/32 | 10.0.0.2  | 65000 |
| r3   | 10.0.0.3/32 | 10.0.0.3  | 65000 |
| r4   | 10.0.0.4/32 | 10.0.0.4  | 65000 |

### Physical links (eth interfaces)

| Link | Node A side       | Node B side       |
|------|-------------------|-------------------|
| r1–r2 | r1 eth1 192.0.2.1/30 | r2 eth1 192.0.2.2/30 |
| r1–r3 | r1 eth2 192.0.2.5/30 | r3 eth1 192.0.2.6/30 |
| r1–r4 | r1 eth3 192.0.2.9/30 | r4 eth1 192.0.2.10/30 |
| r2–r3 | r2 eth2 192.0.2.13/30 | r3 eth2 192.0.2.14/30 |
| r2–r4 | r2 eth3 192.0.2.17/30 | r4 eth2 192.0.2.18/30 |
| r3–r4 | r3 eth3 192.0.2.21/30 | r4 eth3 192.0.2.22/30 |

### BGP session matrix (all iBGP, AS 65000)

Every node peers with the other three via **loopback IPs** (update-source lo,
next-hop-self). Baseline has **12 ESTABLISHED sessions** (4 nodes × 3 peers,
counted from both ends = 12 directed sessions).

| From | To   | Peer IP (neighbour stmnt) |
|------|------|--------------------------|
| r1   | r2   | 10.0.0.2 |
| r1   | r3   | 10.0.0.3 |
| r1   | r4   | 10.0.0.4 |
| r2   | r1   | 10.0.0.1 |
| r2   | r3   | 10.0.0.3 |
| r2   | r4   | 10.0.0.4 |
| r3   | r1   | 10.0.0.1 |
| r3   | r2   | 10.0.0.2 |
| r3   | r4   | 10.0.0.4 |
| r4   | r1   | 10.0.0.1 |
| r4   | r2   | 10.0.0.2 |
| r4   | r3   | 10.0.0.3 |

### Routing: static + BGP origination

Each node has **static host routes** to all other loopbacks (via the directly-
connected /30 link). This means loopback reachability DOES NOT depend on BGP.
Shutting a BGP neighbor drops the BGP session and removes the loopback from the
BGP RIB, but data-plane reachability via the static route survives.

This is the key modelling subtlety: the `watched_prefixes` set (the four
loopbacks) is present in BOTH the static RIB and the BGP RIB. Batfish's
`routes()` query returns ALL routes. The oracle filters `prefixes_lost` to only
those in `watched_prefixes` **and** only where the prefix truly disappears from
the RIB entirely (not just from one protocol). Verify this is the right
behaviour when first running on the lab.

---

## 3. What the oracle code does, step by step

File: `netbrace/batfish/oracle.py`

```
BatfishOracle(host).compute(task)
│
├── _post_configs(task)            # apply task.change.patch → post-change configs
│
├── _materialize_snapshot(pre_configs, tmp/pre)   # write *.cfg files to /tmp
├── _materialize_snapshot(post_configs, tmp/post)
│
├── bf.init_snapshot(tmp/pre, name="pre")   # Batfish parses & models pre
├── bf.init_snapshot(tmp/post, name="post") # Batfish parses & models post
│
├── _established_sessions("pre")   # bgpSessionStatus query → set of (node, peer_ip, vrf)
├── _established_sessions("post")
├── sessions_lost = pre_sessions - post_sessions
│
├── _rib_prefixes("pre")           # routes() query → set of (node, network, vrf)
├── _rib_prefixes("post")
├── prefixes_lost = (pre_ribs - post_ribs) filtered by watched_prefixes
│
└── return BlastRadius(sessions_lost, prefixes_lost).normalized()
```

`compute_with_determinism_check` runs `compute` 3× and checks all results are
byte-identical. Tasks where Batfish returns different results across runs are
flagged `deterministic=False` and should be quarantined.

---

## 4. Batfish container setup

The lab host (`hungrykirby`) runs Batfish as a Docker container.

### Start the container

```bash
docker run -d \
  --name batfish \
  -p 9996:9996 -p 9997:9997 \
  batfish/allinone:nethelm
```

Check it is up:

```bash
curl -s http://127.0.0.1:9996/        # should return Batfish version JSON
# or:
timeout 2 bash -c "echo >/dev/tcp/127.0.0.1/9997" && echo "port open"
```

Port 9997 is the pybatfish gRPC endpoint. Port 9996 is the REST API.

### Stop / restart

```bash
docker stop batfish && docker rm batfish
```

---

## 5. Install oracle dependencies

```bash
source harness/venvs/nethelm/bin/activate
pip install -e ".[oracle]"     # installs pybatfish + pandas
```

Verify:

```bash
python -c "from pybatfish.client.session import Session; print('pybatfish OK')"
```

---

## 6. Run the oracle — step by step

### Step 1: generate the suite (if not done)

```bash
netbrace safety generate --count 20 --out tasks/safety/v0
netbrace safety validate --suite tasks/safety/v0
# Expected: OK — 20 tasks valid
```

### Step 2: verify column names BEFORE processing all tasks

This is critical. pybatfish column names can shift across Batfish versions. Run
this manually on one task first:

```python
source harness/venvs/nethelm/bin/activate
python << 'EOF'
from pybatfish.client.session import Session

bf = Session(host="127.0.0.1")
bf.set_network("netbrace_debug")

# Use the real snapshot from the lab run
bf.init_snapshot("runs/2026-05-27_batfish_frrsq/snapshot", name="debug", overwrite=True)

# BGP session query
df_sess = bf.q.bgpSessionStatus().answer().frame()
print("=== bgpSessionStatus columns ===")
print(df_sess.columns.tolist())
print(df_sess.head(3))
print()

# Routes query
df_routes = bf.q.routes().answer().frame()
print("=== routes columns ===")
print(df_routes.columns.tolist())
print(df_routes.head(3))
EOF
```

**Expected columns for bgpSessionStatus:**
`['Node', 'VRF', 'Local_AS', 'Local_Interface', 'Local_IP', 'Remote_AS', 'Remote_Node',
'Remote_IP', 'Address_Families', 'Session_Type', 'Established_Status']`

**Expected columns for routes:**
`['Node', 'VRF', 'Network', 'Next_Hop_IP', 'Next_Hop_Interface', 'Protocol', 'Admin_Distance',
'Metric', 'Tag']`

If the actual column names differ, edit `oracle.py` in `_established_sessions`
and `_rib_prefixes` accordingly. Re-run `pytest tests/unit -q` after any change.

### Step 3: run one task in isolation to verify results

```python
source harness/venvs/nethelm/bin/activate
python << 'EOF'
from netbrace.storage.layout import load_suite
from netbrace.batfish.oracle import BatfishOracle

tasks = load_suite("tasks/safety/v0")

# Pick the first shut_neighbor task
task = next(t for t in tasks if t.intent == "shut_neighbor")
print(f"Task: {task.task_id}")
print(f"Change: {task.change.description}")

oracle = BatfishOracle(host="127.0.0.1")
br = oracle.compute(task)
print(f"\nBlast radius:")
print(f"  sessions_lost: {[s.key for s in br.sessions_lost]}")
print(f"  prefixes_lost: {[p.key for p in br.prefixes_lost]}")
EOF
```

**Expected result for a `shut_neighbor` on r1 shutting r2:**
- `sessions_lost` should include:
  - `bgp|vrf=default|node=r1|peer_ip=10.0.0.2`
  - `bgp|vrf=default|node=r2|peer_ip=10.0.0.1`  ← both ends
- `prefixes_lost` should be **EMPTY** — because static routes preserve loopback
  reachability in the RIB even when the BGP session is gone.

If `sessions_lost` is empty, check:
1. Column name issue (see Step 2)
2. Whether `Established_Status` value is literally `"ESTABLISHED"` (it is in
   pybatfish ≥2024.x)
3. Whether FRR configs parse cleanly: `fileParseStatus` frame should show all
   `Status == "PASSED"`

### Step 4: run the full suite

```bash
netbrace safety oracle --suite tasks/safety/v0 --host 127.0.0.1
```

This processes all tasks sequentially. It is slow (~5–30 sec per task depending
on Batfish startup). For 20 tasks expect 5–10 minutes.

Progress is visible via stderr: any task that raises an exception prints
`ERROR <task_id>: <message>` and sets `oracle.status = "error"`.

### Step 5: validate

```bash
netbrace safety validate --suite tasks/safety/v0 --require-oracle
# Expected: OK — 20 tasks valid
```

If any task has `oracle.status == "error"`, validate prints the error and exits
nonzero. Fix the underlying issue and re-run `safety oracle` (it overwrites
existing task files).

### Step 6: spot-check against live routers (optional but recommended)

```bash
# With the containerlab topology running:
sudo containerlab deploy --topo harness/lab/frr_square.clab.yml

# Read live BGP state from r1:
python -c "
from netbrace.routers.containerlab_readonly import show_bgp_summary
print(show_bgp_summary('r1'))
"
```

Compare `show ip bgp summary` neighbour counts to what oracle reports.

---

## 7. Known open questions (plan.md §14 Q2/Q3)

**Q2: Does removing neighbor lines drop the session in Batfish?**
Yes — the generator's `shut_neighbor` mutation removes all three
`neighbor <peer_ip> ...` lines from the config. Batfish models this as the
session not existing in the post snapshot, so it drops from
`_established_sessions`. Verified behaviorally by the generator tests
(`test_shut_neighbor_removes_three_lines`). Needs live Batfish confirmation.

**Q3: Does any prefix actually leave the RIB when a session is shut?**
**No** for the square4 topology — static routes to all loopbacks mean the
loopback prefixes survive in the MAIN RIB even when the BGP origination is gone.
`prefixes_lost` (a MAIN-RIB disappearance diff) is therefore EMPTY for BOTH
`shut_neighbor` AND `remove_network` tasks: removing `network 10.0.0.X/32` stops
the BGP *origination*, but the static route to that loopback (admin-distance 1)
keeps the prefix in the main RIB, so it never disappears. The real loss from
`remove_network` is a **BGP-RIB-BEST withdrawal** — visible only to the D9 term
(`bgp_withdrawn`) of the `ExtendedOracle` when `bgp_watch_prefixes` is set, NOT
to the v0 `prefixes_lost` diff.

> ⚠️ **`remove_network` is a v0-oracle FALSE-QUIET.** The v0 `BatfishOracle`
> has no BGP-RIB / D9 term, so it grades a `remove_network` change as a
> *completely empty* blast radius even though every peer loses the prefix from
> its BGP RIB. **Do NOT grade `remove_network` with the v0 oracle.** Grade
> prefix-withdrawal events through `ExtendedOracle` with `bgp_watch_prefixes`
> set (the `ipc` scenario is the gradeable D9 form). The shipped v0 suite is
> `shut_neighbor`-only for exactly this reason; the regression test
> `tests/unit/test_v0_remove_network_guard.py` pins that invariant.

---

## 8. What goes wrong and how to fix it

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ConnectionRefusedError` on port 9997 | Batfish not running | `docker start batfish` or re-deploy |
| `fileParseStatus` shows `FAILED` rows | FRR config syntax issue | Print the failed rows; check config text in `baseline_square4.py` |
| `sessions_lost` is always empty | Column name mismatch | Print `df.columns.tolist()` in `_established_sessions`; adjust column names |
| `oracle.status == "error"` on all tasks | Import error or network issue | Run isolation test (Step 3) to see the raw traceback |
| Non-deterministic results | Batfish has a known non-determinism bug in some route reflector scenarios | Quarantine those tasks; re-run to confirm; open Batfish GH issue if persistent |
| Very slow (>60 sec/task) | Batfish container needs more RAM | Give Docker container ≥8 GB; check `docker stats batfish` |

---

## 9. After the oracle runs — what's next

Once `netbrace safety validate --suite tasks/safety/v0 --require-oracle` exits 0:

```bash
# Verify the pipeline end-to-end with fake model
netbrace eval fake --suite tasks/safety/v0 --run-id fake_check
cat runs/fake_check/results.csv | head -5
# macro_f1 should be 1.0 for all rows (oracle mode echoes ground truth)

# Run one real model call (human approves spend)
export OPENAI_API_KEY=...
netbrace eval run \
  --suite tasks/safety/v0 \
  --model openai/gpt-4o \
  --limit 1 \
  --run-id smoke_gpt4o

# Report
netbrace report --run runs/smoke_gpt4o --figures paper/figures
open paper/figures/safety_f1_by_intent.pdf
```
