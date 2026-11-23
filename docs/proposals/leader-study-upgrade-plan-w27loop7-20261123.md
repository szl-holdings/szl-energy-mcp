# Leader-Study Upgrade Plan - W27 loop-7 - 2026-11-23

Status: PROPOSE-ONLY DRAFT - DO NOT MERGE. Owner-gated: merging requires governing approval and the estate signature-wall owner unlock.

Repo: szl-energy-mcp - Energy-metering vertical MCP server - receipt-gated (every result carries its source sha256). Fail-closed, zero deps.

Frame: OUROBOROS loop-7 leader study. Governing seat: Kimi kimi-k3.1-pro (json_ok, think off). Advisory seats: Astra/Sol/Claude community rails (provenance unverified, advisory only). Leader evidence web-verified 2026-11-23.

## Leader moats to absorb
- CodeCarbon v2.4.1: RAPL Intel CPU + NVML Nvidia GPU + RAM energy telemetry, region-specific carbon intensity conversion, per-component logging for training AND inference Moat: Direct hardware telemetry integration with per-component granularity and carbon-intensity conversion across both training and inference workloads
- MLPerf Power benchmarking: Standardized power benchmarking methodology for ML workloads Moat: Industry-accepted measurement methodology and comparability that makes energy numbers citable across organizations
- Kepler Kubernetes energy: Kubernetes-native energy attribution Moat: Production-cluster energy attribution at pod/container granularity, meeting operators where workloads actually run
- Joules-per-answer energy accounting doctrine: Energy accounting normalized to the unit of delivered inference output Moat: A decision-relevant denominator (per answer) rather than raw fleet totals, enabling cost/efficiency tradeoff reasoning

## Honest gaps (grounded in repo facts)
- No independent energy, carbon, or production claim follows from the interface: the README states each result is a source-checksum receipt with issuer_signature_verified=false and source_revision_verified=false, so local hashing is not signature or publisher proof and the moving main reference authenticates neither issuer nor immutable revision
- No actual joules are measured or inferred: energy_rollup returns NO_MEASUREMENT when measured_receipts=0 and battery_energy_context carries hardware context only with no joules inferred, so the repo currently provides zero direct energy telemetry versus CodeCarbon/Kepler
- A zero-row rollup means NO MEASUREMENT AVAILABLE, not a measured observation of zero joules, so the tool cannot yet distinguish measured-zero from absent data as a real metering leader would
- Index and listing completeness is capped and fail-closed: energy listings stop before the 200-item cap and battery listings before 500, and reaching a cap returns UNAVAILABLE rather than a global catalog, so global-absence or full-fleet claims are not supported
- The README text is truncated mid-sentence at 'Revisions remain unpi', indicating the revision-pinning/immutability story is unfinished in the provided facts and revisions are not verified
- pushed_at is null, so there is no evidence in the facts of committed implementation beyond the README description; tool behavior is asserted by the README, not demonstrated by pushed code in these facts
- No carbon-intensity conversion or per-component (RAPL/NVML/RAM) telemetry integration is present in the facts; the only hardware context comes from evaluation-battery receipts

## Dosed upgrade plan
- Dose 1 (docs/integrity, no behavior change): finish the truncated revision-pinning sentence and publish an explicit threat-model doc restating that receipts prove byte-integrity of fetched sources only, not issuer authenticity, signature validity, or immutable revision; keep fail-closed semantics unchanged
- Dose 2 (provenance hardening, propose-only): add an optional, clearly-labeled immutable-revision pinning field and an issuer-signature verification hook that defaults to false and fails closed, so source_revision_verified and issuer_signature_verified can become true only when actually verified
- Dose 3 (real measurement ingestion, propose-only): introduce an optional ingestion path for externally-measured per-component energy (RAPL/NVML/RAM) carried as signed receipts, keeping the current NO_MEASUREMENT behavior whenever measured_receipts=0 and never inferring joules from context
- Dose 4 (decision metric, propose-only): add a joules-per-answer normalized field that is populated only from genuinely measured receipts and is explicitly UNAVAILABLE otherwise, avoiding any fabricated denominator
- Dose 5 (comparability and operability, propose-only): document an MLPerf Power-style methodology alignment for any measured claims and sketch a Kepler-style Kubernetes attribution integration, both gated behind the same receipt/fail-closed doctrine
- Risk note: Primary risk is overstating trust: adding pinning, signature hooks, or measured-energy ingestion could be misread as authenticated measurement if not kept strictly fail-closed and clearly labeled, which would contradict the repo's core receipt-not-benchmark doctrine. Secondary risks include fabricating joules-per-answer or carbon figures without real measured receipts, and treating capped listings or zero-row rollups as authoritative global/measured claims. Mitigation: keep issuer_signature_verified/source_revision_verified false until genuinely verified, never infer joules from context, and preserve NO_MEASUREMENT/UNAVAILABLE fail-closed behavior throughout.
- Propose-only note: All steps beyond Dose 1 are propose-only design directions grounded in the README's stated doctrine; the facts contain no pushed implementation (pushed_at is null), so no code changes are asserted or performed here and each step requires review before implementation.

## Advisory notes (unverified rails, non-binding)
- astra: szl-quant-bench: torchao szl-block-kv: vLLM szl-energy-mcp: Home Assistant
- sol: szl-quant-bench: Hardware-specific quantization kernels for diverse accelerators szl-block-kv: Zero-copy memory mapping for heterogeneous GPU clusters szl-energy-mcp: Verified hardware-attested energy telemetry standards
- claude: szl-quant-bench: Hardware-specific quantization kernels (Triton/CUDA) for zero-shot accuracy validation. szl-block-kv: Dynamic memory fragmentation management for multi-tenant long-context serving. szl-energy-mcp: Hardware-level power rail telemetry integration for verifiable energy auditing.

## DO NOT MERGE
This plan is a proposal artifact of the 10-pass OUROBOROS loop (loop-7 of 10). No code, no CI, no behavior changes in this file. A reviewer with authority may convert to a work order later.