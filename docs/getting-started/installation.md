# Installation

This page walks you through installing CloudBlocks and its prerequisites from scratch.

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.8+ | Runtime |
| [Pulumi CLI](https://www.pulumi.com/docs/install/) | latest | Deploy infrastructure |
| [OCI CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm) (optional) | latest | Verify OCI credentials |

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

CloudBlocks uses the standard OCI SDK credential chain. The simplest approach is `~/.oci/config`:

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

## Install CloudBlocks

### 1. Clone the repository

```bash
git clone https://github.com/enricopesce/cloudblocks.git
cd cloudblocks
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure a Pulumi state backend

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

Run the test suite to confirm everything is wired correctly:

```bash
source .venv/bin/activate
pytest tests/ -q
```

All tests should pass. If any fail, check that your virtual environment is active and dependencies are installed.

---

## Next step

[Deploy your first VCN →](first-deploy.md)
