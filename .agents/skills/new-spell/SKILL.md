---
name: new-spell
description: Design and implement a new OCI spell in cloudspells-oci, including its public exports, Pulumi mocks, and tests.
---

# Create an OCI spell

## Design the use case

Use the service and requirements already supplied. If the request leaves the use case open, propose up to five production patterns, ranked by relevance. For each, give the class name, architectural decision, resources, and caller inputs. Separate classes when the access model, network placement, retention, scaling, or compliance requirements justify different architectures. Use a constructor value when the difference is a caller-owned input and the rest of the architecture is shared.

Read the repository's root `AGENTS.md` and scoped guidance in `packages/AGENTS.md` and `tests/AGENTS.md`. Check existing OCI exports, core abstractions, `BaseResource`, and the nearest spell. Use `bastion.py` as a minimal OCI implementation reference and `storage.py` for multiple public classes sharing a private mixin.

Define the constructor inputs, inheritance, resources, output types, validation, and defaults before implementing. For networked spells, include subnet tier, ingress and egress requirements, stable rule fingerprints, and when the network is finalized. Confirm material choices with the user when their request leaves the public API or architecture unresolved.

## Implement and verify

1. Verify the resource argument names and types against the installed `pulumi_oci` SDK. Inspect the generated `<Resource>Args` class when the resource constructor uses a generic signature.
2. Add the module under `packages/cloudspells-oci/src/cloudspells/providers/oci/`. Validate plain inputs before creating Pulumi state, name resources through `BaseResource`, and parent child resources with `pulumi.ResourceOptions(parent=self)`. Register the component outputs and follow the existing export key convention.
3. Add the public classes to the provider package imports, `__all__`, and module docstring. Preserve existing semantic groupings.
4. Extend `tests/mocks.py` for new computed outputs and invokes. Add or update `tests/test_<module>.py` for resource creation, public outputs, export keys, and validation boundaries. Cover attached and referenced VCNs where applicable.
5. Check every public class against CS-001 through CS-012. Run `make check` and report the actual result.
