# syntax=docker/dockerfile:1.7

# Postgres 18 + pgvector base image for the ticket-rag service container.
#
# Layers:
#   BILL-12 — postgres + pgvector base + trust-auth init script.
#   BILL-16 — ticket_chunks schema (applied by the BILL-17 entrypoint, see below).
#   BILL-14 — Python 3.12 + FastAPI runtime + /healthz app.
#   BILL-15 — encoder + reranker model files baked at build time.
#   BILL-17 — single entrypoint orchestrating postgres + schema + uvicorn (this).
#
# WARNING — TRUST AUTH IS ON. Every connection method (Unix socket,
# IPv4, IPv6) is configured to accept any user without a password.
# This image is intended to run on 127.0.0.1 only, behind no network.
# Do not expose to any untrusted network.

# ----------------------------------------------------------------------
# Stage 1: Python 3.12 source. Debian 12 bookworm ships python3.11 only;
# the official python:3.12-slim-bookworm image is built on the same
# Debian 12 base, so /usr/local can be copied straight into the postgres
# image with matching glibc / OpenSSL ABIs.
# ----------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS python-stage

# ----------------------------------------------------------------------
# Stage 2: postgres+pgvector base with Python layered on top.
# ----------------------------------------------------------------------
FROM pgvector/pgvector:0.8.2-pg18

# POSTGRES_HOST_AUTH_METHOD=trust tells the upstream entrypoint to write
# host-based pg_hba entries as trust. The init script below overwrites
# pg_hba.conf wholesale to guarantee local-socket entries are also trust
# regardless of initdb defaults, and to add explicit IPv6 catch-alls.
ENV POSTGRES_HOST_AUTH_METHOD=trust

# Init script runs after initdb, before postgres starts accepting real
# connections — so the replaced pg_hba.conf applies on the post-init start.
COPY --chmod=0755 init-trust-auth.sh /docker-entrypoint-initdb.d/00-trust-auth.sh

# BILL-16 schema files. Applied by /entrypoint.sh (BILL-17) on every start,
# idempotently — every CREATE in schema/*.sql uses IF NOT EXISTS, which is
# a hard repo convention for any file landing under this directory. Future
# migrations land as additional schema/NNN_*.sql; the entrypoint picks them
# up in filename order.
#
# init-schema.sh is NOT copied to /docker-entrypoint-initdb.d/ anymore — the
# entrypoint applies schema directly. Doing both would just run the same SQL
# twice on first init (harmless because idempotent, but noisy).
COPY schema/ /docker-entrypoint-initdb.d/schema/

# Python 3.12 from the multi-stage source. /usr/local holds the interpreter,
# pip, and site-packages — copying it whole gives us a working Python without
# pulling deadsnakes or building from source.
COPY --from=python-stage /usr/local /usr/local
# Library dependency sentence-transformers needs at runtime; rest of the
# base image's apt state is left untouched.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Sanity-check that the Python copy is functional before pip runs.
RUN python3 --version && pip3 --version

# Pinned runtime deps. requirements.txt edits bust this layer; app code
# edits below do not.
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt

# BILL-15 — encoder + reranker baked at image-build time.
#
# Models are pre-fetched on the host into ./models/ by fetch-models.sh
# (pinned commit SHAs live there) and COPYed in here. Downloading inside
# the build via huggingface-cli stalled reliably on the Xet protocol path
# through Docker Desktop's VM NAT; host-side download bypasses that.
#
# onnx/ excluded from bge-m3 (~2.3 GB ONNX data, unused by sentence-transformers).
# imgs/ and assets/ excluded (documentation images only).
# NOTE: fp32 weights add ~4.54 GB; expected total image ~6 GB.
# See BILL-13 umbrella for the measured size.
COPY models/bge-m3 /models/bge-m3
COPY models/bge-reranker-v2-m3 /models/bge-reranker-v2-m3

ENV HF_HUB_OFFLINE=1

# FastAPI app — currently /healthz only. Real query endpoints land in future
# tickets under the BILL-13 umbrella.
COPY app/ /app/app/

EXPOSE 5432
EXPOSE 7777

# BILL-17 entrypoint: starts postgres via the upstream entrypoint, waits for
# readiness, re-applies schema idempotently, then launches uvicorn under a
# small shell-based supervisor. SIGTERM is propagated to both children with
# pg_ctl -m fast stop on postgres. See entrypoint.sh's header for the full
# process-supervisor rationale and failure-mode notes.
COPY --chmod=0755 entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD []
