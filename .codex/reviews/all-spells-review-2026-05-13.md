# All Spells Review - 2026-05-13

Status: analysis checkpoint only. No source files were edited for these findings.

Verification run:

```bash
make check
```

Result: passed. Ruff, format check, Pyright, pytest, coverage gate, and Vulture completed successfully. Pytest reported 412 passed with 1 warning.

## High-Priority Findings

1. Public passthrough APIs conflict with CS-001. **Completed 2026-05-13.**

   `Nsg.add_rule()` exposes raw OCI rule fields and provider option objects, and `Vcn.add_security_list_rules()` accepts raw `oci.core.SecurityList*Args` directly.

   Completion note: Raw public passthrough APIs were removed from the public surface. `Vcn` callers now use `add_security_rules(SecurityRules(...))` / `add_unique_security_rules(...)`, and `Nsg` callers use opinionated allow helpers, including UDP helpers for DNS-style rules. Raw OCI rule accumulation remains private provider plumbing only.

   Completion verification:

   ```bash
   make check
   ```

   Result: passed. Ruff, format check, Pyright, pytest, coverage gate, and Vulture completed successfully. Pytest reported 413 passed with 1 warning.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/nsg.py:751`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:1163`

2. `ComputeInstance` lets callers choose subnet tier. **Completed 2026-05-13.**

   The public `subnet` parameter allows public placement. For public instances, the spell assigns a public IP and opens SSH from `0.0.0.0/0`, which violates CS-004 and creates a direct exposure risk.

   Completion note: `ComputeInstance` now requires a role-bearing `Nsg`, derives its VCN from `nsg.vcn`, derives subnet placement from `nsg.role.subnet_tier`, and no longer accepts public `vcn` or `subnet` parameters. Public compute remains possible through `Nsg(role=INTERNET_EDGE, ports=[...])`; internet ingress is controlled by NSG role ports instead of implicit ComputeInstance SSH rules. Tutorials, how-to guides, CLI templates, and examples were updated to document the `nsg=`-only ComputeInstance API.

   Completion verification:

   ```bash
   make check
   ```

   Result: passed. Ruff, format check, Pyright, pytest, coverage gate, and Vulture completed successfully. Pytest reported 418 passed with 1 warning.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py:163`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py:342`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py:533`

3. OKE advertises `VcnRef` support but cannot use it for current security-list behavior. **Completed 2026-05-13.**

   `OkeCluster` and `OkeClusterEnhanced` accept `Vcn | VcnRef`, but construction always adds non-empty security-list rules. `VcnRef` rejects those mutations, so the advertised API is not deployable with `VcnRef`.

   Completion note: OKE subnet-level security behavior now lives in a CloudSpells network profile. Live `Vcn` installs and exports the exact OKE profile via `enable_oke_profile(...)`; `VcnRef` remains read-only and CloudSpells-only, validates exported schema/profile metadata, and OKE requires the exact exported profile instead of mutating the referenced VCN. Tests and docs were updated to cover the live `Vcn` path, missing-profile rejection, successful profiled `VcnRef` deployment, and the CloudSpells-only reference contract.

   Completion verification:

   ```bash
   make check
   ```

   Result: passed. Ruff, format check, Pyright, pytest, coverage gate, and Vulture completed successfully. Pytest reported 429 passed with 1 warning and total coverage 92.43%.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/_network_profiles.py:18`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:1134`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:1194`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:1591`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py:311`
   - `tests/test_vcn.py:169`
   - `tests/test_oke.py:287`

4. `VcnRef.from_stack_reference()` mishandles optional stack outputs.  **Completed 2026-05-13.**

   `StackReference.get_output()` returns `Output` values, so optional missing outputs become `Output[None]` rather than plain `None`. The constructor's optional-output checks cannot detect the missing values, and later resources can be created with `None` subnet IDs.

   Reference:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:1637`

5. IAM principal spells use broad trust boundaries.

   `ComputeInstancePrincipal` accepts raw OCI policy fragments, then interpolates them into IAM statements. Both dynamic-group spells match every compute instance in the compartment, which can grant intended workload privileges to unrelated instances in the same compartment.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/iam.py:159`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/iam.py:201`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/iam.py:305`

6. `GenAiAgentRag` is incomplete for a claimed complete RAG architecture.

   The spell creates a knowledge base and data source, then moves directly to agent/tool/endpoint creation. It never creates or exposes an ingestion job or ingestion workflow. OCI Generative AI Agents data sources must be ingested before the knowledge base can serve that data to the agent.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:13`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:116`
   - Oracle docs: `https://docs.oracle.com/en-us/iaas/Content/generative-ai-agents/ai-data-sources.htm`


## Medium-Priority Findings

1. Several resource names are built with f-string suffixes inside `create_resource_name(...)`, contrary to CS-008.

   Examples:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/nsg.py:813`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py:414`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py:354`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py:781`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/network_logging.py:201`

2. `ComputeInstance` silently skips adding security rules after VCN finalization.

   This can deploy later instances without expected security-list rules instead of failing clearly or forcing the caller to construct spells before finalization.

   Reference:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py:299`

3. `NodePoolConfig.node_metadata` and `VolumeSpec.device` are raw OCI passthrough surfaces.

   `node_metadata` exposes OCI metadata directly, including base64 `user_data` behavior. `VolumeSpec.device` exposes provider-specific paravirtualized device paths.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py:147`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py:392`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/volume.py:43`

4. `DataLakeBucket` allows invalid lifecycle day values.

   It validates only `delete_days > hot_days`; zero or negative `hot_days` can reach OCI lifecycle policy input.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py:341`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py:366`

5. `GenAiAgentRag.bucket_name` lets callers bypass the spell-owned private bucket.

   Supplying an existing bucket means the spell cannot enforce `NoPublicAccess`, tags, compartment placement, or bucket policy assumptions.

   Reference:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:73`

6. `InternalLoadBalancer` documents VCN/on-premises access but only allows `self.vcn.cidr_block`.

   The security-list rule does not include VCN additional CIDRs or DRG/on-premises CIDRs even though the VCN model supports them.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/loadbalancer.py:404`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/loadbalancer.py:568`

7. Bastion private-subnet SSH ingress from `0.0.0.0/0` is a residual routing risk.

   This may be required for OCI Bastion service behavior, but it allows SSH from any routed source if DRG, peering, or future routes can reach the private subnet.

   Reference:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/bastion.py:215`

## Low-Priority Findings

1. `GenAiAgentRag` public methods use one-line docstrings instead of Google-style `Returns:` docstrings.

   Reference:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py:188`

2. Package docs overstate `ArchiveBucket` retention as immutable.

   The package docs say the retention rule is immutable, while the storage module correctly says administrators can modify or delete the rule unless it is separately locked.

   References:

   - `packages/cloudspells-oci/src/cloudspells/providers/oci/__init__.py:34`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py:429`

3. Tests leave important spell contracts under-asserted.

   Current tests pass, but several focus on resource existence rather than fixed decisions and security-sensitive defaults, such as IAM matching rules/statements, GenAI ingestion behavior, lifecycle rule values, LB rule content, VcnRef optional-output handling, and kubeconfig permissions.

## Open Questions Before Fixing

1. Should raw security-rule APIs be removed from the public surface, or should CS-001 get an explicit exception for advanced networking composition?

2. Should `ComputeInstance` always use private subnet placement, or should there be separate opinionated spell classes for public bastion-like instances versus private workloads?

3. Should OKE support `VcnRef`, and if so should referenced VCN stacks be required to pre-export OKE-compatible security rules?

4. Should `GenAiAgentRag` own data ingestion end to end, or be renamed/documented as provisioning only the control-plane resources?

5. Should IAM dynamic groups be constrained with CloudSpells-managed tags, fixed workload identifiers, or separate narrower spell variants?

6. Should existing public inputs such as `NodePoolConfig.node_metadata`, `VolumeSpec.device`, and `GenAiAgentRag.bucket_name` be removed now, deprecated first, or retained behind explicit policy exceptions?
