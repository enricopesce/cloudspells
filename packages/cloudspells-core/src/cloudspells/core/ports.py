"""Well-known TCP/UDP port constants for use in security rules.

These are cloud-neutral integers suitable for any provider's firewall
model (OCI SecurityList, AWS Security Group, GCP Firewall Rule, etc.).
Import them here rather than from a provider-specific module so that
code in `core.abstractions` and provider-agnostic spell logic remains
free of provider dependencies.

Exports:
    HTTP, HTTPS, HTTP_ALT, HTTPS_ALT: Web ports.
    SSH, RDP: Remote access ports.
    MYSQL, POSTGRES, ORACLE_DB, MSSQL, CASSANDRA, MONGODB: Database ports.
    REDIS, MEMCACHED, RABBITMQ, KAFKA: Caching and messaging ports.
    NFS, SMB, LDAP, LDAPS: File and directory service ports.
    ELASTICSEARCH: Search port.
    SMTP, SMTPS: Mail ports.
    DNS: DNS query port.
"""

# ── Web / access ──────────────────────────────────────────────────────────────

HTTP: int = 80
"""Standard HTTP port."""

HTTPS: int = 443
"""Standard HTTPS port."""

HTTP_ALT: int = 8080
"""Alternate HTTP port commonly used by application servers."""

HTTPS_ALT: int = 8443
"""Alternate HTTPS port commonly used by application servers."""

SSH: int = 22
"""Standard SSH port."""

RDP: int = 3389
"""Remote Desktop Protocol port."""

# ── Databases ─────────────────────────────────────────────────────────────────

MYSQL: int = 3306
"""Default MySQL / Aurora port."""

POSTGRES: int = 5432
"""Default PostgreSQL port."""

ORACLE_DB: int = 1521
"""Default Oracle Database listener port."""

MSSQL: int = 1433
"""Default Microsoft SQL Server port."""

CASSANDRA: int = 9042
"""Default Apache Cassandra CQL native transport port."""

MONGODB: int = 27017
"""Default MongoDB port."""

# ── Caching / messaging ───────────────────────────────────────────────────────

REDIS: int = 6379
"""Default Redis port."""

MEMCACHED: int = 11211
"""Default Memcached port."""

RABBITMQ: int = 5672
"""Default RabbitMQ AMQP port."""

KAFKA: int = 9092
"""Default Apache Kafka broker port."""

# ── File / directory services ─────────────────────────────────────────────────

NFS: int = 2049
"""Network File System (NFSv3/v4) port."""

SMB: int = 445
"""SMB / CIFS (Windows file sharing) port."""

LDAP: int = 389
"""Lightweight Directory Access Protocol port."""

LDAPS: int = 636
"""LDAP over TLS port."""

# ── Search / observability ────────────────────────────────────────────────────

ELASTICSEARCH: int = 9200
"""Elasticsearch HTTP REST API port."""

# ── Mail ──────────────────────────────────────────────────────────────────────

SMTP: int = 25
"""SMTP relay port."""

SMTPS: int = 587
"""SMTP submission (STARTTLS) port."""

# ── DNS ───────────────────────────────────────────────────────────────────────

DNS: int = 53
"""DNS query port (TCP for zone transfers; UDP for queries)."""

__all__ = [
    # Web / access
    "HTTP",
    "HTTPS",
    "HTTP_ALT",
    "HTTPS_ALT",
    "SSH",
    "RDP",
    # Databases
    "MYSQL",
    "POSTGRES",
    "ORACLE_DB",
    "MSSQL",
    "CASSANDRA",
    "MONGODB",
    # Caching / messaging
    "REDIS",
    "MEMCACHED",
    "RABBITMQ",
    "KAFKA",
    # File / directory
    "NFS",
    "SMB",
    "LDAP",
    "LDAPS",
    # Search / observability
    "ELASTICSEARCH",
    # Mail
    "SMTP",
    "SMTPS",
    # DNS
    "DNS",
]
