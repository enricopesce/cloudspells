"""Check documentation for known code-drift patterns."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ForbiddenText:
    """A forbidden text pattern in one or more documentation files."""

    paths: tuple[str, ...]
    needle: str
    reason: str


FORBIDDEN_TEXT: tuple[ForbiddenText, ...] = (
    ForbiddenText(
        paths=("docs/tutorials/secure-vcn.md", "examples/secure-vcn/__main__.py", "docs/tutorials/web-db.md"),
        needle="ZprLabel",
        reason="CloudSpells does not create ZPR labels on NSGs.",
    ),
    ForbiddenText(
        paths=("docs/tutorials/secure-vcn.md", "examples/secure-vcn/__main__.py", "docs/tutorials/web-db.md"),
        needle="Zero Trust Packet Routing",
        reason="ZPR policy examples require tags that the code does not create.",
    ),
    ForbiddenText(
        paths=("docs/tutorials/oke.md", "docs/reference/oke-architecture.md"),
        needle='display_name="lab-k8s"',
        reason="OkeCluster has no display_name parameter.",
    ),
    ForbiddenText(
        paths=("docs/tutorials/oke.md", "docs/reference/oke-architecture.md"),
        needle="4 NSGs with 34 NSG rules",
        reason="OKE rule counts depend on kubectl_allowed_cidrs.",
    ),
    ForbiddenText(
        paths=("docs/tutorials/oke.md", "docs/reference/oke-architecture.md"),
        needle="with 19 rules",
        reason="OKE security-list rule counts depend on kubectl_allowed_cidrs.",
    ),
    ForbiddenText(
        paths=("docs/reference/vcn-architecture.md", "docs/reference/oke-architecture.md"),
        needle="private→secure",
        reason="Private-to-secure paths are registered by NSG relationships, not VCN baseline rules.",
    ),
    ForbiddenText(
        paths=("packages/AGENTS.md",),
        needle="add_security_list_rules",
        reason="The public VCN API is add_security_rules.",
    ),
    ForbiddenText(
        paths=("docs/how-to/loadbalancer.md",),
        needle="10.0.128.10",
        reason="This IP is outside the default VCN CIDR.",
    ),
    ForbiddenText(
        paths=("docs/tutorials/autoscale.md",),
        needle="yum install",
        reason="The autoscale example uses dnf.",
    ),
    ForbiddenText(
        paths=("README.md", "docs/concepts/design.md"),
        needle="same user-facing API",
        reason="Only the OCI provider exists today; other providers are roadmap work.",
    ),
    ForbiddenText(
        paths=("README.md",),
        needle="zero-Pulumi-dependency",
        reason="Config wraps pulumi.Config.",
    ),
    ForbiddenText(
        paths=("docs/concepts/design.md",),
        needle="Nsg`, `Bastion`, `VcnFlowLogs`",
        reason="VcnFlowLogs attaches logs after subnets exist; it is not a rule-registering spell.",
    ),
)


REQUIRED_TEXT: tuple[ForbiddenText, ...] = (
    ForbiddenText(
        paths=("docs/tutorials/autoscale.md",),
        needle="dnf install -y nginx",
        reason="The autoscale tutorial should track the example cloud-init package manager.",
    ),
    ForbiddenText(
        paths=("docs/tutorials/autoscale.md",),
        needle="cloud_init_script=user_data_script",
        reason="The autoscale tutorial should use the current ScalableWorkload parameter.",
    ),
    ForbiddenText(
        paths=("docs/how-to/bastion.md", "docs/reference/vcn-architecture.md"),
        needle="attached to the private subnet",
        reason="The Bastion placement decision should stay explicit in docs.",
    ),
    ForbiddenText(
        paths=(
            "docs/superpowers/plans/2026-05-13-cs008-resource-names.md",
            "docs/superpowers/plans/2026-05-13-vcnref-network-profiles.md",
            "docs/superpowers/plans/2026-05-13-vcnref-stack-output-normalization.md",
        ),
        needle="Historical plan",
        reason="Historical plan docs must be marked as non-product manuals.",
    ),
)


def read_text(relative_path: str) -> str:
    """Read a repository file as UTF-8 text."""
    return (ROOT / relative_path).read_text(encoding="utf-8")


def check_forbidden() -> list[str]:
    """Return failures for forbidden text that is present."""
    failures: list[str] = []
    for check in FORBIDDEN_TEXT:
        for relative_path in check.paths:
            if check.needle in read_text(relative_path):
                failures.append(f"{relative_path}: forbidden text {check.needle!r}: {check.reason}")
    return failures


def check_required() -> list[str]:
    """Return failures for required text that is missing."""
    failures: list[str] = []
    for check in REQUIRED_TEXT:
        for relative_path in check.paths:
            if check.needle not in read_text(relative_path):
                failures.append(f"{relative_path}: missing text {check.needle!r}: {check.reason}")
    return failures


def check_example_readmes() -> list[str]:
    """Return failures for example stacks without a README."""
    failures: list[str] = []
    for main_file in sorted((ROOT / "examples").glob("*/__main__.py")):
        readme = main_file.with_name("README.md")
        if not readme.exists():
            failures.append(f"{readme.relative_to(ROOT)}: missing README for example stack")
    return failures


def main() -> int:
    """Run all documentation drift checks."""
    failures = [*check_forbidden(), *check_required(), *check_example_readmes()]
    if failures:
        print("Documentation drift check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Documentation drift check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
