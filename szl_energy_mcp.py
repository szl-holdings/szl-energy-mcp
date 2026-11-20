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
import math
import re
import sys
import urllib.request
from datetime import datetime, timezone

DATASET = "https://huggingface.co/datasets/SZLHOLDINGS/frontier-54-runs"
TREE_API = "https://huggingface.co/api/datasets/SZLHOLDINGS/frontier-54-runs/tree/main"
SERVER_VERSION = "0.1.0"
__version__ = SERVER_VERSION
MAX_SOURCE_BYTES = 1_048_576
MAX_INPUT_LINE_CHARS = 16_384
ENERGY_LIST_LIMIT = 200
BATTERY_LIST_LIMIT = 500
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")


class Unavailable(ValueError):
    """Fixed non-secret denial, never caller-controlled message text."""


def _unique_pairs(pairs):
    value = {}
    for key, content in pairs:
        if key in value:
            raise Unavailable("DUPLICATE_JSON_KEY")
        value[key] = content
    return value


def _no_nonfinite(_):
    raise Unavailable("NONFINITE_JSON")


def _validated_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique_pairs,
                          parse_constant=_no_nonfinite)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise Unavailable("SOURCE_JSON_INVALID") from exc


def _validated_tree(raw, prefix, limit):
    entries = _validated_json(raw)
    if not isinstance(entries, list) or len(entries) >= limit:
        raise Unavailable("INDEX_COVERAGE_UNAVAILABLE")
    names = []
    for item in entries:
        if not isinstance(item, dict):
            raise Unavailable("INDEX_ITEM_INVALID")
        path = item.get("path")
        if not isinstance(path, str) or not path.startswith(prefix):
            raise Unavailable("INDEX_PATH_INVALID")
        if item.get("type") == "file":
            name = path[len(prefix):]
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", name):
                raise Unavailable("INDEX_FILE_INVALID")
            names.append(name)
    if len(names) != len(set(names)):
        raise Unavailable("INDEX_DUPLICATE_FILE")
    return names
TOOLS_SPEC = [
    {
        "name": "energy_rollup",
        "description": "Fleet rollup source (szl.energy-attestation/v2). Zero source receipts mean NO MEASUREMENT; fetched checksum does not verify the issuer.",
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
        "integrity": "LOCAL_FETCH_CHECKSUM_ONLY",
        "issuer_signature_verified": False,
        "source_revision_verified": False,
        "source_reference": "MOVING_MAIN_UNPINNED",
    }
    if note:
        r["note"] = note
    return r


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "szl-energy-mcp/" + SERVER_VERSION})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise Unavailable("SOURCE_BYTE_BUDGET")
    return raw


def call_energy_rollup():
    url = DATASET + "/resolve/main/energy/fleet-rollup-1.json"
    raw = _fetch(url)
    data = _validated_json(raw)
    if not isinstance(data, dict) or data.get("schema") != "szl.energy-attestation/v2":
        raise Unavailable("ROLLUP_SCHEMA_INVALID")
    count = data.get("measured_receipts")
    total = data.get("total_joules")
    if type(count) is not int or count < 0:
        raise Unavailable("ROLLUP_COUNT_INVALID")
    if type(total) not in (int, float) or not math.isfinite(total) or total < 0:
        raise Unavailable("ROLLUP_JOULES_INVALID")
    if count == 0 and total != 0:
        raise Unavailable("ROLLUP_DENOMINATOR_CONTRADICTION")
    sha = hashlib.sha256(raw).hexdigest()
    status = ("NO_MEASUREMENT_RECEIPTS_OBSERVED" if count == 0
              else "SOURCE_DECLARED_MEASUREMENT_UNVERIFIED")
    result = {
        "rollup": data,
        "measurement_state": status,
        "honesty": (
            "measured_receipts=%d; zero receipts means NO MEASUREMENT, not evidence "
            "of a zero-joule observation. This local raw-source hash does not "
            "authenticate the issuer, fleet, NVML sampler or carbon conversion."
            % count
        ),
        "receipt": _receipt("szl.energy-attestation/v2", url, sha,
                            "live moving-main fetch; checksum, NOT signature"),
    }
    return result


def call_energy_receipt_index():
    url = TREE_API + "/energy?limit=200"
    raw = _fetch(url)
    files = _validated_tree(raw, "energy/", ENERGY_LIST_LIMIT)
    result = {
        "count": len(files),
        "files": files,
        "coverage": "COMPLETE_WITHIN_SINGLE_PAGE_ONLY",
        "honesty": "Unpinned public index; source and issuer not independently verified.",
        "receipt": _receipt("szl.frontier-54-runs/energy-index", url, hashlib.sha256(raw).hexdigest()),
    }
    return result


def call_battery_energy_context(token):
    url = TREE_API + "/benchmark?limit=500"
    raw = _fetch(url)
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        raise Unavailable("MODEL_TOKEN_INVALID")
    names = _validated_tree(raw, "benchmark/", BATTERY_LIST_LIMIT)
    tok = token.lower()
    matches = [name for name in names if tok in name.lower()]
    if not matches:
        return {
            "matches": [],
            "honesty": "No battery receipt filename matched. Absent = absent.",
            "receipt": _receipt("szl.frontier-54-runs/benchmark-index", url, hashlib.sha256(raw).hexdigest()),
        }
    name = matches[0]
    furl = DATASET + "/resolve/main/benchmark/" + name
    fraw = _fetch(furl)
    data = _validated_json(fraw)
    if not isinstance(data, dict):
        raise Unavailable("BATTERY_RECEIPT_INVALID")
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
    if not isinstance(args, dict):
        raise Unavailable("ARGUMENTS_NOT_OBJECT")
    if name == "energy_rollup":
        if args:
            raise Unavailable("ARGUMENTS_UNEXPECTED")
        return call_energy_rollup()
    if name == "energy_receipt_index":
        if args:
            raise Unavailable("ARGUMENTS_UNEXPECTED")
        return call_energy_receipt_index()
    if name == "battery_energy_context":
        token = args.get("model_token")
        if set(args) != {"model_token"} or not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
            raise Unavailable("MODEL_TOKEN_INVALID")
        return call_battery_energy_context(token)
    raise Unavailable("TOOL_NOT_FOUND")


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
    while True:
        line = sys.stdin.readline(MAX_INPUT_LINE_CHARS + 1)
        if not line:
            break
        if len(line) > MAX_INPUT_LINE_CHARS:
            # Drain a too-long NDJSON request without growing a second string.
            if not line.endswith("\n"):
                while True:
                    part = sys.stdin.readline(4096)
                    if not part or part.endswith("\n"):
                        break
            send({"jsonrpc": "2.0", "id": None,
                  "error": {"code": -32600, "message": "request too large"}})
            continue
        if not line.strip():
            continue
        try:
            msg = json.loads(line, object_pairs_hook=_unique_pairs,
                             parse_constant=_no_nonfinite)
            if not isinstance(msg, dict):
                raise Unavailable("MESSAGE_NOT_OBJECT")
        except (ValueError, RecursionError):
            send({"jsonrpc": "2.0", "id": None,
                  "error": {"code": -32700, "message": "invalid JSON request"}})
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
                # Exception strings may contain remote URLs, headers, raw data
                # or caller-controlled text; never reflect them in tool output.
                send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": json.dumps({
                        "state": "UNAVAILABLE",
                        "error_code": "SOURCE_OR_INPUT_UNAVAILABLE",
                        "fail_closed": True,
                    })}],
                    "isError": True,
                }})
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": mid, "result": {}})
        else:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}})


if __name__ == "__main__":
    main()
