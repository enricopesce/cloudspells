"""OCI Generative AI Agent RAG spell.

Exports `GenAiAgentRag`, a single-call spell that provisions a complete
Retrieval-Augmented Generation (RAG) pipeline on OCI Generative AI Service:

- **Object Storage bucket** — document store for source materials (created or
  supplied by the caller).
- **Knowledge Base** — OCI-managed OpenSearch vector index; no cluster
  provisioning required.
- **Data Source** — wires the bucket to the Knowledge Base so ingestion jobs
  can run.
- **Agent** — the LLM-backed conversational agent.
- **RAG Tool** — attaches the Knowledge Base to the Agent using the modern
  `AgentTool` API.
- **Agent Endpoint** — the invocation endpoint returned to callers; citations
  are enabled by default.

Usage:

```python
from cloudspells.providers.oci import GenAiAgentRag

rag = GenAiAgentRag(
    name="support-rag",
    compartment_id=compartment_id,
    namespace=namespace,          # Object Storage tenancy namespace
)
rag.export()                      # publishes endpoint_id, agent_id, etc.
```

To supply an existing bucket instead of creating one:

```python
rag = GenAiAgentRag(
    name="support-rag",
    compartment_id=compartment_id,
    namespace=namespace,
    bucket_name="my-existing-docs-bucket",
)
```
"""

from __future__ import annotations

import pulumi
import pulumi_oci as oci
from cloudspells.core.base import BaseResource

__all__ = ["GenAiAgentRag"]


class GenAiAgentRag(BaseResource):
    """Provisions a complete OCI Generative AI Agent RAG architecture.

    Creates an Object Storage bucket for documents, a Knowledge Base with
    OCI-managed vector indexing, a Data Source wiring the bucket to the Knowledge
    Base, an Agent, a RAG Tool, and an Agent Endpoint — all from a single
    opinionated call.

    Args:
        name: Logical resource name.
        compartment_id: OCI compartment OCID.
        namespace: Object Storage namespace for the tenancy.
        bucket_name: Name of an existing bucket to use for RAG documents. When
            `None` (the default) a new private bucket is created inside the spell.
        welcome_message: Optional natural-language description of the agent's
            purpose, shown to end-users.
        stack_name: Pulumi stack name override (used in tests).
        opts: Pulumi resource options.

    Attributes:
        bucket: The Object Storage bucket created by this spell, or `None` if an
            existing bucket was supplied via `bucket_name`.
        knowledge_base: The OCI Generative AI Knowledge Base resource.
        data_source: The OCI Generative AI Data Source resource.
        agent: The OCI Generative AI Agent resource.
        rag_tool: The OCI Generative AI RAG Tool resource.
        endpoint: The OCI Generative AI Agent Endpoint resource.
        endpoint_id: OCID of the agent endpoint (primary invocation handle).
        agent_id: OCID of the agent.
        knowledge_base_id: OCID of the knowledge base.
        document_bucket_name: Name of the Object Storage bucket used for RAG documents.

    Example:
        ```python
        from cloudspells.providers.oci import GenAiAgentRag

        rag = GenAiAgentRag(
            name="support-rag",
            compartment_id=compartment_id,
            namespace=namespace,
        )
        rag.export()
        ```
    """

    bucket: oci.objectstorage.Bucket | None
    knowledge_base: oci.generativeai.AgentKnowledgeBase
    data_source: oci.generativeai.AgentDataSource
    agent: oci.generativeai.AgentAgent
    rag_tool: oci.generativeai.AgentTool
    endpoint: oci.generativeai.AgentAgentEndpoint
    endpoint_id: pulumi.Output[str]
    agent_id: pulumi.Output[str]
    knowledge_base_id: pulumi.Output[str]
    document_bucket_name: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        namespace: pulumi.Input[str],
        bucket_name: pulumi.Input[str] | None = None,
        welcome_message: str | None = None,
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create an OCI Generative AI Agent RAG stack.

        Args:
            name: Logical name for the RAG agent resources.
            compartment_id: OCID of the OCI compartment to deploy into.
            namespace: Object Storage namespace for the tenancy.
            bucket_name: Existing private bucket name for source documents, or
                `None` to create one.
            welcome_message: Optional end-user welcome text for the agent.
            stack_name: Pulumi stack name. Defaults to `pulumi.get_stack()`
                when `None`.
            opts: Pulumi resource options forwarded to the component.
        """
        super().__init__("custom:genai:GenAiAgentRag", name, compartment_id, stack_name, opts)

        child_opts = pulumi.ResourceOptions(parent=self)

        # 1. Document bucket — create or reference existing
        if bucket_name is None:
            docs_name = self.create_resource_name("docs")
            self.bucket = oci.objectstorage.Bucket(
                docs_name,
                compartment_id=compartment_id,
                namespace=namespace,
                name=docs_name,
                access_type="NoPublicAccess",
                storage_tier="Standard",
                freeform_tags=self.create_freeform_tags(docs_name, "bucket"),
                opts=child_opts,
            )
            resolved_bucket_name: pulumi.Output[str] = self.bucket.name
        else:
            self.bucket = None
            resolved_bucket_name = pulumi.Output.from_input(bucket_name)

        self.document_bucket_name = resolved_bucket_name

        # 2. Knowledge Base — OCI-managed OpenSearch index (no cluster_id = service-managed)
        kb_name = self.create_resource_name("kb")
        self.knowledge_base = oci.generativeai.AgentKnowledgeBase(
            kb_name,
            compartment_id=compartment_id,
            index_config=oci.generativeai.AgentKnowledgeBaseIndexConfigArgs(
                index_config_type="OCI_OPEN_SEARCH_INDEX_CONFIG",
            ),
            display_name=kb_name,
            freeform_tags=self.create_freeform_tags(kb_name, "knowledge-base"),
            opts=child_opts,
        )
        self.knowledge_base_id = self.knowledge_base.id

        # 3. Data Source — Object Storage bucket → Knowledge Base
        ds_name = self.create_resource_name("ds")
        self.data_source = oci.generativeai.AgentDataSource(
            ds_name,
            compartment_id=compartment_id,
            knowledge_base_id=self.knowledge_base.id,
            data_source_config=oci.generativeai.AgentDataSourceDataSourceConfigArgs(
                data_source_config_type="OCI_OBJECT_STORAGE_DATA_SOURCE_CONFIG",
                object_storage_prefixes=[
                    oci.generativeai.AgentDataSourceDataSourceConfigObjectStoragePrefixArgs(
                        namespace=namespace,
                        bucket=resolved_bucket_name,
                    )
                ],
            ),
            display_name=ds_name,
            freeform_tags=self.create_freeform_tags(ds_name, "data-source"),
            opts=child_opts,
        )

        # 4. Agent
        agent_name = self.create_resource_name("agent")
        self.agent = oci.generativeai.AgentAgent(
            agent_name,
            compartment_id=compartment_id,
            display_name=agent_name,
            welcome_message=welcome_message,
            freeform_tags=self.create_freeform_tags(agent_name, "agent"),
            opts=child_opts,
        )
        self.agent_id = self.agent.id

        # 5. RAG Tool — uses AgentTool (modern API; AgentAgent.knowledge_base_ids is deprecated)
        tool_name = self.create_resource_name("rag-tool")
        self.rag_tool = oci.generativeai.AgentTool(
            tool_name,
            agent_id=self.agent.id,
            compartment_id=compartment_id,
            description="RAG retrieval over the knowledge base",
            tool_config=oci.generativeai.AgentToolToolConfigArgs(
                tool_config_type="RAG_TOOL_CONFIG",
                knowledge_base_configs=[
                    oci.generativeai.AgentToolToolConfigKnowledgeBaseConfigArgs(
                        knowledge_base_id=self.knowledge_base.id,
                    )
                ],
            ),
            display_name=tool_name,
            freeform_tags=self.create_freeform_tags(tool_name, "tool"),
            opts=child_opts,
        )

        # 6. Agent Endpoint
        ep_name = self.create_resource_name("endpoint")
        self.endpoint = oci.generativeai.AgentAgentEndpoint(
            ep_name,
            agent_id=self.agent.id,
            compartment_id=compartment_id,
            display_name=ep_name,
            should_enable_citation=True,
            freeform_tags=self.create_freeform_tags(ep_name, "endpoint"),
            opts=child_opts,
        )
        self.endpoint_id = self.endpoint.id

        self.register_outputs({
            "endpoint_id": self.endpoint.id,
            "agent_id": self.agent.id,
            "knowledge_base_id": self.knowledge_base.id,
            "document_bucket_name": resolved_bucket_name,
        })

    def get_endpoint_id(self) -> pulumi.Output[str]:
        """Return the OCID of the agent endpoint.

        Returns:
            `pulumi.Output[str]` resolving to the agent endpoint OCID.
        """
        return self.endpoint_id

    def get_agent_id(self) -> pulumi.Output[str]:
        """Return the OCID of the agent.

        Returns:
            `pulumi.Output[str]` resolving to the agent OCID.
        """
        return self.agent_id

    def get_knowledge_base_id(self) -> pulumi.Output[str]:
        """Return the OCID of the knowledge base.

        Returns:
            `pulumi.Output[str]` resolving to the knowledge base OCID.
        """
        return self.knowledge_base_id

    def get_document_bucket_name(self) -> pulumi.Output[str]:
        """Return the Object Storage bucket used for RAG documents.

        Returns:
            `pulumi.Output[str]` resolving to the bucket name.
        """
        return self.document_bucket_name

    def export(self) -> None:
        """Export agent endpoint and supporting resource OCIDs.

        Publishes stack outputs named from the spell's logical name.
        """
        key = self.name.replace("-", "_")
        pulumi.export(f"{key}_endpoint_id", self.endpoint_id)
        pulumi.export(f"{key}_agent_id", self.agent_id)
        pulumi.export(f"{key}_knowledge_base_id", self.knowledge_base_id)
        pulumi.export(f"{key}_document_bucket_name", self.document_bucket_name)
