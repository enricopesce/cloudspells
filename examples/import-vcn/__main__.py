"""Deploy services into a VCN managed by another Pulumi stack.

Uses :class:`~blocks.vcn.network.VcnRef` to import a VCN from a separately-
managed stack (e.g. ``examples/vcn``) and then deploys a compute instance
into it.

No network resources are created or modified here.

.. warning::

    Security rules required by the services deployed here (Compute, etc.)
    must already exist in the source VCN stack.  ``VcnRef`` does not add or
    modify security lists.

Prerequisites
-------------
The referenced VCN stack must already have run ``pulumi up`` and export:

- ``vcn_id``
- ``cidr_block``
- ``public_subnet_id``
- ``private_subnet_id``
- ``public_subnet_cidr``
- ``private_subnet_cidr``
- ``public_security_list_id``
- ``private_security_list_id``

All eight values are exported by the ``examples/vcn`` stack.

Quick start
-----------
.. code-block:: bash

    cd examples/import-vcn
    pulumi stack init <stack-name>
    pulumi config set compartment_ocid  <COMPARTMENT_OCID>
    pulumi config set vcn_stack         <STACK_REFERENCE>

Stack reference format
----------------------
- Pulumi Cloud:       ``"<organization>/<project>/<stack>"``
- Local file backend: ``"<project>/<stack>"``
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

import pulumi
from providers.oci.network import VcnRef
from providers.oci.compute import ComputeInstance

config: pulumi.Config = pulumi.Config()
compartment_id: str = config.require("compartment_ocid")
vcn_stack: str = config.require("vcn_stack")

ssh_key: str | None = config.get("ssh_key") or None

vcn: VcnRef = VcnRef.from_stack_reference(vcn_stack)

instance: ComputeInstance = ComputeInstance(
    name="app-server",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
)

instance.export()
