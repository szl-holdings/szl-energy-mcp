# szl-energy-mcp

**Energy-metering vertical MCP server — receipt-gated.** Every tool result carries its receipt (source URL + sha256 over raw bytes + schema + fetch timestamp). Where no energy measurement exists, the tool says so. It never fabricates joules, watts, or carbon numbers.

From the estate frontier study (2026-11-15, item 8): the Upstage korean-tax-calc-MCP pattern, applied to our vertical — energy metering. MCP + receipts is an empty lane; this is the estate's first vertical MCP.

## Tools

| Tool | Returns | Receipt carried |
|---|---|---|
| `energy_rollup` | Latest fleet energy rollup (szl.energy-attestation/v2): MEASURED joules from fleet NVML sampling, EPA eGRID published-average conversion | sha256 of the fetched rollup JSON |
| `energy_receipt_index` | Live index of `energy/` in [SZLHOLDINGS/frontier-54-runs](https://huggingface.co/datasets/SZLHOLDINGS/frontier-54-runs) | sha256 of the tree-API response |
| `battery_energy_context` | Measured GPU/node/driver/timestamp context from an evaluation-battery receipt (context only — no joules are inferred) | sha256 of the fetched receipt |

## Run

```bash
python server.py            # stdio MCP (JSON-RPC 2.0, newline-delimited)
python server.py --smoke    # one-shot self-test against the live dataset
```

Zero dependencies — Python 3.9+ stdlib only.

## Wire into an MCP client

```json
{"mcpServers": {"szl-energy": {"command": "python", "args": ["/path/to/szl-energy-mcp/server.py"]}}}
```

## Doctrine

- Fail-closed: zero-joule states are reported as-measured, never padded.
- Every result carries its source receipt; absent evidence is labeled absent.
- Honest scope: battery receipts carry hardware context, not energy — the tool says exactly that.
- Pipeline doctrine: GitHub source → deploy → package (PyPI lane follows the proven trusted-publisher pattern).

License: Apache-2.0. Estate: SZL Holdings / a11oy — receipts, not benchmarks.
