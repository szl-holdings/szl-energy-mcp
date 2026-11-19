#!/usr/bin/env python3
"""szl-energy-mcp — energy-metering vertical MCP server (receipt-gated).

Doctrine: every tool result carries its receipt (source URL + sha256 + schema).
Fail-closed: where no energy measurement exists, the tool says so — it never
fabricates joules, watts, or carbon numbers. License: Apache-2.0.

Protocol: Model Context Protocol over stdio (JSON-RPC 2.0, newline-delimited).
Zero external dependencies — Python 3.9+ stdlib only.

Estate assets served:
  - SZLHOLDINGS/frontier-54-runs  energy/  (szl.energy-attestation/v2 rollups)
  - SZLHOLDINGS/frontier-54-runs  benchmark/  (battery receipts; GPU/node context)
"""
import json
import hashlib
import sys
import urllib.request
from datetime import datetime, timezone

DATASET = "https://huggingface.co/datasets/SZLHOLDINGS/frontier-54-runs"
TREE_API = "https://huggingface.co/api/datasets/SZLHOLDINGS/frontier-54-runs/tree/main"
SERVER_VERSION = "0.1.0"
__version__ = SERVER_VERSION
TOOLS_SPEC = [
    {
        "name": "energy_rollup",
        "description": "Latest fleet energy rollup receipt (szl.energy-attestation/v2). MEASURED joules from fleet NVML sampling; honest zero-state is reported as-measured.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "energy_receipt_index",
        "description": "Index of energy receipts published in the estate receipts dataset (energy/ directory).",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "battery_energy_context",
        "description": "Measured GPU/node/driver/timestamp context from an evaluation-battery receipt. Context only — battery receipts do not carry joules; this tool never infers them.",
        "inputSchema": {
            "type": "object",
            "properties": {"model_token": {"type": "string", "description": "case-insensitive substring of the receipt filename, e.g. 'base-baseline'"}},
            "required": ["model_token"],
        },
    },
]


def _receipt(kind, url, sha256, note=None):
    r = {
        "kind": kind,
        "source": url,
        "sha256": sha256,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    if note:
        r["note"] = note
    return r


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "szl-energy-mcp/" + SERVER_VERSION})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def call_energy_rollup():
    url = DATASET + "/resolve/main/energy/fleet-rollup-1.json"
    raw = _fetch(url)
    data = json.loads(raw)
    sha = hashlib.sha256(raw).hexdigest()
    result = {
        "rollup": data,
        "honesty": (
            "Measured_receipts=%d. If total_joules is 0, that is the as-measured state, "
            "not a placeholder. Schema: szl.energy-attestation/v2 (NVML fleet sampling; "
            "EPA eGRID 0.385 kgCO2/kWh published-average conversion only)."
            % data.get("measured_receipts", 0)
        ),
        "receipt": _receipt("szl.energy-attestation/v2", url, sha, "fetched live; sha over raw bytes"),
    }
    return result


def call_energy_receipt_index():
    url = TREE_API + "/energy?limit=200"
    raw = _fetch(url)
    entries = json.loads(raw)
    files = [e.get("path", "").split("/")[-1] for e in entries if e.get("type") == "file"]
    result = {
        "count": len(files),
        "files": files,
        "honesty": "Live index of the public receipts dataset; absent entries are absent, not omitted.",
        "receipt": _receipt("szl.frontier-54-runs/energy-index", url, hashlib.sha256(raw).hexdigest()),
    }
    return result


def call_battery_energy_context(token):
    url = TREE_API + "/benchmark?limit=500"
    raw = _fetch(url)
    entries = json.loads(raw)
    tok = token.lower()
    matches = [e.get("path", "").split("/")[-1] for e in entries if tok in e.get("path", "").lower()]
    if not matches:
        return {
            "matches": [],
            "honesty": "No battery receipt filename matched. Absent = absent.",
            "receipt": _receipt("szl.frontier-54-runs/benchmark-index", url, hashlib.sha256(raw).hexdigest()),
        }
    name = matches[0]
    furl = DATASET + "/resolve/main/benchmark/" + name
    fraw = _fetch(furl)
    data = json.loads(fraw)
    context = {
        "receipt_file": name,
        "kind": data.get("kind"),
        "model": data.get("model"),
        "gpu": data.get("gpu"),
        "node": data.get("node"),
        "driver": data.get("driver"),
        "ts": data.get("ts"),
        "state": data.get("state"),
        "score": data.get("score"),
    }
    return {
        "context": context,
        "honesty": "Battery receipts carry measured hardware context, not joules. No energy number is inferred from this context.",
        "receipt": _receipt("szl.estate-battery", furl, hashlib.sha256(fraw).hexdigest(), "sha over raw receipt bytes"),
        "other_matches": matches[1:5],
    }


def dispatch(name, args):
    if name == "energy_rollup":
        return call_energy_rollup()
    if name == "energy_receipt_index":
        return call_energy_receipt_index()
    if name == "battery_energy_context":
        return call_battery_energy_context(args.get("model_token", ""))
    raise ValueError("unknown tool: " + name)


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main():
    if "--smoke" in sys.argv:
        out = {
            "server": "szl-energy-mcp",
            "version": SERVER_VERSION,
            "energy_rollup": call_energy_rollup()["rollup"]["measured_receipts"],
            "index_count": call_energy_receipt_index()["count"],
            "battery_context_probe": call_battery_energy_context("base-baseline")["context"],
        }
        print(json.dumps(out, indent=1))
        return
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        mid = msg.get("id")
        method = msg.get("method")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "szl-energy-mcp", "version": SERVER_VERSION},
            }})
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS_SPEC}})
        elif method == "tools/call":
            try:
                res = dispatch(msg["params"]["name"], msg["params"].get("arguments", {}))
                send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": json.dumps(res, indent=1)}],
                    "isError": False,
                }})
            except Exception as ex:
                send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": repr(ex), "fail_closed": True})}],
                    "isError": True,
                }})
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": mid, "result": {}})
        else:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}})


if __name__ == "__main__":
    main()
