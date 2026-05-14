# Installation

This page walks you through installing CloudSpells and its prerequisites from scratch.

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.10+ | Runtime (union type syntax used throughout the packages) |
| [Pulumi CLI](https://www.pulumi.com/docs/install/) | latest | Deploy infrastructure |
| [OCI CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm) (optional) | latest | Verify OCI credentials |

!!! note "`cloudspells-cli` requires Python 3.12+"
    The `cloudspells-cli` package uses features available only in Python 3.12 and later. It lives in this repository, but the current publish workflow does not publish a CLI wheel to PyPI.

### Install the Pulumi CLI

=== "Linux / macOS"

    ```bash
    curl -fsSL https://get.pulumi.com | sh
    ```

=== "Homebrew"

    ```bash
    brew install pulumi/tap/pulumi
    ```

=== "Windows (winget)"

    ```bash
    winget install pulumi
    ```

Verify:

```bash
pulumi version
```

### Configure OCI credentials

CloudSpells uses the standard OCI SDK credential chain. The simplest approach is `~/.oci/config`:

```ini
[DEFAULT]
user=ocid1.user.oc1..aaaa...
fingerprint=xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx
tenancy=ocid1.tenancy.oc1..aaaa...
region=eu-frankfurt-1
key_file=~/.oci/oci_api_key.pem
```

If you already use the OCI CLI, your credentials are already in place. Verify with:

```bash
oci iam region list
```

---

## Install CloudSpells

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows
```

### 2. Install from PyPI

Install the OCI provider package. `cloudspells-core` is pulled in automatically as a dependency:

```bash
pip install cloudspells-oci
```

!!! note "Installing from source"
    If you need unreleased changes or want to contribute, clone the repository and install in editable mode instead:

    ```bash
    git clone https://github.com/enricopesce/cloudspells.git
    cd cloudspells
    pip install -e packages/cloudspells-core -e packages/cloudspells-oci
    ```

    To use the source CLI, install it in the same Python 3.12+ environment:

    ```bash
    pip install -e packages/cloudspells-cli
    ```

## CloudSpells CLI

The source-installed `cs` command wraps common Pulumi Automation API workflows:

| Command | Purpose |
|---------|---------|
| `cs wizard` | Interactive guided flow for scaffolding, deploy, status, refresh, destroy, and project workflows |
| `cs new <spell> <name>` | Scaffold a stack directory from a spell template; use `--list` to show available templates |
| `cs up [path]` | Deploy a stack; use `--preview` to preview without applying changes |
| `cs destroy [path]` | Destroy stack resources; use `--remove` to remove stack state after destroy |
| `cs output [path]` | Read stack outputs; use `--key` for one output or `--json` for JSON |
| `cs refresh [path]` | Reconcile Pulumi state with live OCI resources |
| `cs status [path]` | Display the resource tree from Pulumi state without live OCI API calls |
| `cs config set/get/list` | Manage stack configuration keys, including `--secret` values |
| `cs stack list/rm` | List or remove Pulumi stacks for a project directory |
| `cs backend oci-url` | Generate an OCI Object Storage backend URL for Pulumi state |
| `cs project new/up/destroy/status` | Scaffold and operate ordered multi-spell projects from `project.yaml` |

`cs new` currently includes templates for `autoscale`, `bastion`, `compute`,
`iam`, `lb`, `oke`, `storage`, `vcn`, and `web-db`.

### 3. Configure a Pulumi state backend

Pulumi needs somewhere to store state. The simplest option for getting started is the local filesystem:

```bash
pulumi login --local
```

For production use, store state in OCI Object Storage:

```bash
pulumi login oci://bucket-name
```

Or use the free Pulumi Cloud:

```bash
pulumi login
```

---

## Verify the installation

Confirm the package is importable:

```bash
python -c "import cloudspells.providers.oci; print('cloudspells-oci OK')"
```

And that the Pulumi CLI can see it:

```bash
pulumi version
```

If the import fails, check that your virtual environment is active and that `pip install cloudspells-oci` completed without errors.

---

## Next step

[Deploy your first VCN →](first-deploy.md)
