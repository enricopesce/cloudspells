"""Unit tests for GenAiAgentRag spell."""

import unittest

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import set_mocks

set_mocks()

# Import AFTER mocks are set
from cloudspells.providers.oci.genai_agent_rag import GenAiAgentRag

_COMPARTMENT = "ocid1.compartment.oc1..test"
_NAMESPACE = "testtenancy"


class TestGenAiAgentRag(unittest.TestCase):
    """Test cases for GenAiAgentRag spell."""

    @pulumi.runtime.test
    def test_creates_knowledge_base(self):
        """Test that a Knowledge Base resource is created."""
        rag = GenAiAgentRag(
            name="test-rag",
            compartment_id=_COMPARTMENT,
            namespace=_NAMESPACE,
            stack_name="test",
        )

        def check(kb_id: str) -> None:
            self.assertIsNotNone(kb_id)
            self.assertIn("test", kb_id)

        return rag.knowledge_base.id.apply(check)

    @pulumi.runtime.test
    def test_creates_endpoint(self):
        """Test that an Agent Endpoint resource is created."""
        rag = GenAiAgentRag(
            name="test-rag",
            compartment_id=_COMPARTMENT,
            namespace=_NAMESPACE,
            stack_name="test",
        )

        def check(ep_id: str) -> None:
            self.assertIsNotNone(ep_id)

        return rag.endpoint.id.apply(check)

    @pulumi.runtime.test
    def test_endpoint_id_output(self):
        """Test that endpoint_id Output resolves to a non-empty string."""
        rag = GenAiAgentRag(
            name="test-rag",
            compartment_id=_COMPARTMENT,
            namespace=_NAMESPACE,
            stack_name="test",
        )

        def check(ep_id: str) -> None:
            self.assertIsNotNone(ep_id)
            self.assertGreater(len(ep_id), 0)

        return rag.endpoint_id.apply(check)

    def test_creates_bucket_when_no_bucket_name(self) -> None:
        """Test that a bucket is created when bucket_name is not supplied."""
        rag = GenAiAgentRag(
            name="test-rag-newbucket",
            compartment_id=_COMPARTMENT,
            namespace=_NAMESPACE,
            stack_name="test",
        )
        self.assertIsNotNone(rag.bucket)

    def test_no_bucket_created_when_bucket_name_given(self) -> None:
        """Test that bucket is None when an existing bucket_name is supplied."""
        rag = GenAiAgentRag(
            name="test-rag-existing",
            compartment_id=_COMPARTMENT,
            namespace=_NAMESPACE,
            bucket_name="my-existing-bucket",
            stack_name="test",
        )
        self.assertIsNone(rag.bucket)

    @pulumi.runtime.test
    def test_document_bucket_name_resolves_for_existing_bucket(self):
        """Test that document_bucket_name resolves to the provided bucket name."""
        rag = GenAiAgentRag(
            name="test-rag-existing",
            compartment_id=_COMPARTMENT,
            namespace=_NAMESPACE,
            bucket_name="my-existing-bucket",
            stack_name="test",
        )

        def check(name: str) -> None:
            self.assertEqual(name, "my-existing-bucket")

        return rag.document_bucket_name.apply(check)

    @pulumi.runtime.test
    def test_resource_names_use_namer(self):
        """Test that bucket and KB names follow the ResourceNamer pattern."""
        rag = GenAiAgentRag(
            name="my-rag",
            compartment_id=_COMPARTMENT,
            namespace=_NAMESPACE,
            stack_name="prod",
        )

        def check_bucket(name: str) -> None:
            self.assertIn("prod", name)
            self.assertIn("my-rag", name)
            self.assertIn("docs", name)

        def check_kb(kb_id: str) -> None:
            self.assertIn("my-rag", kb_id)

        rag.bucket.name.apply(check_bucket)  # type: ignore[union-attr]
        return rag.knowledge_base.id.apply(check_kb)

    @pulumi.runtime.test
    def test_agent_id_output(self):
        """Test that agent_id Output is set."""
        rag = GenAiAgentRag(
            name="test-rag",
            compartment_id=_COMPARTMENT,
            namespace=_NAMESPACE,
            stack_name="test",
        )

        def check(agent_id: str) -> None:
            self.assertIsNotNone(agent_id)

        return rag.agent_id.apply(check)

    @pulumi.runtime.test
    def test_knowledge_base_id_output(self):
        """Test that knowledge_base_id Output is set."""
        rag = GenAiAgentRag(
            name="test-rag",
            compartment_id=_COMPARTMENT,
            namespace=_NAMESPACE,
            stack_name="test",
        )

        def check(kb_id: str) -> None:
            self.assertIsNotNone(kb_id)

        return rag.knowledge_base_id.apply(check)

    @pulumi.runtime.test
    def test_getter_methods(self):
        """Test that all getter methods return non-None Outputs."""
        rag = GenAiAgentRag(
            name="test-getters",
            compartment_id=_COMPARTMENT,
            namespace=_NAMESPACE,
            stack_name="test",
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        rag.get_endpoint_id().apply(check)
        rag.get_agent_id().apply(check)
        rag.get_knowledge_base_id().apply(check)
        return rag.get_document_bucket_name().apply(check)

    def test_export_does_not_raise(self) -> None:
        """Test that export() runs without raising."""
        rag = GenAiAgentRag(
            name="test-export",
            compartment_id=_COMPARTMENT,
            namespace=_NAMESPACE,
            stack_name="test",
        )
        rag.export()
