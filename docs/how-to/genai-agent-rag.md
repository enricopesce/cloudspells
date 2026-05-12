# How to Deploy a Generative AI RAG Agent

This guide shows you how to provision a complete RAG (Retrieval-Augmented Generation) pipeline on OCI Generative AI Agents using the `GenAiAgentRag` spell.

## When to use this

- You want an AI agent that answers questions grounded in your own documents.
- You need a fully-managed RAG pipeline without provisioning OpenSearch or a VCN yourself.
- You want to expose a chat endpoint that cites sources from an Object Storage bucket.

---

## Prerequisites

- OCI Generative AI Agents service is available in your region and tenancy.
- Your OCI tenancy Object Storage **namespace** — a fixed string assigned to your tenancy. Find it in the OCI Console under **Profile → Tenancy Details → Object Storage Namespace**, or via the CLI:

  ```bash
  oci os ns get --query 'data' --raw-output
  ```

Store it in Pulumi config:

```bash
pulumi config set namespace <your-namespace>
```

---

## Minimal deployment

`GenAiAgentRag` creates every resource in the RAG pipeline from a single call:

```python
from cloudspells.providers.oci import GenAiAgentRag

rag = GenAiAgentRag(
    name="support-rag",
    compartment_id=compartment_id,
    namespace=namespace,
)
rag.export()
```

**What gets created:**

| Resource | Purpose |
|----------|---------|
| `oci.objectstorage.Bucket` | Private document store for RAG source files |
| `oci.generativeai.AgentKnowledgeBase` | OCI-managed vector index (no OpenSearch cluster to provision) |
| `oci.generativeai.AgentDataSource` | Wires the bucket to the knowledge base |
| `oci.generativeai.AgentAgent` | The AI agent |
| `oci.generativeai.AgentTool` | RAG tool connecting the agent to the knowledge base |
| `oci.generativeai.AgentAgentEndpoint` | Invocation endpoint (citations enabled) |

---

## Using an existing bucket

If you already have an Object Storage bucket with documents, pass its name — the spell skips bucket creation and uses yours instead:

```python
rag = GenAiAgentRag(
    name="support-rag",
    compartment_id=compartment_id,
    namespace=namespace,
    bucket_name="my-existing-docs-bucket",
)
rag.export()
```

---

## Adding a welcome message

Set a natural-language description that end-users see when they open a chat session:

```python
rag = GenAiAgentRag(
    name="support-rag",
    compartment_id=compartment_id,
    namespace=namespace,
    welcome_message="Hi! I can answer questions about our product documentation.",
)
```

---

## Uploading documents

After deploying, upload documents to the bucket to populate the knowledge base. Supported formats include PDF, DOCX, TXT, and HTML.

```bash
# Get the bucket name from stack outputs
BUCKET=$(pulumi stack output support_rag_document_bucket_name)

# Upload a document
oci os object put \
  --namespace <your-namespace> \
  --bucket-name "$BUCKET" \
  --file ./docs/user-guide.pdf \
  --name user-guide.pdf
```

Then trigger a data ingestion job in the OCI Console under **Generative AI → Agents → Knowledge Bases → Data Sources → Sync**.

---

## Invoking the agent

Use the OCI SDK or REST API with the endpoint OCID from stack outputs:

```python
import oci

config = oci.config.from_file()
endpoint_id = "<your-endpoint-ocid>"  # from stack output

agent_client = oci.generative_ai_agent_runtime.GenerativeAiAgentRuntimeClient(config)

response = agent_client.chat(
    agent_endpoint_id=endpoint_id,
    chat_details=oci.generative_ai_agent_runtime.models.ChatDetails(
        user_message="What are the system requirements?",
        should_stream=False,
    ),
)
print(response.data.message.content[0].text)
```

---

## Outputs

`export()` publishes the following stack outputs:

| Output | Description |
|--------|-------------|
| `{name}_endpoint_id` | OCID of the agent endpoint — primary invocation handle |
| `{name}_agent_id` | OCID of the agent |
| `{name}_knowledge_base_id` | OCID of the knowledge base |
| `{name}_document_bucket_name` | Name of the Object Storage bucket for RAG documents |

---

## Configuration reference

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `name` | Yes | — | Logical resource name |
| `compartment_id` | Yes | — | OCI compartment OCID |
| `namespace` | Yes | — | OCI tenancy Object Storage namespace |
| `bucket_name` | No | `None` | Existing bucket name; if omitted a new bucket is created |
| `welcome_message` | No | `None` | Agent greeting shown at the start of a chat session |
