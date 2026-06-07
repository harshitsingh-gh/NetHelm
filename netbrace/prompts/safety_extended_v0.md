# NetBrace Safety Axis — Extended (8-Dimension) Prompt Template (`safety_extended_v0`)

## SYSTEM CONTRACT

You are a network engineer expert. Predict the **blast radius** of a proposed
configuration change applied to an already-converged network — across EIGHT
dimensions, not just lost BGP sessions. A change can be harmful even when no
session drops and every destination stays reachable (e.g. it reroutes traffic
off a mandatory inspection node, halves redundant paths, flips a firewall rule,
or creates a silent blackhole).

**Output contract** — return EXACTLY ONE ```json block with these keys (use an
empty list `[]` for any dimension the change does not affect):

```json
{
  "sessions_lost":      [{"node": "<r>", "peer_ip": "<IP>", "vrf": "default"}],
  "prefixes_lost":      [{"node": "<r>", "prefix": "<CIDR>", "vrf": "default"}],
  "reachability_lost":  [{"src_node": "<r>", "dst_prefix": "<CIDR>", "vrf": "default"}],
  "waypoint_violations":[{"src_node": "<r>", "dst_prefix": "<CIDR>", "waypoint": "<r>", "vrf": "default"}],
  "redundancy_losses":  [{"node": "<r>", "dst_prefix": "<CIDR>", "before_paths": <int>, "after_paths": <int>}],
  "filter_deltas":      [{"node": "<r>", "src_ip": "<IP>", "dst_ip": "<IP>", "protocol": "tcp", "dst_port": <int>, "transition": "permit_to_deny|deny_to_permit"}],
  "forwarding_anomalies":[{"node": "<r>", "dst_prefix": "<CIDR>", "kind": "blackhole|null_routed|loop", "vrf": "default"}],
  "scale_violations":   [{"node": "<r>", "resource": "fib|rib|label|acl_tcam", "limit": <int>, "observed": <int>}],
  "reasoning": "<free text — your analysis>"
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
- **filter_deltas** — a flow whose ACL/filter action flipped. `permit_to_deny` =
  newly blocked; `deny_to_permit` = newly allowed (segmentation leak).
- **forwarding_anomalies** — traffic silently dropped (`blackhole` = no route,
  `null_routed`, `loop`), localized to the dropping node.
- **scale_violations** — a device resource exceeds its limit after the change.

Rules:
- Use only node names / prefixes that appear in the topology or config below.
- `transition`, `kind`, and `resource` MUST be one of the listed values.
- Do NOT add any text before or after the ```json block.

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

Think step by step in the `"reasoning"` field, then fill the other fields precisely.
