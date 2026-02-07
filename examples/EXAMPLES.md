# OCIBlocks Examples

This directory contains multiple Pulumi project examples demonstrating OCIBlocks components.

## Project Structure

- **Main Stack** (`/examples/`): Complete example with VCN, Compute Instance, and ScalableWorkload
- **Standalone Examples** (subdirectories): Individual component demonstrations
  - `vcn/` - VCN with subnets and gateways only
  - `compute/` - VCN + ComputeInstance
  - `autoscale/` - VCN + ScalableWorkload with load balancer
  - `oke/` - VCN + OKE cluster

## Prerequisites

### 1. Passphrase File Setup

All projects use an encrypted passphrase file for Pulumi state. Create it once:

```bash
echo "your-secure-passphrase" > ~/.pulumi-passphrase
chmod 600 ~/.pulumi-passphrase
```

**Important:** This file is not tracked in git (.gitignore'd for security).

### 2. Export Environment Variable

Add to your shell profile (`~/.bashrc` or `~/.zshrc`):

```bash
export PULUMI_CONFIG_PASSPHRASE_FILE=~/.pulumi-passphrase
```

Or prefix each Pulumi command:

```bash
PULUMI_CONFIG_PASSPHRASE_FILE=~/.pulumi-passphrase pulumi preview
```

## Usage

### Main Stack (All Components)

```bash
cd /home/opc/source/OCIblocks/test
pulumi preview
pulumi up
```

### Standalone Examples

Each subdirectory is an independent Pulumi project:

```bash
# VCN only
cd /home/opc/source/OCIblocks/examples/vcn
pulumi preview

# Compute instance
cd /home/opc/source/OCIblocks/examples/compute
pulumi preview

# Autoscaling workload
cd /home/opc/source/OCIblocks/examples/autoscale
pulumi preview

# OKE cluster
cd /home/opc/source/OCIblocks/examples/oke
pulumi preview
```

## Configuration

Each project has its own state stored in `oci-stack-statefile/` (git-ignored).

Required config (already set):
- `compartment_ocid`: Your OCI compartment OCID

Optional config:
- `vcn_cidr_block`: Default "10.0.0.0/16"
- `ssh_key`: SSH public key (leave empty to auto-generate)

## State Management

- **Backend**: Local file backend (`file://oci-stack-statefile`)
- **Stack Name**: `paloma`
- **Encryption**: Secured with passphrase file

Each subdirectory has its own isolated state - you can deploy multiple examples simultaneously without conflicts.
