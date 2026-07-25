# Graph v1 contract

Looptimal graphs describe how governed loops and explicit human gates compose into one outcome.
They are an operator-facing planning and inspection artifact, not a runtime.

> **The executable contract is
> [`scripts/looptimal-graph.py`](../scripts/looptimal-graph.py).** `looptimal graph validate`
> is the fail-closed structural gate. Graph v1 never executes a node, grants authority, or
> upgrades trust.

Graphs wire the work. Loops keep each node honest. Receipts prove the run.

## What the starter kit does

```bash
looptimal graph starters
looptimal graph init my-graph --starter verified-code-change
looptimal graph validate my-graph
looptimal graph inspect my-graph --json
looptimal graph render my-graph -o my-graph/graph.mmd
```

`init` copies a packaged starter into an empty directory. `validate` checks schema, topology,
authority gates, independent makers/checkers, and trust evidence. `inspect` exposes the ordered
work and human gates. `render` emits Mermaid only after validation is GREEN and refuses to
overwrite an existing output unless `--force` is explicit.

None of these commands run a verifier command found in the manifest. A command is declarative
input for a future authorized runtime.

## Top-level fields

| Field | Required | Contract |
|-|-|-|
| `schema_version` | yes | Integer `1`. |
| `id` | yes | Lowercase kebab-case identifier. |
| `version` | yes | Semantic version `x.y.z`. |
| `name` / `outcome` | yes | Human-readable graph identity and accepted outcome. |
| `trust_tier` | yes | `idea`, `starter`, `runnable`, `verified`, or `receipted`. |
| `execution.mode` | yes | Must be `disabled` in v1. |
| `state.path` | yes | Relative durable-state path; absolute paths and `..` are rejected. |
| `authority.default` | yes | `tier-a`, `H1`, `H2`, or `custom`. |
| `acceptance.verifier` | yes | Graph-level `command`, `reviewer`, or `rubric` verifier. |
| `acceptance.evidence` | yes | Evidence expected before the graph can be accepted. |
| `stop` | yes | `success`, positive `max_transitions`, and positive `wall_clock_minutes`. |
| `nodes` / `edges` | yes | One connected directed acyclic graph with exactly one root. |
| `evidence_refs` | conditional | Required for `verified` and `receipted` trust. |
| `receipt_path` | conditional | Required for `receipted` trust. |

Trust words are claims, not decoration. A starter can be structurally valid without being
runnable. `verified` requires evidence references; `receipted` also requires a relative receipt
path. Validation checks that references are declared, not that the referenced evidence is true.
Evidence verification remains an external checker responsibility.

## Loop nodes

A loop node has `kind: loop`, an immutable `uses` reference such as
`loop://verify-code-change@1.0.0`, and:

- `outcome` and `authority`
- distinct `actors.maker` and `actors.checker`
- `contract.goal`
- relative `contract.state`
- external `contract.verifier`
- `contract.stop.success` and positive `contract.stop.max_iterations`
- one or more expected `evidence` items

The four loop atoms remain local to every node. Node GREEN does not imply graph GREEN; the graph
has its own acceptance verifier and stop condition.

## Human gates and authority

A human gate has `kind: human_gate`, authority `H1`, `H2`, or `custom`, a named `approver`, and
expected evidence. It must have an outgoing `approval` edge.

Any loop node with H1 or H2 authority must receive an inbound `approval` edge from a human gate
with the same authority. Graph structure can preserve approval; it cannot forge or infer it.

## Edges and topology

Edges use `from`, `to`, and `on`, where `on` is `success`, `approval`, or `data`. Validation
rejects unknown nodes, self-edges, duplicate edges, multiple roots, disconnected nodes, and
cycles. The returned order is deterministic.

## Packaged starters

| Starter | Intended adaptation |
|-|-|
| `verified-code-change` | Reproduce, implement, and independently verify a bounded code change. |
| `customer-signal-roadmap` | Collect customer observations, identify a repeated pattern, and produce a checked roadmap proposal. |
| `reviewed-content-publish` | Source claims, draft, simulate audience review, require H1 approval, then represent publication as an H1 node. |

The starter verifier commands and reviewer identities are examples that must be bound to real
local tools and actors before a graph can honestly move beyond `starter`.

## Runtime boundary

A future runtime may consume a validated graph, but it must independently implement work
isolation, idempotency, durable event state, authority enforcement, evidence collection,
receipt verification, retry budgets, cancellation, and recovery. The v1 starter kit makes none
of those runtime claims.
