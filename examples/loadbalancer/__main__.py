"""VCN + LoadBalancer example — internet-facing HTTPS load balancer.

Deploys a public-subnet HTTPS load balancer that terminates TLS using a
certificate already uploaded to the OCI Load Balancer service.  HTTP traffic
on port 80 is automatically redirected to HTTPS (301).  Backend instances
(running on port 8080) are registered separately after deployment.

Prerequisites:
    Upload a TLS certificate to the OCI Load Balancer service in your
    compartment before running `pulumi up`.  Pass the certificate name
    via `pulumi config set certificate_name <name>`.
"""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci.loadbalancer import LoadBalancer
from cloudspells.providers.oci.network import Vcn

config = Config()
compartment_id: str = config.require("compartment_ocid")
vcn_cidr_block: str = config.get("vcn_cidr_block") or "10.0.0.0/18"
certificate_name: str = config.require("certificate_name")

# VCN — four-tier subnet layout (public, private, secure, management).
vcn: Vcn = Vcn(
    name="web",
    compartment_id=compartment_id,
    cidr_block=vcn_cidr_block,
)

# LoadBalancer — flexible-shape HTTPS LB in the public subnet.
# HTTP:80 redirects to HTTPS:443; backends are expected on port 8080.
lb: LoadBalancer = LoadBalancer(
    name="web-frontend",
    compartment_id=compartment_id,
    vcn=vcn,
    certificate_name=certificate_name,
    backend_port=8080,
)


vcn.export()
lb.export()
