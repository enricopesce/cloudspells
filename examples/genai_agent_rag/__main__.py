"""Generative AI Agent RAG example.

Deploys a complete OCI Generative AI Agent RAG pipeline:

- `GenAiAgentRag`: provisions an Object Storage bucket for documents, a
  Knowledge Base backed by OCI-managed OpenSearch, a Data Source wiring the
  bucket to the Knowledge Base, an Agent, a RAG Tool, and an Agent Endpoint
  with citations enabled.

After deployment, upload PDF, DOCX, or TXT files to the document bucket and
trigger a data ingestion job in the OCI Console to populate the knowledge base
before invoking the endpoint.

The OCI tenancy namespace cannot be resolved automatically (CS-002) and must be
supplied via config.
"""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

import pulumi

from cloudspells.core import Config
from cloudspells.providers.oci import GenAiAgentRag

config = Config()
compartment_id: str = config.require("compartment_ocid")
namespace: str = config.require("namespace")

rag = GenAiAgentRag(
    name="support-rag",
    compartment_id=compartment_id,
    namespace=namespace,
    welcome_message="Hi! I can answer questions about our product documentation.",
)
rag.export()
