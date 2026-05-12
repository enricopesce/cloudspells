# Generative AI Agent RAG Example

Deploys a complete OCI Generative AI Agent RAG pipeline in a single spell call.

## What Gets Created

- `oci.objectstorage.Bucket` — private document store for RAG source files
- `oci.generativeai.AgentKnowledgeBase` — OCI-managed vector index (no OpenSearch cluster to provision)
- `oci.generativeai.AgentDataSource` — wires the bucket to the knowledge base
- `oci.generativeai.AgentAgent` — the AI agent
- `oci.generativeai.AgentTool` — RAG tool connecting the agent to the knowledge base
- `oci.generativeai.AgentAgentEndpoint` — invocation endpoint (citations enabled)

## Architecture

```
GenAiAgentRag (support-rag)
  ├── ObjectStorage Bucket (documents)
  ├── AgentKnowledgeBase  ← OCI-managed vector index
  │     └── AgentDataSource ← bucket
  ├── AgentAgent
  │     └── AgentTool (RAG_TOOL_CONFIG) ← knowledge base
  └── AgentAgentEndpoint  ← citations enabled
```

## Prerequisites

- [Pulumi CLI](https://www.pulumi.com/docs/install/) installed
- OCI credentials configured (`~/.oci/config`)
- OCI Generative AI Agents service available in your region
- Python virtual environment set up from the repository root:
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
- Your OCI tenancy Object Storage namespace. Find it in the OCI Console under **Profile → Tenancy Details → Object Storage Namespace**, or via the CLI:
  ```bash
  oci os ns get --query 'data' --raw-output
  ```

## Configuration

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `compartment_ocid` | Yes | — | OCI compartment OCID |
| `namespace` | Yes | — | OCI tenancy Object Storage namespace |

## Deploy

```bash
cd examples/genai_agent_rag

# Create a new stack
pulumi stack init dev

# Set required config
pulumi config set compartment_ocid <your-compartment-ocid>
pulumi config set namespace <your-tenancy-namespace>

# Preview changes
pulumi preview

# Deploy
pulumi up
```

## Upload Documents

After deployment, upload source documents to the bucket:

```bash
BUCKET=$(pulumi stack output support_rag_document_bucket_name)
oci os object put \
  --namespace <your-namespace> \
  --bucket-name "$BUCKET" \
  --file ./docs/user-guide.pdf \
  --name user-guide.pdf
```

Then trigger a data ingestion sync in the OCI Console under **Generative AI → Agents → Knowledge Bases → Data Sources**.

## Outputs

| Output | Description |
|--------|-------------|
| `support_rag_endpoint_id` | OCID of the agent endpoint — use this to invoke the agent |
| `support_rag_agent_id` | OCID of the agent |
| `support_rag_knowledge_base_id` | OCID of the knowledge base |
| `support_rag_document_bucket_name` | Name of the Object Storage bucket for documents |

## Teardown

```bash
pulumi destroy
```
