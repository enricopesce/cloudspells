"""VCN + ScalableWorkload example — autoscaling instance pool with load balancer."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

import pulumi
import base64
from blocks.vcn.network import Vcn
from blocks.autoscale import ScalableWorkload

config: pulumi.Config = pulumi.Config()
compartment_id: str = config.require("compartment_ocid")
vcn_cidr_block: str = config.get("vcn_cidr_block") or "10.0.0.0/16"

# Cloud-init script to install and start nginx (Oracle Linux 8)
user_data_script = """#!/bin/bash
set -e

# Install and enable nginx
yum install -y --disablerepo='*' --enablerepo='ol8_appstream,ol8_baseos_latest' nginx
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

user_data_encoded = base64.b64encode(user_data_script.encode()).decode()

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
    ssh_public_key=config.get("ssh_key"),
    user_data=user_data_encoded,
    max_instances=3,
)

vcn.export()
scalable_pool.export()
