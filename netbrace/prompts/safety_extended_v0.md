# NetBrace Safety Axis — Extended (8-Dimension) Prompt Template (`safety_extended_v0`)

## SYSTEM CONTRACT

You are a network engineer expert. Predict the **blast radius** of a proposed
configuration change applied to an already-converged network — across EIGHT
dimensions, not just lost BGP sessions. A change can be harmful even when no
session drops and every destination stays reachable (e.g. it reroutes traffic
off a mandatory inspection node, halves redundant paths, flips a firewall rule,
or creates a silent blackhole).

**Output contract** — END your reply with ONE final ```json block with these keys
(use an empty list `[]` for any dimension the change does not affect):

```json
{
  "sessions_lost":      [{"node": "<r>", "peer_ip": "<IP>", "vrf": "default"}],
  "prefixes_lost":      [{"node": "<r>", "prefix": "<CIDR>", "vrf": "default"}],
  "reachability_lost":  [{"src_node": "<r>", "dst_prefix": "<CIDR>", "vrf": "default"}],
  "waypoint_violations":[{"src_node": "<r>", "dst_prefix": "<CIDR>", "waypoint": "<r>", "vrf": "default"}],
  "redundancy_losses":  [{"node": "<r>", "dst_prefix": "<CIDR>", "before_paths": <int>, "after_paths": <int>}],
  "forwarding_anomalies":[{"node": "<r>", "dst_prefix": "<CIDR>", "kind": "blackhole|null_routed|loop", "vrf": "default"}],
  "scale_violations":   [{"node": "<r>", "resource": "fib|rib", "limit": <int>, "observed": <int>}],
  "bgp_withdrawals":    [{"node": "<r>", "network": "<CIDR>", "vrf": "default"}],
  "intent_violations":  [{"kind": "reachability|waypoint|isolation|redundancy_floor|te_pin", "src": "<r|null>", "dst": "<CIDR|r>"}]
}
```

Dimension definitions:
- **sessions_lost** — BGP/IGP adjacencies that go down.
- **prefixes_lost** — routes that disappear from a node's RIB/FIB.
- **reachability_lost** — (src, dst) pairs that can no longer deliver traffic.
- **waypoint_violations** — a flow that MUST transit `waypoint` no longer does
  (traffic bypasses a required inspection/steering node), even if still reachable.
- **redundancy_losses** — an (node, prefix) whose number of equal-cost/redundant
  paths decreased (capacity/resilience cut) without losing reachability.
- **forwarding_anomalies** — traffic silently dropped (`blackhole` = no route,
  `null_routed`, `loop`), localized to the dropping node.
- **scale_violations** — a device's installed-route count exceeds its `fib`/`rib`
  budget after the change.
- **bgp_withdrawals** — a prefix withdrawn from a node's BGP RIB (the advertised
  route is gone) even if a static/IGP backup keeps it reachable.
- **intent_violations** — a stated POLICY INTENT that held before the change is
  broken after it, EVEN WHEN coarse reachability survives. Derive these from the
  "Intents the network must satisfy" prose: e.g. a traffic-engineering / multihoming
  more-specific (`te_pin`) is withdrawn so traffic falls back onto a covering
  aggregate; a mandated transit node (`waypoint`); a required isolation/segmentation
  (`isolation`); or a minimum redundant-path floor (`redundancy_floor`). Report the
  intent that no longer holds — a change can keep every destination pingable yet
  still violate the intent those specifics/paths served.

(Note: an ACL/filter dimension is intentionally out of scope for this version.)

Example of the exact required shape (an empty skeleton — NOT an answer; a change
with no effect on a dimension keeps that list empty):

```json
{
  "sessions_lost": [],
  "prefixes_lost": [],
  "reachability_lost": [],
  "waypoint_violations": [],
  "redundancy_losses": [],
  "forwarding_anomalies": [],
  "scale_violations": [],
  "bgp_withdrawals": [],
  "intent_violations": []
}
```

Scope: "blast radius" here means the **static, steady-state** difference between the
pre-change and post-change *converged* network — what the RIB/FIB/forwarding looks
like after everything settles. Convergence transients (microloops, timing, flap
dynamics) are out of scope.

Rules:
- Use only node names / prefixes that appear in the topology or config below.
- `kind` and `resource` MUST be one of the listed values.
- Reason however you like BEFORE the final ```json block, but the LAST fenced
  json block in your reply must be exactly the contract object — only it is scored.

---

## TASK TEMPLATE

### Topology: `{{ topology.name }}`

Nodes: {{ topology.nodes | join(', ') }}
Routing protocols: {{ topology.routing_protocols | join(', ') }}

{% if intents %}### Intents the network must satisfy
{{ intents }}
{% endif %}

### Baseline configuration

{% for node, config in baseline.configs.items() | sort %}
#### {{ node }}
```
{{ config }}
```
{% endfor %}

### Proposed change

{{ change.description }}

**Unified diff** (applies to the baseline above):
```diff
{{ change.patch }}
```

Watched prefixes (only these matter for prefix/reachability scoring):
{{ watched_prefixes | join(', ') }}

---

**Question:** Across all eight dimensions, what is the blast radius of this change?

Fill every field precisely; use `[]` for any dimension the change does not affect.
