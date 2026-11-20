"""Negative runtime contracts for the public energy MCP (no network or secrets)."""
import hashlib
import io
import json
import unittest
from unittest.mock import patch

import szl_energy_mcp as m


def wire(value):
    return json.dumps(value, sort_keys=True).encode("utf-8")


def rollup(**updates):
    value = {
        "schema": "szl.energy-attestation/v2",
        "measured_receipts": 0,
        "total_joules": 0,
        "timestamp_utc": "2026-11-09T04:47:06Z",
    }
    value.update(updates)
    return wire(value)


def item(prefix, name, kind="file"):
    return {"type": kind, "path": prefix + name}


class EnergyMCPContracts(unittest.TestCase):
    def test_live_shape_with_no_receipts_is_unavailable_not_zero_measured(self):
        raw = rollup()
        with patch.object(m, "_fetch", return_value=raw):
            result = m.call_energy_rollup()
        self.assertEqual(result["measurement_state"], "NO_MEASUREMENT_RECEIPTS_OBSERVED")
        self.assertIn("NO MEASUREMENT", result["honesty"])
        self.assertEqual(result["receipt"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertFalse(result["receipt"]["issuer_signature_verified"])
        self.assertFalse(result["receipt"]["source_revision_verified"])
        self.assertEqual(result["receipt"]["source_reference"], "MOVING_MAIN_UNPINNED")

    def test_positive_source_count_is_not_signer_verified(self):
        with patch.object(m, "_fetch", return_value=rollup(measured_receipts=2, total_joules=50)):
            result = m.call_energy_rollup()
        self.assertEqual(result["measurement_state"], "SOURCE_DECLARED_MEASUREMENT_UNVERIFIED")
        self.assertFalse(result["receipt"]["issuer_signature_verified"])

    def test_malformed_rollups_do_not_issue_measurement_receipts(self):
        cases = [
            rollup(schema="unrecognized"),
            rollup(measured_receipts=True),
            rollup(measured_receipts=-1),
            rollup(measured_receipts=0, total_joules=1),
            rollup(measured_receipts=1, total_joules=-2),
            b'{"schema":"szl.energy-attestation/v2","measured_receipts":0,"total_joules":NaN}',
            b'{"schema":"szl.energy-attestation/v2","measured_receipts":0,"measured_receipts":10,"total_joules":0}',
            b'[]',
        ]
        for payload in cases:
            with self.subTest(payload=payload[:40]), patch.object(m, "_fetch", return_value=payload):
                with self.assertRaises(m.Unavailable):
                    m.call_energy_rollup()

    def test_bounded_network_fetch_refuses_oversize_responses(self):
        fake = io.BytesIO(b"x" * (m.MAX_SOURCE_BYTES + 1))
        with patch.object(m.urllib.request, "urlopen", return_value=fake):
            with self.assertRaisesRegex(m.Unavailable, "SOURCE_BYTE_BUDGET"):
                m._fetch("https://huggingface.co/datasets/SZLHOLDINGS/frontier-54-runs/resolve/main/energy/fleet-rollup-1.json")

    def test_complete_one_page_energy_index_with_no_measured_claim(self):
        payload = wire([item("energy/", "one.json"), item("energy/", "two.json")])
        with patch.object(m, "_fetch", return_value=payload):
            result = m.call_energy_receipt_index()
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["files"], ["one.json", "two.json"])
        self.assertEqual(result["coverage"], "ONE_PAGE_ONLY_GLOBAL_COMPLETENESS_UNVERIFIED")
        self.assertFalse(result["receipt"]["issuer_signature_verified"])

    def test_energy_index_at_page_limit_never_claims_absence(self):
        payload = wire([item("energy/", f"e{n:03}.json") for n in range(m.ENERGY_LIST_LIMIT)])
        with patch.object(m, "_fetch", return_value=payload):
            with self.assertRaisesRegex(m.Unavailable, "INDEX_COVERAGE_UNAVAILABLE"):
                m.call_energy_receipt_index()

    def test_battery_index_at_page_limit_is_unavailable(self):
        payload = wire([item("benchmark/", f"b{n:03}.json") for n in range(m.BATTERY_LIST_LIMIT)])
        with patch.object(m, "_fetch", return_value=payload):
            with self.assertRaisesRegex(m.Unavailable, "INDEX_COVERAGE_UNAVAILABLE"):
                m.call_battery_energy_context("b")

    def test_tree_path_escape_duplicates_and_malformed_results_refused(self):
        inputs = [
            [item("energy/", "../steal.json")],
            [item("energy/", "ok.json"), item("energy/", "ok.json")],
            [item("benchmark/", "wrong.json")],
            [None],
            {"type": "file", "path": "energy/ok.json"},
        ]
        for entries in inputs:
            with self.subTest(entries=entries), patch.object(m, "_fetch", return_value=wire(entries)):
                with self.assertRaises(m.Unavailable):
                    m.call_energy_receipt_index()

    def test_battery_argument_cannot_be_empty_or_path_escape(self):
        for token in ("", "../secret", "a" * 65, 3, True, ["base"]):
            with self.subTest(token=token):
                with self.assertRaises(m.Unavailable):
                    m.dispatch("battery_energy_context", {"model_token": token})
        for args in (None, [], {"unexpected": "x"}):
            with self.subTest(args=args):
                with self.assertRaises(m.Unavailable):
                    m.dispatch("energy_receipt_index", args)

    def test_no_matching_battery_filename_does_not_prove_global_absence(self):
        with patch.object(m, "_fetch", return_value=wire([])):
            result = m.call_battery_energy_context("base")
        self.assertEqual(result["matches"], [])
        self.assertIn("global absence is UNVERIFIED", result["honesty"])
        self.assertFalse(result["receipt"]["issuer_signature_verified"])


    def test_ambiguous_battery_match_refuses_before_receipt_fetch(self):
        # Reorder the tree to prove the selected result is not list-order based.
        for names in (
            ["model-a.json", "model-a-v2.json"],
            ["model-a-v2.json", "model-a.json"],
        ):
            with self.subTest(names=names):
                body = wire([item("benchmark/", name) for name in names])
                with patch.object(m, "_fetch", return_value=body) as fetch:
                    with self.assertRaisesRegex(
                        m.Unavailable, "BATTERY_RECEIPT_AMBIGUOUS"
                    ):
                        m.call_battery_energy_context("model-a")
                self.assertEqual(fetch.call_count, 1)
                self.assertIn("benchmark?limit=500", fetch.call_args[0][0])

    def test_exact_filename_wins_over_substring_regardless_of_tree_order(self):
        receipt = wire({"kind": "evaluation", "gpu": "synthetic"})
        for names in (
            ["old-model-a.json", "model-a.json"],
            ["model-a.json", "old-model-a.json"],
        ):
            with self.subTest(names=names):
                tree = wire([item("benchmark/", name) for name in names])
                with patch.object(m, "_fetch", side_effect=[tree, receipt]) as fetch:
                    result = m.call_battery_energy_context("model-a.json")
                self.assertEqual(fetch.call_count, 2)
                self.assertTrue(
                    fetch.call_args_list[1].args[0].endswith(
                        "/benchmark/model-a.json"
                    )
                )
                self.assertEqual(result["context"]["receipt_file"], "model-a.json")
                self.assertEqual(result["selection_policy"], "EXACT_FILENAME")
                self.assertEqual(result["other_matches"], ["old-model-a.json"])
                self.assertEqual(
                    result["coverage"], "ONE_PAGE_ONLY_GLOBAL_COMPLETENESS_UNVERIFIED"
                )

    def test_unique_substring_selection_is_explicit_not_globally_complete(self):
        tree = wire([item("benchmark/", "study-b.json")])
        receipt = wire({"kind": "evaluation"})
        with patch.object(m, "_fetch", side_effect=[tree, receipt]):
            result = m.call_battery_energy_context("study")
        self.assertEqual(result["selection_policy"], "UNIQUE_SUBSTRING")
        self.assertEqual(result["other_matches"], [])
        self.assertEqual(result["context"]["receipt_file"], "study-b.json")

    def test_battery_context_reports_no_joules(self):
        names = wire([item("benchmark/", "base-baseline.json")])
        receipt = wire({"kind": "evaluation", "gpu": "synthetic", "node": "test", "score": 1})
        with patch.object(m, "_fetch", side_effect=[names, receipt]):
            result = m.call_battery_energy_context("base")
        self.assertIn("not joules", result["honesty"])
        self.assertEqual(result["context"]["receipt_file"], "base-baseline.json")
        self.assertNotIn("joules", result["context"])

    def _serve(self, input_text):
        output = io.StringIO()
        with patch.object(m.sys, "stdin", io.StringIO(input_text)), \
             patch.object(m.sys, "stdout", output), \
             patch.object(m.sys, "argv", ["szl_energy_mcp.py"]):
            m.main()
        return [json.loads(line) for line in output.getvalue().splitlines()]

    def test_stdio_rejects_large_duplicate_or_scalar_requests(self):
        invalid = [
            '{"jsonrpc":"2.0","method":"tools/list","method":"tools/call","id":2}\n',
            '[1,2,3]\n',
            "x" * (m.MAX_INPUT_LINE_CHARS + 100) + "\n",
        ]
        for request in invalid:
            with self.subTest(chars=len(request)):
                responses = self._serve(request)
                self.assertEqual(len(responses), 1)
                self.assertIn("error", responses[0])

    def test_tool_errors_do_not_reflect_untrusted_arguments_or_exceptions(self):
        msg = {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
               "params": {"name": "unknown-secret-reflection", "arguments": {}}}
        out = self._serve(json.dumps(msg) + "\n")
        self.assertTrue(out[0]["result"]["isError"])
        text = out[0]["result"]["content"][0]["text"]
        self.assertNotIn("unknown-secret-reflection", text)
        self.assertIn("SOURCE_OR_INPUT_UNAVAILABLE", text)


if __name__ == "__main__":
    unittest.main()
