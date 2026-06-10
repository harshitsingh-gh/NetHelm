# Batfish — Verified Facts, Column Names, and Known Limitations

## What Batfish Is
Batfish is an open-source network configuration analysis tool. It builds a complete model of a network from configuration files (without a running network), then answers questions about routing, reachability, and correctness. It uses the pybatfish Python client to interact with a running Batfish server.

## Docker Setup (NetHELM)
```
docker run -d --name batfish -p 9996:9996 -p 9997:9997 batfish/allinone:netbrace
```
Ports: 9996 (gRPC questions), 9997 (HTTP status/UI).

## Key pybatfish API

### Session + Snapshot
```python
from pybatfish.client.session import Session
bf = Session(host="localhost")
bf.set_network("my_network")
bf.init_snapshot("/path/to/snapshot_dir", name="snap1", overwrite=True)
```
Snapshot directory must contain a `configs/` subdirectory with router config files.

### bgpSessionStatus Question
Returns all BGP sessions and their status.
```python
from pybatfish.question import bfq
result = bfq.bgpSessionStatus().answer(snapshot="snap1").frame()
```
**Verified column names (FRR/IOS):**
- `Node` — local router name
- `VRF` — VRF name (usually "default")
- `Local_AS` — local AS number
- `Remote_AS` — remote AS number
- `Local_IP` — local BGP source IP
- `Remote_IP` — remote peer IP
- `Session_Type` — "IBGP" | "EBGP_SINGLEHOP" | "EBGP_MULTIHOP"
- `Established_Status` — "ESTABLISHED" | "NOT_ESTABLISHED" | "UNIQUE_MATCH"

**Filter for established sessions:**
```python
established = result[result["Established_Status"] == "ESTABLISHED"]
```

### bgpRib Question
Returns BGP RIB entries.
```python
result = bfq.bgpRib().answer(snapshot="snap1").frame()
```
Columns: `Node`, `VRF`, `Network` (prefix), `Next_Hop_IP`, `Next_Hop_Interface`, `Origin_Protocol`, `Local_Pref`, `MED`, `Communities`, `AS_Path`, `Status`.

### routes Question
Returns the RIB (all protocols).
```python
result = bfq.routes().answer(snapshot="snap1").frame()
```
Columns: `Node`, `VRF`, `Network`, `Next_Hop_IP`, `Next_Hop_Interface`, `Protocol`, `Metric`, `Admin_Distance`, `Tag`.

### traceroute Question
Simulates packet forwarding from a source.
```python
from pybatfish.datamodel.flow import HeaderConstraints
result = bfq.traceroute(
    startLocation="@enter(r1[eth0])",
    headers=HeaderConstraints(srcIps="10.0.0.1", dstIps="192.168.1.0/24")
).answer(snapshot="snap1").frame()
```
**Disposition values (verified):**
- `ACCEPTED` — packet delivered to destination
- `DENIED_IN` — inbound ACL/policy denied
- `DENIED_OUT` — outbound ACL/policy denied
- `NO_ROUTE` — routing table lookup failed (black hole)
- `LOOP` — routing loop detected
- `INSUFFICIENT_INFO` — Batfish lacks info to determine outcome
- `EXITS_NETWORK` — packet exits the modeled network (expected for egress)
- `NEIGHBOR_UNREACHABLE` — next-hop unreachable at L2/L3

### reachability Question
Tests if packets can flow between endpoints.
```python
result = bfq.reachability(
    pathConstraints=PathConstraints(startLocation="r1"),
    headers=HeaderConstraints(srcIps="10.0.0.1", dstIps="10.0.0.2"),
    actions=["ACCEPTED"]
).answer(snapshot="snap1").frame()
```

### differentialReachability (snapshot pairs)
Compares reachability between two snapshots.
```python
bf.set_network("my_network")
result = bfq.differentialReachability(
    pathConstraints=PathConstraints(startLocation="/.*/ "),
    headers=HeaderConstraints(dstIps="0.0.0.0/0"),
    actions=["ACCEPTED"]
).answer(snapshot="post", reference_snapshot="pre").frame()
```

### searchFilters
Tests ACL/prefix-list behavior.
```python
result = bfq.searchFilters(
    filters="acl_name",
    action="permit",
    headers=HeaderConstraints(srcIps="10.0.0.0/8")
).answer(snapshot="snap1").frame()
```

## FRR-Specific Limitations (Verified in Lab)

### ACL / Prefix-list Parsing
**KNOWN LIMITATION**: Batfish does NOT model FRR-style `access-list` statements for BGP filtering. FRR uses a different ACL format from IOS. Symptoms:
- `searchFilters` returns empty or incorrect results for FRR ACLs
- BGP route filtering via FRR access-lists is not reflected in Batfish bgpRib

**Workaround**: Use `ip prefix-list` in FRR configs (IOS-style prefix-lists ARE parsed by Batfish). Alternatively, test filter dimension (D6) against IOS/Arista configs.

### FRR Route Maps
Route maps with `match ip address prefix-list` work. Route maps with `match ip address access-list` may not parse correctly.

### Supported Config Formats
Batfish parses: Cisco IOS, Cisco IOS-XE, Cisco IOS-XR, Cisco NX-OS, Arista EOS, Juniper JunOS, Palo Alto PAN-OS, iptables, AWS VPC, Azure/GCP (limited), FRR (partial — see limitations above).

## Snapshot Directory Structure
```
snapshot_dir/
├── configs/
│   ├── r1.cfg   ← router config file (one per device)
│   ├── r2.cfg
│   └── ...
└── batfish/     ← optional: layer 1 topology, runtime data
    └── layer1_topology.json
```

## Layer 1 Topology (optional)
Required for correct link modeling on some topologies:
```json
{
  "edges": [
    {"node1": {"hostname": "r1", "interfaceName": "eth0"},
     "node2": {"hostname": "r2", "interfaceName": "eth0"}}
  ]
}
```

## Multi-Snapshot Workflow (Pre/Post Diff)
```python
bf.init_snapshot(pre_dir, name="pre")
bf.init_snapshot(post_dir, name="post")
# Question answered against "post", compared with "pre":
result = bfq.bgpSessionStatus().answer(snapshot="post", reference_snapshot="pre").frame()
```
For differential questions, only use questions that support the `reference_snapshot` parameter. bgpSessionStatus does NOT natively diff — use two separate `.answer()` calls and diff in Python.

## ExtendedOracle (NetHELM Custom)
Location: `oracle/extended.py`
`ExtendedOracle.compute(pre_dir, post_dir)` returns a dict with keys:
- `d1_sessions`: {"lost": [...], "gained": [...]}
- `d2_prefixes`: {"lost": [...], "gained": [...]}
- `d3_reachability`: {"lost": [...], "gained": [...]}
- `d4_waypoint`: {"violations": [...]}
- `d5_redundancy`: {"degraded": [...]}
- `d7_forwarding`: {"changed": [...]}
- `d6_filter`: not yet implemented (schema-only)
- `d8_scale`: not yet implemented (schema-only)

## Common Errors and Fixes
- `java.lang.OutOfMemoryError`: increase Docker memory (`--memory 8g`); large topologies need >4GB
- `BatfishException: No snapshot`: call `bf.init_snapshot()` before any question
- `KeyError: 'Established_Status'`: column name is case-sensitive; always check `.columns` first
- `Empty DataFrame`: snapshot parsed correctly but no sessions/routes exist; verify config syntax
- Model not started: `docker ps` to check; restart with `docker start batfish`
