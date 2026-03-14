# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| `main` branch | Yes |
| `dev` branch | Yes (pre-release) |
| Older tags | No |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Instead, email **security@cloudblocks.dev** with:
- Subject: `SECURITY: <one-line summary>`
- Steps to reproduce
- Potential impact and affected versions
- Any suggested fix (optional but appreciated)

We will acknowledge receipt within **3 business days** and aim to release a patch within **14 days** for critical issues.

## Scope

**In scope:**
- Vulnerabilities in CloudBlocks framework code (`src/`)
- Insecure defaults that could expose user infrastructure

**Out of scope:**
- The user's OCI configuration or credentials
- Pulumi or OCI SDK vulnerabilities (report those upstream)
- Issues requiring a compromised OCI account to exploit

## Safe Harbour

We will not take legal action against researchers who report vulnerabilities responsibly following this policy.
