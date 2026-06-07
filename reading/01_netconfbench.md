# NetConfBench Notes
- Notes an abstracted methodology of testing networking concepts using ANI.
- Frees restrictions from cisco/arista/hp conf
- Higher focus on intent driven dynamic benchmarking instead of static datasets.

## What it evaluates
- MCQ based bencchmarking
- Comparison and eval for LLM's calculation/derivation/reasoning vs defined ground truth on certain "actions/triggers".

## Task categories
1. Scenario category
2. Environment topology
3. Initial device configurations
4. Intent

## Harness / environment
- GNS3 based environment for interacting with vendor images from various builds (cisco/juniper/etc.)
- Uses Agent-Network Interface (ANI) replicating simple "tool" calls / method operations, like get-topology, update-cfg, get-running-cfg, execute-cmd to interact with the virtual/hw routers.

## Agent interface
- Agent simply relies on interaction with 2 things:
    - ANI: As mentioned above, interact with the router here.
    - Task Evaluation Interface: Execute a set of predefined tasks, and capture output configs for all devices, to ensure correctness of the models reasoning/outputs for various tasks.

## Metrics
- **Reasoning Score (S_reasoning)** : Embedding-based cosine similarity between the agent's reasoning trace and the ground truth reasoning. Ranges from 0 to 1.

- **Command Score (S_command)**: Hierarchical diff of final vs. initial router configurations (using Python's ciscoconfparse). Wildcard matching ignores non-essential identifiers (e.g., ACL numbers).

Compute precision = (correctly generated commands / total generated) and recall = (correctly generated / ground truth commands). _S_command_ is the harmonic mean of precision and recall, ranging from 0 to 1.

- **Testcase Score (S_testcase)**:
Portion of testcases passed in the emulated environment.
Fine-grained sub-intents (per device) each correspond to a testcase.
S_testcase is the testcase pass rate, defined as the proportion of passed testcases among all defined testcases.


## What NetBrace should reuse
- Task Assignment
- ANI
- Task Evaluation interface

## What NetBrace should not copy
- Since we have access to real cisco routers, we will use real routers for that part.
-

## How NetBrace differentiates
For now — to be revised after reading up on Cornetto, NetPress, NIKA, and HELM.

1. **Holistic comparison across benchmarks.** Instead of creating another standalone benchmark, NetBrace imports existing benchmarks such as NetConfBench, Cornetto, NIKA, TeleQnA/NetEval, and possibly NetPress-style tasks into one normalized harness. The contribution is the shared scoring surface: same model fleet, same runner, comparable metrics.

2. **Safety / blast-radius axis.** NetBrace adds a new task category: given a proposed network change, predict what BGP sessions, prefixes, interfaces, or services will be lost or degraded. This is not the main focus of NetConfBench. Ground truth can be computed with Batfish, making the category automatically gradeable.

3. **Commercial network-agent baselines.** If access and approval land, NetBrace can include commercial or vendor-specific agents such as Cisco DNM or Juniper `junos-mcp-server`. However, this is not guaranteed and is 100% reliant on how much motion I have in Cisco to get this baby going.

TLDR: NetConfBench asks, “Can an LLM solve these network-configuration tasks?” NetBrace asks, “How do LLMs and network agents compare across the existing task landscape, and can they predict the blast radius of changes?”

## Reproduction questions


[Original Paper](https://www.ietf.org/archive/id/draft-cui-nmrg-llm-benchmark-00.html)