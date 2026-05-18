"""VCN + ScalableWorkload example — autoscaling instance pool with load balancer."""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci.autoscale import ScalableWorkload
from cloudspells.providers.oci.network import Vcn

config = Config()
compartment_id: str = config.require("compartment_ocid")
vcn_cidr_block: str = config.get("vcn_cidr_block") or "10.0.0.0/18"

# Cloud-init script to install and start nginx (Oracle Linux 8)
user_data_script = """#!/bin/bash
set -e

# Install and enable nginx
dnf install -y nginx
systemctl enable nginx
systemctl start nginx

# Open port 80 through firewalld (required on Oracle Linux)
firewall-cmd --permanent --add-service=http
firewall-cmd --reload

# Create health check endpoint for load balancer
echo "OK" > /usr/share/nginx/html/health

# Create a simple index page (hostname evaluated at boot time)
INSTANCE_HOSTNAME=$(hostname)
cat > /usr/share/nginx/html/index.html <<EOF
<!DOCTYPE html>
<html>
<head><title>OCI Autoscale Demo</title></head>
<body>
<h1>Instance: ${INSTANCE_HOSTNAME}</h1>
<p>This instance is part of an autoscaling pool.</p>
</body>
</html>
EOF
"""

# Create VCN
vcn: Vcn = Vcn(
    name="scalable",
    compartment_id=compartment_id,
    cidr_block=vcn_cidr_block,
)

# ScalableWorkload: minimal configuration with sensible defaults.
# Defaults: VM.Standard.E4.Flex (1 OCPU / 16GB), 1-5 instances,
# HTTP load balancer on port 80, CPU-based autoscaling (scale out >80%, scale in <20%).
scalable_pool: ScalableWorkload = ScalableWorkload(
    name="web-pool",
    compartment_id=compartment_id,
    vcn=vcn,
    image_id=config.require("image_ocid"),
    ssh_public_key=config.get("ssh_key"),
    cloud_init_script=user_data_script,
    max_instances=3,
)

vcn.export()
scalable_pool.export()
