# szl-energy-mcp

**Energy-metering vertical MCP server — source-checksum receipts, not signer verification.** Each result carries a source URL, SHA-256 of retrieved bytes, schema and fetch time. The public dataset is accessed through a **moving main reference**: neither its issuer nor immutable revision is authenticated here. A zero-row rollup means **NO MEASUREMENT AVAILABLE**, not a measured observation of zero joules. No independent energy, carbon or production claim follows from this interface.

From the estate frontier study (2026-11-15, item 8): the Upstage korean-tax-calc-MCP pattern, applied to our vertical — energy metering. MCP + receipts is an empty lane; this is the estate's first vertical MCP.

## Tools

| Tool | Returns | Receipt carried |
|---|---|---|
| `energy_rollup` | Public fleet rollup declaration (szl.energy-attestation/v2); explicitly NO_MEASUREMENT when measured_receipts=0, without independently verifying NVML or issuer | sha256 of the fetched rollup JSON |
| `energy_receipt_index` | Live index of `energy/` in [SZLHOLDINGS/frontier-54-runs](https://huggingface.co/datasets/SZLHOLDINGS/frontier-54-runs) | sha256 of the tree-API response |
| `battery_energy_context` | Measured GPU/node/driver/timestamp context from an evaluation-battery receipt (context only — no joules are inferred) | sha256 of the fetched receipt |

## Run

```bash
python szl_energy_mcp.py       # stdio MCP (JSON-RPC 2.0, newline-delimited)
python szl_energy_mcp.py --smoke    # one-shot self-test against the live dataset
szl-energy-mcp                   # console entry point after pip install szl-energy-mcp
```

Zero dependencies — Python 3.9+ stdlib only.

## Wire into an MCP client

```json
{"mcpServers": {"szl-energy": {"command": "python", "args": ["/path/to/szl-energy-mcp/szl_energy_mcp.py"]}}}
```

## Doctrine

- Fail-closed: zero **source receipts** mean `NO_MEASUREMENT_RECEIPTS_OBSERVED`; zero source total is not evidence of measured zero consumption.
- Each response has a source checksum with `issuer_signature_verified=false` and `source_revision_verified=false`; local hashing is not signature or publisher proof.
- Honest scope: battery receipts carry hardware context, not energy; index responses at configured pagination caps fail closed rather than claiming global absence.
- Pipeline doctrine: GitHub source → deploy → package (PyPI lane follows the proven trusted-publisher pattern).

License: Apache-2.0. Estate: SZL Holdings / a11oy — receipts, not benchmarks.

## Input and source boundaries

MCP request lines are bounded to 16,384 characters and duplicate JSON keys or
non-finite literals are rejected. Remote JSON reads are capped at 1 MiB per
request and all output errors use fixed safe reason codes rather than reflecting
remote exception text or caller data. Energy listings stop before the 200-item
cap and battery listings before 500; reaching a cap returns UNAVAILABLE, not
an incomplete catalog disguised as authoritative. Revisions remain unpinned:
this protects the demo's honesty, **not** its source authenticity.

The new GitHub CI workflow runs offline deterministic request/receipt tests on
Python 3.9 and 3.12. These tests do not establish that a Cloudflare MCP route,
Hugging Face dataset signer, NVML sampler, carbon calculation or deployment is
operational. No provider writes or training are part of this repository.
