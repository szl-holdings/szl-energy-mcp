"""One OIDC Trusted Publishing workflow, pinned and release-gated.

Parses ``.github/workflows/*.yml`` and fails unless exactly one workflow
publishes with ``pypa/gh-action-pypi-publish``, that pin is a full SHA, the
publishing job has ``id-token: write`` and an environment, and that workflow
cannot be started with ``workflow_dispatch``.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
ACTION = "pypa/gh-action-pypi-publish"
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class _GitHubActionsLoader(yaml.SafeLoader):
    """SafeLoader that leaves GitHub Actions keys such as ``on`` as strings.

    PyYAML's YAML 1.1 resolver would otherwise turn ``on`` into ``True`` and
    hide the trigger map.
    """


for _ch, _resolvers in list(_GitHubActionsLoader.yaml_implicit_resolvers.items()):
    _GitHubActionsLoader.yaml_implicit_resolvers[_ch] = [
        (tag, regexp)
        for tag, regexp in _resolvers
        if tag != "tag:yaml.org,2002:bool"
    ]


def _load(path: Path) -> dict:
    document = yaml.load(path.read_text(encoding="utf-8"), Loader=_GitHubActionsLoader)
    if not isinstance(document, dict):
        raise AssertionError(f"{path.name}: workflow document is not a mapping")
    return document


def _iter_uses(node: object):
    if isinstance(node, dict):
        uses = node.get("uses")
        if isinstance(uses, str):
            yield uses
        for value in node.values():
            yield from _iter_uses(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_uses(item)


def _action_ref(uses: str) -> str | None:
    prefix = ACTION + "@"
    if uses.startswith(prefix):
        return uses[len(prefix) :]
    if uses == ACTION:
        return ""
    return None


def _has_workflow_dispatch(triggers: object) -> bool:
    if isinstance(triggers, str):
        return triggers == "workflow_dispatch"
    if isinstance(triggers, list):
        return any(item == "workflow_dispatch" for item in triggers)
    if isinstance(triggers, dict):
        return "workflow_dispatch" in triggers
    return False


def _environment_ok(environment: object) -> bool:
    if isinstance(environment, str):
        return bool(environment.strip())
    if isinstance(environment, dict):
        name = environment.get("name")
        return isinstance(name, str) and bool(name.strip())
    return False


def _publishing_jobs(document: dict) -> list[tuple[str, dict, list[str]]]:
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return []
    found = []
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        refs = [ref for uses in _iter_uses(job) if (ref := _action_ref(uses)) is not None]
        if refs:
            found.append((str(job_name), job, refs))
    return found


def test_exactly_one_sha_pinned_oidc_pypi_publisher() -> None:
    paths = sorted(WORKFLOWS.glob("*.yml"))
    assert paths, f"no workflow files under {WORKFLOWS}"

    publishers: list[tuple[str, str, dict, list[str], dict]] = []
    violations: list[str] = []

    for path in paths:
        document = _load(path)
        document_refs = [
            ref for uses in _iter_uses(document) if (ref := _action_ref(uses)) is not None
        ]
        jobs = _publishing_jobs(document)
        job_ref_count = sum(len(refs) for _name, _job, refs in jobs)
        if len(document_refs) != job_ref_count:
            violations.append(
                f"{path.name}: {ACTION} is referenced outside a job "
                f"({len(document_refs)} uses, {job_ref_count} inside jobs)"
            )
        for job_name, job, refs in jobs:
            publishers.append((path.name, job_name, job, refs, document))

    workflow_names = sorted({name for name, _job, _job_body, _refs, _doc in publishers})
    if len(workflow_names) != 1:
        violations.append(
            "expected exactly one workflow referencing "
            f"{ACTION}, found {len(workflow_names)}: {workflow_names or 'none'}"
        )

    for filename, job_name, job, refs, document in publishers:
        for ref in refs:
            if SHA_RE.fullmatch(ref) is None:
                violations.append(
                    f"{filename}: job {job_name!r} references {ACTION}@{ref or '<missing>'}, "
                    "which is not a 40-hex SHA"
                )
        permissions = job.get("permissions")
        id_token = permissions.get("id-token") if isinstance(permissions, dict) else None
        if id_token != "write":
            violations.append(
                f"{filename}: job {job_name!r} permissions.id-token is {id_token!r}, expected 'write'"
            )
        if not _environment_ok(job.get("environment")):
            violations.append(f"{filename}: job {job_name!r} has no environment")
        triggers = document.get("on", document.get(True))
        if triggers is None:
            violations.append(f"{filename}: publish workflow has no 'on' triggers")
        elif _has_workflow_dispatch(triggers):
            violations.append(f"{filename}: publish workflow has a workflow_dispatch trigger")

    assert not violations, "OIDC publish workflow invariant failed:\n- " + "\n- ".join(violations)
