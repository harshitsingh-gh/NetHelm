# NetBrace Safety Axis — Prompt Template v0 (`safety_direct_v0`)

## SYSTEM CONTRACT

You are a network engineer expert. Your task is to predict the **blast radius** of a
proposed configuration change — that is, which BGP sessions, IP prefixes, and
reachability paths will be **lost** if the change is applied to an already-converged
network.

**Output contract** — return EXACTLY ONE ```json block containing an object with these
four keys and no others:

```json
{
  "sessions_lost":     [{"node": "<router>", "peer_ip": "<IP>", "vrf": "<vrf>"},  ...],
  "prefixes_lost":     [{"node": "<router>", "prefix": "<CIDR/mask>", "vrf": "<vrf>"}, ...],
  "reachability_lost": [{"src_node": "<router>", "dst_prefix": "<CIDR/mask>", "vrf": "<vrf>"}, ...],
  "reasoning": "<free text — explain your analysis here>"
}
```

Rules:
- Use **empty lists `[]`** for any category that is NOT affected by the change.
- Use **only node names and prefixes** that appear in the topology or config below.
  Do not invent names.
- Prefixes must be valid CIDR notation (e.g. `10.0.0.1/32`, `192.168.0.0/24`).
- `vrf` defaults to `"default"` when not otherwise specified.
- Do NOT add any text before or after the ```json block.

---

## TASK TEMPLATE

### Topology: `{{ topology.name }}`

Nodes: {{ topology.nodes | join(', ') }}
Routing protocols: {{ topology.routing_protocols | join(', ') }}

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

Watched prefixes (only these matter for prefix-loss scoring):
{{ watched_prefixes | join(', ') }}

---

**Question:** {{ presentation.operator_question }}

Think step by step in the `"reasoning"` field, then fill the other fields precisely.
