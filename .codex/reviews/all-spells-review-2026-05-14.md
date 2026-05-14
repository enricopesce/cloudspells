# All Spells Review - 2026-05-14

Status: analysis checkpoint only. No source files were edited for these findings.

Verification run:

```bash
make check
```

Result: passed. Ruff, format check, Pyright, pytest, coverage gate, and Vulture completed successfully. Pytest reported 435 passed with 1 warning and total coverage 92.44%.

## High-Priority Findings

1. IAM principal trust boundaries remain broad.

   `ComputeInstancePrincipal` still exposes raw OCI IAM grant fragments despite documenting this as a CS-001 exception, and it interpolates those fragments directly into policy statements. Both dynamic-group spells still match every instance in the compartment, so unrelated compute resources in the same compartment can inherit workload privileges.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/iam.py:112`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/iam.py:159`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/iam.py:201`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/iam.py:213`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/iam.py:305`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/iam.py:317`

2. `GenAiAgentRag` is still incomplete for a claimed complete RAG architecture.

   The spell creates the bucket, knowledge base, data source, agent, RAG tool, and endpoint, but no ingestion job or ingestion workflow. OCI Generative AI Agents data sources must be ingested before the knowledge base can serve that data to the agent.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:13`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:83`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:116`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:148`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:168`
   - Oracle docs: `https://docs.oracle.com/en-us/iaas/Content/generative-ai-agents/ai-data-sources.htm`

## Medium-Priority Findings

1. Several resource names are still built with f-string suffixes inside `create_resource_name(...)`, contrary to CS-008.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py:404`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py:424`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/nsg.py:686`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:791`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:874`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:983`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py:379`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py:647`

2. `NodePoolConfig.node_metadata` and `VolumeSpec.device` remain raw OCI passthrough surfaces.

   `node_metadata` lets callers pass OCI instance metadata directly, including pre-encoded `user_data`. `VolumeSpec.device` lets callers choose provider-specific paravirtualized device paths and is forwarded directly to the volume attachment.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py:168`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py:219`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py:417`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/volume.py:43`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/volume.py:107`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py:432`

3. `DataLakeBucket` still allows zero or negative lifecycle day values.

   The only validation is `delete_days > hot_days`, so values such as `hot_days=-1, delete_days=0` or `hot_days=0, delete_days=1` reach the OCI lifecycle policy as string day counts.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py:341`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py:366`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py:399`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py:408`
   - `tests/test_storage.py:186`

4. `GenAiAgentRag.bucket_name` still lets callers bypass the spell-owned private bucket.

   When `bucket_name` is supplied, the spell does not create or own the bucket, so it cannot enforce `NoPublicAccess`, storage tier, tagging, compartment placement, or lifecycle/security assumptions for RAG documents.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:24`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:73`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:83`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:96`
   - `tests/test_genai_agent_rag.py:79`

5. `InternalLoadBalancer` still documents VCN/on-premises access but only allows the primary VCN CIDR.

   The ingress rule source is `self.vcn.cidr_block`. It does not include additional VCN CIDR blocks or `on_premise_cidrs`, even though `Vcn` supports both and routes on-premises CIDRs through DRG-enabled private tiers.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/loadbalancer.py:399`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/loadbalancer.py:557`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/loadbalancer.py:563`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:400`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:425`

6. Bastion private-subnet SSH ingress from `0.0.0.0/0` remains a residual routing risk.

   The code now documents the OCI Bastion rationale and fails fast when the VCN was finalized without the rule, so the old ordering issue is improved. The rule itself still permits SSH from any routed source at the subnet security-list layer; actual client restriction is deferred to the Bastion resource allow list.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/bastion.py:156`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/bastion.py:163`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/bastion.py:218`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/bastion.py:224`
   - `tests/test_bastion.py:132`
   - `tests/test_bastion.py:158`

## Low-Priority Findings

1. `GenAiAgentRag` public methods still use one-line non-Google-style docstrings.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:188`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:192`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:196`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:200`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:204`

2. Archive retention docs still overstate immutability.

   The package docs call the `ArchiveBucket` retention rule immutable, and the constructor docstring says it creates an immutable compliance bucket, while the class docstring correctly says the rule is not cryptographically locked and an administrator can modify or delete it.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/__init__.py:35`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py:429`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py:475`

3. Package docs still mention raw subnet-tier constructor parameters.

   The public package docstring says subnet tier constants can be passed to spell constructors through a `subnet_tier` parameter, but current placement rules are role-based and `ComputeInstance` explicitly rejects direct `subnet` input.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/__init__.py:83`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/__init__.py:86`
   - `tests/test_compute.py:593`

4. Tests remain under-asserted for several security-sensitive contracts.

   Several tests still assert only resource existence or output non-nullness instead of checking IAM matching rules/statements, GenAI ingestion behavior, bucket ownership/security fields, lifecycle rule values, or load balancer rule sources.

   References:

   - `tests/test_iam.py:24`
   - `tests/test_iam.py:39`
   - `tests/test_genai_agent_rag.py:22`
   - `tests/test_genai_agent_rag.py:38`
   - `tests/test_storage.py:170`
   - `tests/test_loadbalancer.py:166`

## Rechecked Old Findings With No Current Issue Found

1. `ComputeInstance` no longer accepts public `vcn` or `subnet` parameters and derives placement from required `nsg.role`.

   The tests assert direct `vcn` and `subnet` inputs raise `TypeError`.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py:155`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py:160`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py:253`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py:259`
   - `tests/test_compute.py:582`
   - `tests/test_compute.py:593`

2. The old `ComputeInstance` post-finalization silent-skip behavior was not found.

   `ComputeInstance` now finalizes `nsg.vcn` after the NSG dependency is constructed, and `Vcn.add_security_rules()` raises after finalization instead of silently accepting late mutations.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py:253`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py:296`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:1249`
   - `tests/test_vcn.py:410`

3. The old `VcnRef.from_stack_reference()` optional-output issue was not found.

   It now uses `require_output()` for the CloudSpells network contract, including `drg_id`.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:1855`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:1872`

4. Raw public VCN security-list passthrough APIs were not found.

   `Vcn` and `VcnRef` no longer expose `add_security_list_rules` or `add_unique_security_list_rules`; tests assert both methods are absent.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:1214`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:1272`
   - `tests/test_vcn.py:405`
   - `tests/test_vcn.py:705`

## Open Questions Before Fixing

1. Should IAM principal spells keep the documented CS-001 exception for raw grant fragments, or should they move to fixed role variants and narrower dynamic-group membership?

2. Should `GenAiAgentRag` own data ingestion end to end, or should it be renamed/documented as provisioning only the RAG control-plane resources?

3. Should existing public passthrough-like fields such as `node_metadata`, `VolumeSpec.device`, and `GenAiAgentRag.bucket_name` be removed, deprecated, or kept behind explicit policy exceptions?

4. Should internal load balancer ingress include additional VCN CIDRs and DRG/on-premises CIDRs, or should the docs narrow the promise to primary-VCN-CIDR-only access?

5. Is Bastion's `0.0.0.0/0` private security-list rule an accepted OCI service exception that should be codified in AGENTS.md, or should CloudSpells model a stricter architecture?
