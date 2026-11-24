# Pulumi examples

Each example demonstrates one usage pattern. Keep stack-specific configuration in `__main__.py` and put reusable provisioning logic in the spell.

Run Pulumi commands within the example directory. From the repository root, activate the environment with `source .venv/bin/activate` and then change to `examples/<name>`. Read the example's entry point and README, where available, for stack configuration and prerequisites. Most examples use `compartment_ocid`. CIDR keys and defaults vary by stack. Use `pulumi preview` to inspect changes. `pulumi up` deploys resources and `pulumi destroy` tears them down.

| Example | Pattern |
| --- | --- |
| `vcn/` | Standalone VCN with outputs consumed by `import-vcn/` |
| `compute/` | NSG roles, role-based subnet placement, and block volumes |
| `autoscale/` | Load balancer, instance pool, CPU autoscaling, and cloud-init |
| `oke/` | Kubernetes cluster and kubeconfig |
| `bastion/` | OCI Bastion SSH access to a private instance |
| `web-db/` | Internet-edge, application, and database tiers connected through `nsg.serves()` |
| `iam/` | Compute and OKE instance principals and compartment administration |
| `import-vcn/` | Cross-stack VCN access via `VcnRef.from_stack_reference()` |
| `secure-vcn/` | Flow logs, four NSG tiers, management SSH, and instance principals |
| `loadbalancer/` | HTTPS termination and HTTP-to-HTTPS redirection |
| `storage/` | Versioned backups and tiered data lake retention |
| `genai_agent_rag/` | Document bucket, knowledge base, RAG agent, tool, and endpoint |
