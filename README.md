# OCIBlocks Infrastructure Framework

A Python-based infrastructure-as-code (IaC) framework built on [Pulumi](https://www.pulumi.com/) for Oracle Cloud Infrastructure (OCI).

## What is OCIBlocks?

OCIBlocks provides high-level **building blocks** that encapsulate multiple OCI resources into simplified interfaces. Built on Pulumi's `ComponentResource` model, it enables developers to deploy sophisticated infrastructure with minimal code while enforcing OCI best practices.

```python
# Deploy a complete VCN + Compute Instance with just a few lines
vcn = Vcn(name="lab", compartment_id=compartment_id, stack_name=stack_name)
web_server = ComputeInstance(name="web-server", compartment_id=compartment_id, vcn=vcn, stack_name=stack_name)
```

## Motivations

| Challenge | OCIBlocks Solution |
|-----------|-------------------|
| **Complex low-level configurations** | High-level blocks abstract VCNs, Kubernetes clusters, etc. |
| **Lack of OCI-specific abstractions** | Prebuilt blocks with embedded OCI best practices |
| **Code duplication across projects** | Modular, reusable components |
| **Steep learning curve** | Intuitive Python interface with minimal parameters |

## Architecture

### Core Framework

OCIBlocks centers on a custom `BaseResource` class (extending Pulumi's `ComponentResource`) that provides:

- **Standardized naming** via `ResourceNamer`
- **Consistent tagging** via `ResourceTagger`
- **Output registration** for cross-block dependencies

### Building Blocks

Each block encapsulates one or more Pulumi resources:

| Block | Resources Included |
|-------|-------------------|
| **VCN** | Virtual Cloud Network, subnets, gateways, route tables, security lists |
| **OKE Cluster** | Kubernetes cluster, node pools, networking components |
| **Compute Instance** | VM instance, block volumes, SSH key management |

### Stack and Building Block Model

- **Stack**: A deployment unit scoped to a single OCI compartment and region
- **Building Block**: A reusable component grouping related OCI resources

```
Stack (e.g., "production")
├── VCN Block
│   ├── Internet Gateway
│   ├── NAT Gateway
│   ├── Public Subnet
│   └── Private Subnet
└── Compute Block
    ├── VM Instance
    └── Block Volume
```

## Key Features

- **Declarative Syntax**: Define infrastructure using Python classes
- **Type Safety**: Python type hints + Pulumi's strongly-typed APIs
- **State Management**: Pulumi Service, S3, or local storage backends
- **Modularity**: Reusable blocks for common OCI patterns
- **Extensibility**: Create custom blocks via `BaseResource` inheritance
- **Preview and Diff**: `pulumi preview` shows changes before deployment

### Pulumi Features

- **Automation API**: Programmatic control for CI/CD pipelines
- **Dynamic Providers**: Custom resource types for specialized configurations
- **Secrets Management**: Encrypted storage for sensitive data
- **Parallel Execution**: Faster deployments via parallel provisioning
- **Policy as Code**: Compliance enforcement via CrossGuard policies

## Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Define         │     │  Preview        │     │  Deploy         │
│  Python code    │ ──▶ │  pulumi preview │ ──▶ │  pulumi up      │
│  with blocks    │     │  (review diff)  │     │  (provision)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

1. **Define**: Write Python code using OCIBlocks building blocks
2. **Preview**: Run `pulumi preview` to see planned changes
3. **Deploy**: Run `pulumi up` to provision resources
4. **Manage**: Use `pulumi refresh`, `pulumi destroy` for lifecycle management

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.8+ |
| IaC Engine | Pulumi 3.x |
| Cloud Provider | OCI (via pulumi_oci) |
| Testing | Pytest |
| Type Checking | Pyright |

## OCIBlocks vs Raw Pulumi

| Feature | OCIBlocks | Pulumi |
|---------|-----------|--------|
| **Abstraction Level** | High-level blocks with OCI best practices | Low-level resources |
| **Code Volume** | Minimal (prebuilt blocks) | Verbose (individual resources) |
| **OCI Optimization** | Embedded best practices | General-purpose |
| **Encapsulation** | Complex patterns as single blocks | Manual resource grouping |
| **Reusability** | Ready-to-use blocks | Requires custom components |
| **Configuration** | Minimal parameters | Detailed per-resource config |
| **Language** | Python only | Multiple languages |

## Security and Best Practices

- **IAM**: Least-privilege policies enforced by default
- **Networking**: Private subnets with NAT gateways for secure access
- **Encryption**: Automatic encryption for storage and databases
- **Tagging**: Standardized tags for cost tracking and governance
- **Secrets**: Pulumi encrypted secrets for credentials and API keys

## Extensibility

### Creating Custom Blocks

Extend `BaseResource` to create custom building blocks:

```python
from core.base import BaseResource

class MyCustomBlock(BaseResource):
    def __init__(self, name: str, compartment_id: str, stack_name: str):
        super().__init__("ociblocks:custom:MyBlock", name, compartment_id, stack_name)
        # Define your resources here
```

### Additional Options

- **Plugins**: Integrate with monitoring, CI/CD tools via Pulumi plugins
- **Cross-Region**: Multi-region deployments via Pulumi stack references
- **Automation API**: Embed deployments in larger applications

## Future Enhancements

- **CLI Tool**: OCIBlocks-specific commands for stack management
- **Visual Designer**: GUI for designing infrastructure
- **Multi-Cloud**: Extend to AWS, Azure, GCP
- **Community Blocks**: Repository of community-contributed patterns

## Getting Started

```bash
# Install dependencies
pip install -r requirements.txt

# Configure OCI credentials
# (ensure ~/.oci/config is set up)

# Preview infrastructure
cd examples && pulumi preview

# Deploy
pulumi up
```

## License

See [LICENSE](LICENSE) for details.
