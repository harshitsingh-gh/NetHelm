# 3-Day Lab Catch-Up Plan — Wed May 27 → Fri May 29, 2026

> **Context:** Phase 0 Week 1 (lab stand-up). Memorial Day's FRR-square +
> iBGP is up and verified ([harness/lab/frr_square/verify_2026-05-25.txt](../harness/lab/frr_square/verify_2026-05-25.txt)).
> **Skipped:** Tue May 26 Batfish slot.
> **Target:** complete *all* Phase 0 Week 1 lab deliverables (Batfish, cEOS,
> cRPD, junos-mcp-server smoketest) in 3 days so Sat/Sun can revert to
> reading + paper outline per the execution plan. NetConfEval (Phase 1
> Week 2) gets a head-start.
> **Host:** `hungrykirby` (Ubuntu 24.x kernel 7.0.0-15-generic, 96 GB RAM,
> 2 TB disk, x86_64). Repo at `~/projects/NetBrace`. Containerlab 0.75.0,
> Docker 29.5.2 already installed.
> **Time budget:** ~6 hr/day × 3 = 18 hr. Treat this as a sprint week.

---

## Day 1 — Wed May 27 (today) — Batfish + NetConfEval clone

### Goals
1. Batfish container running, persisting under `~/batfish-data`.
2. pybatfish in a venv, parsing the `frr_square` configs, one real query
   returning expected route data.
3. NetConfEval repo cloned + env built (no API calls yet).
4. `harness/grader_notes/batfish_setup.md` and
   `runs/2026-05-27_batfish_frrsq/` populated.

### Step-by-step

**[30 min] Pre-flight on the host**
```bash
cd ~/projects/NetBrace
git pull
docker info | head -20            # confirm daemon healthy
df -h /var/lib/docker             # confirm > 50 GB free for images
containerlab inspect -a           # confirm frrsq is still up
```
If `frrsq` is **not** running:
```bash
cd ~/projects/NetBrace/harness/lab
sudo containerlab deploy -t frr_square.clab.yml
```

**[45 min] Pull and start Batfish (allinone image)**
> The `batfish/allinone` image bundles Batfish service + example Jupyter
> notebooks. It's the upstream-recommended starting point
> (https://pybatfish.readthedocs.io/en/latest/getting_started.html). On a
> 96 GB box you don't need `--memory` caps. Pin to a known good tag (Jul
> 2025) so a future `latest` re-pull doesn't break repro.

```bash
docker pull batfish/allinone:2025.07.07
docker tag  batfish/allinone:2025.07.07 batfish/allinone:netbrace

# Persistent volume so snapshots survive container restarts.
docker volume create batfish-data

docker run -d \
  --name batfish \
  --restart unless-stopped \
  -v batfish-data:/data \
  -p 127.0.0.1:8888:8888 \
  -p 127.0.0.1:9996:9996 \
  -p 127.0.0.1:9997:9997 \
  batfish/allinone:netbrace

# Confirm it's up.
docker logs --tail 30 batfish
ss -tlnp | grep -E '8888|9996|9997'
```
**Sanity:** `curl -sf http://127.0.0.1:9996/` should return JSON or 404
(not connection refused) within ~30 s of `docker run`.

**[30 min] Python venv + pybatfish**
```bash
sudo apt-get update
sudo apt-get install -y python3.12-venv python3-pip git build-essential

mkdir -p ~/projects/NetBrace/harness/venvs
python3 -m venv ~/projects/NetBrace/harness/venvs/batfish
source ~/projects/NetBrace/harness/venvs/batfish/bin/activate
pip install --upgrade pip wheel
pip install --upgrade pybatfish pandas jupyterlab matplotlib
pip freeze > ~/projects/NetBrace/harness/venvs/batfish-requirements.txt
```
Pin a requirements file so summer-you can recreate. Commit
`harness/venvs/batfish-requirements.txt` (the `venvs/` directory itself
should be `.gitignore`d).

**[45 min] Package the `frr_square` configs as a Batfish snapshot**

Batfish wants a snapshot directory layout. For FRR:
```
snapshot/
  configs/
    r1.conf    # contents of harness/lab/frr_square/configs/r1/frr.conf
    r2.conf
    r3.conf
    r4.conf
  hosts/       # optional
  iptables/    # optional
```
FRR is supported as the `frr` format; per-device file naming = hostname.

```bash
SNAP=~/projects/NetBrace/runs/2026-05-27_batfish_frrsq/snapshot
mkdir -p "$SNAP/configs"
for r in r1 r2 r3 r4; do
  cp ~/projects/NetBrace/harness/lab/frr_square/configs/$r/frr.conf \
     "$SNAP/configs/$r.conf"
done
```
> **Important:** Batfish parses FRR by sniffing the `frr version` line at
> the top of the file. Your r1.conf already has `frr version 10.6.1_git`
> so this should Just Work. If parse warnings appear, the workaround is
> to prepend `! RANCID-CONTENT-TYPE: frr` as the first line.

**[60 min] Run the first pybatfish query**

Create `runs/2026-05-27_batfish_frrsq/query.py`:
```python
"""First Batfish query against frr_square snapshot.

Validates: snapshot loads, all four nodes are recognized, BGP RIB has the
four /32 loopbacks, eBGP/iBGP topology matches the lab.
"""
from pathlib import Path
import pandas as pd
from pybatfish.client.session import Session

SNAPSHOT_DIR = Path(__file__).parent / "snapshot"
NETWORK = "frrsq"
SNAPSHOT = "v1_2026-05-27"

bf = Session(host="127.0.0.1")
bf.set_network(NETWORK)
bf.init_snapshot(str(SNAPSHOT_DIR), name=SNAPSHOT, overwrite=True)

print("\n== nodes ==")
print(bf.q.nodeProperties().answer().frame()[
    ["Node", "Configuration_Format", "Routing_Protocols"]
])

print("\n== bgp peer config ==")
print(bf.q.bgpPeerConfiguration().answer().frame())

print("\n== bgp session status ==")
print(bf.q.bgpSessionStatus().answer().frame())

print("\n== bgp RIB on r1 ==")
rib = bf.q.bgpRib(nodes="r1").answer().frame()
print(rib[["Node", "VRF", "Network", "Next_Hop_IP", "AS_Path"]])

print("\n== reachability r1 lo -> r3 lo ==")
trace = bf.q.traceroute(
    startLocation="@enter(r1[lo])", headers={"dstIps": "10.0.0.3"}
).answer().frame()
print(trace)
```
Run it:
```bash
cd ~/projects/NetBrace/runs/2026-05-27_batfish_frrsq
python query.py | tee query_output.txt 2>&1
```
**Pass criteria (write these into the README):**
- `nodeProperties()` shows 4 rows, all with `Configuration_Format == FRR`.
- `bgpSessionStatus()` shows 12 rows (4 × 3) all `ESTABLISHED`.
- `bgpRib(r1)` contains networks `10.0.0.1/32` through `10.0.0.4/32`.
- `traceroute` from r1.lo to 10.0.0.3 succeeds.

**[30 min] Document and commit**

Write `harness/grader_notes/batfish_setup.md` covering:
- Container image + tag pinned.
- Snapshot directory layout for FRR.
- The four pass-criteria above as a smoke-test contract.
- Known issue: Batfish doesn't simulate FRR's BGP add-path / next-hop
  rewrite identically to FRR — flag for Week 6 Cornetto grader work.

Commit message:
```
lab(batfish): install + first frrsq snapshot, baseline pybatfish query green
```

**[60 min] NetConfEval head-start (foundation only, no API calls)**

This bleeds into Phase 1 Week 2 work, but it removes the highest-risk
unknown (does the upstream repo still install cleanly?) early.

```bash
mkdir -p ~/projects/NetBrace/external
cd ~/projects/NetBrace/external
git clone https://github.com/RedHatResearch/conext24-NetConfEval.git netconfeval
cd netconfeval
git log -1 --format='%H %ci'   # record the pinned commit in your notes

python3 -m venv ~/projects/NetBrace/harness/venvs/netconfeval
source ~/projects/NetBrace/harness/venvs/netconfeval/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt
pip freeze > ~/projects/NetBrace/harness/venvs/netconfeval-requirements.txt

# Confirm HF dataset can be reached (no download yet, just resolve).
python - <<'PY'
from huggingface_hub import HfApi
print(HfApi().dataset_info("NetConfEval/NetConfEval").id)
PY
```
Stop here. Step-1 / step-2 runs go in Day 3.

**Day 1 deliverables checklist**
- [ ] `docker ps` shows `batfish` running.
- [ ] `harness/venvs/batfish-requirements.txt` committed.
- [ ] `runs/2026-05-27_batfish_frrsq/{query.py,query_output.txt}` committed.
- [ ] `harness/grader_notes/batfish_setup.md` committed.
- [ ] `external/netconfeval` cloned, venv built, pinned commit recorded.
- [ ] One-line entry added to [progress.md](../progress.md).

---

## Day 2 — Thu May 28 — Arista cEOS + DNM ticket re-ping

### Goals
1. cEOS-lab image downloaded, imported into Docker.
2. `frrsq` topology cloned to `frrsq_mixed` with one cEOS node added.
3. cEOS reachable, advertises a /32 into the existing iBGP mesh.
4. Re-verify Batfish parses the mixed-vendor snapshot.
5. Cisco DNM data-release legal ticket re-pinged.

### Step-by-step

**[60 min] Get the cEOS image (this is the gating step)**
> Arista requires a registered arista.com account. Get one *now* — first-
> time registration approval can take a few hours and that's the only
> blocker. Use your Cisco corporate email (you have a relationship via
> day-job).

1. Go to https://www.arista.com/en/support/software-download
2. Log in. Navigate to **EOS > cEOS-lab**.
3. Download the **latest 4.34.x cEOS64-lab** archive (file looks like
   `cEOS64-lab-4.34.0F.tar.xz`). 4.32.0F+ is the cutoff for cgroups-v2
   auto-detect (Ubuntu 24 uses v2 unified), so anything ≥4.32 is safe.
   4.34 is the current branch.
4. SHA512 is shown on the download page — verify after transfer.

```bash
# Transfer to the host via scp / browser download / corp share, then:
cd ~/downloads
sha512sum cEOS64-lab-4.34.0F.tar.xz   # compare with Arista's value

docker import cEOS64-lab-4.34.0F.tar.xz ceos:4.34.0F
docker images ceos
```

**[15 min] Sanity-boot cEOS standalone**
```bash
mkdir -p /tmp/ceos-boot && cd /tmp/ceos-boot
cat > boot.clab.yml <<'YAML'
name: ceosboot
topology:
  nodes:
    ceos1:
      kind: arista_ceos
      image: ceos:4.34.0F
YAML
sudo containerlab deploy -t boot.clab.yml
sudo containerlab inspect -t boot.clab.yml
# cEOS takes ~60–120s to fully boot. Then:
docker exec -it clab-ceosboot-ceos1 Cli -p '' -c 'show version'
sudo containerlab destroy -t boot.clab.yml --cleanup
```
You should see `Arista vEOS` / `cEOSLab` and version 4.34.0F.

**[60 min] Build the mixed-vendor topology**

We *clone* `frr_square` rather than mutate it, because the verified FRR
snapshot is your baseline-of-record for Batfish reproducibility tests.

```bash
cd ~/projects/NetBrace/harness/lab
mkdir -p frr_square_mixed/configs/ceos1
cp -r frr_square/configs/r1 frr_square_mixed/configs/
cp -r frr_square/configs/r2 frr_square_mixed/configs/
cp -r frr_square/configs/r3 frr_square_mixed/configs/
# drop r4, replace with ceos1
```

Create `harness/lab/frr_square_mixed.clab.yml`:
```yaml
name: frrsqm

topology:
  defaults:
    kind: linux

  kinds:
    linux:
      image: quay.io/frrouting/frr:10.6.1
    arista_ceos:
      image: ceos:4.34.0F

  nodes:
    r1:
      binds:
        - /home/harshitsingh/projects/NetBrace/harness/lab/frr_square_mixed/configs/r1/daemons:/etc/frr/daemons
        - /home/harshitsingh/projects/NetBrace/harness/lab/frr_square_mixed/configs/r1/frr.conf:/etc/frr/frr.conf
    r2:
      binds:
        - /home/harshitsingh/projects/NetBrace/harness/lab/frr_square_mixed/configs/r2/daemons:/etc/frr/daemons
        - /home/harshitsingh/projects/NetBrace/harness/lab/frr_square_mixed/configs/r2/frr.conf:/etc/frr/frr.conf
    r3:
      binds:
        - /home/harshitsingh/projects/NetBrace/harness/lab/frr_square_mixed/configs/r3/daemons:/etc/frr/daemons
        - /home/harshitsingh/projects/NetBrace/harness/lab/frr_square_mixed/configs/r3/frr.conf:/etc/frr/frr.conf
    ceos1:
      kind: arista_ceos
      startup-config: frr_square_mixed/configs/ceos1/startup.cfg

  links:
    - endpoints: ["r1:eth1", "r2:eth1"]
    - endpoints: ["r1:eth2", "r3:eth1"]
    - endpoints: ["r1:eth3", "ceos1:eth1"]
    - endpoints: ["r2:eth2", "r3:eth2"]
    - endpoints: ["r2:eth3", "ceos1:eth2"]
    - endpoints: ["r3:eth3", "ceos1:eth3"]
```

Create `harness/lab/frr_square_mixed/configs/ceos1/startup.cfg` (full-mesh
iBGP, ASN 65000, loopback 10.0.0.4/32, matches the existing FRR
addressing plan):
```
hostname ceos1
!
interface Loopback0
   ip address 10.0.0.4/32
!
interface Ethernet1
   no switchport
   ip address 192.0.2.10/30
!
interface Ethernet2
   no switchport
   ip address 192.0.2.6/30
!
interface Ethernet3
   no switchport
   ip address 192.0.2.11/30
!
ip routing
!
ip route 10.0.0.1/32 192.0.2.9
ip route 10.0.0.2/32 192.0.2.5
ip route 10.0.0.3/32 192.0.2.10
!
router bgp 65000
   router-id 10.0.0.4
   no bgp default ipv4-unicast
   neighbor 10.0.0.1 remote-as 65000
   neighbor 10.0.0.1 update-source Loopback0
   neighbor 10.0.0.2 remote-as 65000
   neighbor 10.0.0.2 update-source Loopback0
   neighbor 10.0.0.3 remote-as 65000
   neighbor 10.0.0.3 update-source Loopback0
   !
   address-family ipv4
      neighbor 10.0.0.1 activate
      neighbor 10.0.0.1 next-hop-self
      neighbor 10.0.0.2 activate
      neighbor 10.0.0.2 next-hop-self
      neighbor 10.0.0.3 activate
      neighbor 10.0.0.3 next-hop-self
      network 10.0.0.4/32
!
end
```
> **Important:** the existing FRR r1/r2/r3 configs reference neighbor
> `10.0.0.4` — that role is now cEOS, which keeps the iBGP mesh
> definition unchanged. The point-to-point /30s on the cEOS↔FRR links
> in the cEOS config must match what's already in the FRR configs:
>   - r1:eth3 ↔ ceos1:eth1 → 192.0.2.9/30 ↔ 192.0.2.10/30 ✅
>   - r2:eth3 ↔ ceos1:eth2 → 192.0.2.5/30 ↔ 192.0.2.6/30 — **conflict
>     with r3:eth1**. Re-pull `verify_2026-05-25.txt` and re-derive the
>     /30 allocation before pasting; the cleanest fix is to bump the
>     `r2:eth3 ↔ ceos1:eth2` link to a new subnet `192.0.2.12/30` and
>     update r2.conf accordingly.

> **Strong recommendation:** before editing, run
> ```
> grep -nE 'ip address|ip route' harness/lab/frr_square_mixed/configs/*/frr.conf
> ```
> and write the full subnet plan into
> `harness/lab/frr_square_mixed/IP_PLAN.md` *before* deploying. 10 minutes
> here saves 2 hours of debugging stuck BGP sessions.

**[45 min] Deploy + verify**
```bash
cd ~/projects/NetBrace/harness/lab
# tear down the original lab first to free interface MACs
sudo containerlab destroy -t frr_square.clab.yml --cleanup
sudo containerlab deploy  -t frr_square_mixed.clab.yml

# wait ~90s for cEOS to fully boot
sleep 90
sudo containerlab inspect -t frr_square_mixed.clab.yml

docker exec clab-frrsqm-ceos1 Cli -p '' -c 'show ip bgp summary'
docker exec clab-frrsqm-r1    vtysh -c 'show ip bgp summary'
```
Capture the output to `harness/lab/frr_square_mixed/verify_2026-05-28.txt`
using the same template as the FRR-only verify file. The four loopbacks
(`10.0.0.1/32`–`10.0.0.4/32`) must appear in every router's BGP RIB.

**[30 min] Re-snapshot in Batfish**
Update `runs/2026-05-27_batfish_frrsq/query.py` (or copy to
`runs/2026-05-28_batfish_frrsqm/`) to consume the new configs, including
the cEOS `startup.cfg`. cEOS uses the `arista` format — Batfish auto-
detects it. The four-pass criteria from Day 1 should still hold; if
`bgpSessionStatus()` shows fewer than 12 ESTABLISHED rows, fix the
config before moving on.

**[15 min] Re-deploy the original FRR-only lab (parallel)**
Don't lose your baseline. The two labs can run side-by-side; they use
different docker network names (`clab-frrsq` vs `clab-frrsqm`).
```bash
cd ~/projects/NetBrace/harness/lab
sudo containerlab deploy -t frr_square.clab.yml
```

**[15 min] DNM legal ticket re-ping**
Per progress.md you flagged this as own action item but the original
filing slipped. Send a short follow-up email today, with subject
prefix `[NetBrace data-release] re-ping`. One sentence: *"Re-flagging the
ticket from May 24 for any update; need a yes/no decision by mid-July
to plan paper §6."*

**Day 2 deliverables checklist**
- [ ] `docker images` shows `ceos:4.34.0F`.
- [ ] `harness/lab/frr_square_mixed.clab.yml` committed.
- [ ] `harness/lab/frr_square_mixed/IP_PLAN.md` + `configs/` committed.
- [ ] `harness/lab/frr_square_mixed/verify_2026-05-28.txt` committed.
- [ ] `runs/2026-05-28_batfish_frrsqm/query_output.txt` committed.
- [ ] DNM ticket re-pinged (note in `progress.md`).

---

## Day 3 — Fri May 29 — Juniper cRPD + junos-mcp-server + NetConfEval step-1

### Goals
1. cRPD image loaded, one cRPD node deployed standalone.
2. `junos-mcp-server` cloned + running, talking to that cRPD over SSH.
3. End-to-end MCP transcript: tool call → cRPD CLI → response back.
4. NetConfEval step-1 runs end-to-end against GPT-4o on one task.

### Step-by-step

**[45 min] Get the cRPD image**
> cRPD requires a free Juniper account at https://support.juniper.net/.
> Image is gated behind a "Junos Routing - cRPD - Container Software" SKU
> entitlement. Trial entitlements are easy to request and approved
> within a day.

1. Log in at https://support.juniper.net/support/downloads/?p=crpd
2. Download the latest `junos-routing-crpd-docker-XX.YR.B.tgz` (as of
   May 2026 the current branch is **24.4R1** — pick the highest 24.x
   release available to you).
3. SHA also published; verify.

```bash
cd ~/downloads
sha256sum junos-routing-crpd-docker-24.4R1.10.tgz
sudo docker load -i junos-routing-crpd-docker-24.4R1.10.tgz
docker images crpd
# expected: REPOSITORY=crpd, TAG=24.4R1.10
```

**[30 min] Stand up a 1-node cRPD lab**

Create `harness/lab/crpd_solo.clab.yml`:
```yaml
name: crpdsolo

topology:
  nodes:
    crpd1:
      kind: juniper_crpd
      image: crpd:24.4R1.10
```
Deploy and verify SSH works:
```bash
cd ~/projects/NetBrace/harness/lab
sudo containerlab deploy -t crpd_solo.clab.yml
sleep 30
sudo containerlab inspect -t crpd_solo.clab.yml
# Note the management IP printed (172.20.20.x)

# Default creds: root / clab123
ssh -o StrictHostKeyChecking=no root@<crpd1-mgmt-ip>
# inside cRPD:
cli
show version
show route
exit
exit
```
Capture `show version` + `show route` output to
`harness/lab/crpd_solo/verify_2026-05-29.txt`.

**[30 min] Switch cRPD to SSH-key auth (required by junos-mcp-server)**
The MCP server's `add_device` tool requires SSH keys; password auth is
disabled there for security. Even for stdio you want this for the
realistic baseline.

```bash
# On the host:
mkdir -p ~/projects/NetBrace/harness/lab/crpd_solo/keys
ssh-keygen -t ed25519 -N '' -C 'netbrace-mcp' \
  -f ~/projects/NetBrace/harness/lab/crpd_solo/keys/id_mcp

# Copy pubkey into cRPD root authorized_keys
PUB=$(cat ~/projects/NetBrace/harness/lab/crpd_solo/keys/id_mcp.pub)
docker exec clab-crpdsolo-crpd1 bash -c \
  "mkdir -p /root/.ssh && echo '$PUB' >> /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys"

# Verify key auth works:
ssh -i ~/projects/NetBrace/harness/lab/crpd_solo/keys/id_mcp \
    -o StrictHostKeyChecking=no \
    root@<crpd1-mgmt-ip> 'cli -c "show version"'
```
**Do not commit** the private key. Add `harness/lab/**/keys/` to `.gitignore`.

**[60 min] Install + run junos-mcp-server**
```bash
cd ~/projects/NetBrace/external
git clone https://github.com/Juniper/junos-mcp-server.git
cd junos-mcp-server
git checkout v1.1.1     # current release per upstream

python3 -m venv ~/projects/NetBrace/harness/venvs/jmcp
source ~/projects/NetBrace/harness/venvs/jmcp/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt
pip freeze > ~/projects/NetBrace/harness/venvs/jmcp-requirements.txt
```

Create `harness/lab/crpd_solo/devices.json` (replace `<IP>` with the
cRPD mgmt IP from `containerlab inspect`):
```json
{
  "crpd1": {
    "ip": "<IP>",
    "port": 22,
    "username": "root",
    "auth": {
      "type": "ssh_key",
      "private_key_path": "/home/harshitsingh/projects/NetBrace/harness/lab/crpd_solo/keys/id_mcp"
    }
  }
}
```

Start MCP with stdio transport (simplest, no auth needed):
```bash
cd ~/projects/NetBrace/external/junos-mcp-server
python jmcp.py -f ~/projects/NetBrace/harness/lab/crpd_solo/devices.json -t stdio
```
This stays foreground and waits for an MCP client to attach over stdio.
Kill with Ctrl-C after the smoketest below.

**[45 min] Drive MCP from a test client (smoketest transcript)**

For Phase 0, the cleanest smoketest is the official `mcp` Python client
talking to the same process via stdio. Open a *new* terminal:

```bash
source ~/projects/NetBrace/harness/venvs/jmcp/bin/activate
pip install mcp
```

Save as `harness/lab/crpd_solo/smoketest.py`:
```python
"""Phase-0 smoketest: drive junos-mcp-server against the cRPD lab.

Exercises three tools: get_router_list, execute_junos_command (show
version), get_junos_config. Writes the full transcript to
verify_mcp_2026-05-29.txt for the paper.
"""
import asyncio, json, os, sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO   = Path.home() / "projects/NetBrace"
JMCP   = REPO / "external/junos-mcp-server/jmcp.py"
DEVS   = REPO / "harness/lab/crpd_solo/devices.json"
OUTPUT = REPO / "harness/lab/crpd_solo/verify_mcp_2026-05-29.txt"

async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(JMCP), "-f", str(DEVS), "-t", "stdio"],
        env={**os.environ},
    )
    transcript = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as sess:
            await sess.initialize()
            tools = await sess.list_tools()
            transcript.append(("tools", [t.name for t in tools.tools]))

            r = await sess.call_tool("get_router_list", {})
            transcript.append(("get_router_list", r.content[0].text))

            r = await sess.call_tool("execute_junos_command",
                {"router_name": "crpd1", "command": "show version"})
            transcript.append(("show version", r.content[0].text))

            r = await sess.call_tool("get_junos_config",
                {"router_name": "crpd1"})
            transcript.append(("get_junos_config", r.content[0].text[:2000]))

    OUTPUT.write_text(json.dumps(transcript, indent=2))
    print(f"wrote {OUTPUT}")

asyncio.run(main())
```
Run with the previous MCP foreground process **stopped** (the smoketest
spawns its own):
```bash
python ~/projects/NetBrace/harness/lab/crpd_solo/smoketest.py
cat ~/projects/NetBrace/harness/lab/crpd_solo/verify_mcp_2026-05-29.txt
```
**Pass criteria:**
- `tools` list includes `execute_junos_command`, `get_junos_config`,
  `get_router_list`, `gather_device_facts`.
- `show version` returns Junos version string.
- `get_junos_config` returns a multi-line Junos config block.

**[60 min] NetConfEval step-1 against GPT-4o (one task, sanity)**
```bash
cd ~/projects/NetBrace/external/netconfeval
source ~/projects/NetBrace/harness/venvs/netconfeval/bin/activate

export OPENAI_API_KEY=...    # your key; do NOT commit
# Inspect what step_1 expects:
python step_1_formal_spec_translation.py --help

# Smallest possible smoke run:
python step_1_formal_spec_translation.py \
    --model gpt-4o \
    --policy_types reachability \
    --batch_size 1 \
    --n_runs 1 \
    --results_path ~/projects/NetBrace/runs/2026-05-29_netconfeval_gpt4o
```
Capture stdout + the `results_path` JSON to
`runs/2026-05-29_netconfeval_gpt4o/`. Estimated cost: < $1 for a single
policy type × 1 run.

**[30 min] Cleanup + write Phase-0 close-out**

Append to `progress.md`:
- Bullet list of everything completed Wed/Thu/Fri.
- Updated blockers (none expected; if cEOS/cRPD account approval blocked
  Day 2/3, list explicitly).
- Confirm Sat/Sun remain on plan (reading: NetPress+NIKA combined,
  HELM methodology; Sun: paper outline + collab targets +
  landscape_table.md).

**Day 3 deliverables checklist**
- [ ] `docker images` shows `crpd:24.4R1.x`.
- [ ] `harness/lab/crpd_solo.clab.yml` + `crpd_solo/devices.json` +
      `verify_2026-05-29.txt` + `verify_mcp_2026-05-29.txt` committed.
- [ ] `external/junos-mcp-server` cloned + pinned, jmcp-requirements.txt
      committed.
- [ ] `harness/lab/crpd_solo/smoketest.py` committed.
- [ ] `runs/2026-05-29_netconfeval_gpt4o/` committed (results JSON only;
      `.gitignore` raw model outputs > 10 MB).
- [ ] `.gitignore` updated for `harness/lab/**/keys/` and `harness/venvs/`.
- [ ] `progress.md` updated with Phase-0 close-out.

---

## Risk register for the sprint

| Risk | Probability | Mitigation |
|---|---|---|
| Arista cEOS account approval slow | Medium | Submit Wed evening; if Thu morning still pending, escalate via Cisco partner contact. Fallback Day 2 work: do the FRR↔FRR Batfish mixed-vendor work with a second FRR distro (Quagga image) and slip cEOS to Sat AM. |
| Juniper cRPD account approval slow | Medium | Same: file Wed evening. Fallback: substitute Nokia SR-Linux container (free, no registration) for the MCP smoketest — *but* you lose Junos-specific MCP coverage, so prefer to wait. |
| Batfish parses FRR configs with warnings | Low | Prepend `! RANCID-CONTENT-TYPE: frr` to each `.conf`. |
| iBGP doesn't establish with cEOS | Medium | Most-likely culprit is /30 collision (see IP_PLAN warning). Second most-likely: cEOS needs `no bgp default ipv4-unicast` + explicit `activate` per address family, which the config above already includes. |
| NetConfEval step-1 OOMs / rate-limits | Low | Stick to `--batch_size 1 --n_runs 1` for the Day-3 sanity. Full sweep is Phase 1 Week 2. |
| junos-mcp-server requires `mcp >= X` mismatch with venv | Low | Pin both the server's release tag and the client's `mcp` version in the requirements file. |

---

## What this plan deliberately *does not* do

- **No Cornetto work.** Stays in Phase 1 Week 3 per execution plan.
- **No safety-axis design.** Phase 1 Week 8.
- **No multi-cEOS / multi-cRPD scaling.** One node of each is enough for
  the Phase-0 baseline; scaling is a Phase 1 problem.
- **No paper writing.** Sun May 31 still owns `paper/outline_v0.md` per
  the execution plan.
- **No reading catch-up on weekdays.** The compressed reading schedule
  (NetPress+NIKA combined, HELM methodology) still runs Thu+Fri *eves*
  per the original plan — but if the lab work overruns, push reading to
  Sat AM and accept that as the only scope cut.
