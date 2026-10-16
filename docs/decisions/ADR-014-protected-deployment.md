# ADR-014 — Protected synthetic deployment

Date: 2026-10-16. Status: implemented locally; Railway deployment unverified.

Public deployment cannot reuse the local demo authentication or enable local
preview in production. A full corporate identity integration requires an IdP
that is not configured in this repository. For an isolated synthetic technical
demonstration, use operator-issued private bearer credentials with 256 bits of
randomness, SHA-256 hashes only in PostgreSQL, a maximum seven-day lifetime,
revocation and active-principal checks on every authenticated request.

Credentials are generated offline, saved only to exclusive 0600 files and never
issued by a public endpoint. Backend database roles/permissions remain the
authorization authority. The bootstrap manifest contains hashes, never tokens;
legacy demo token columns receive discarded random values. Known local tokens
are ignored by the deployment authentication path. No credentials are issued
for reserved evaluation principals. The frontend retains entered credentials
only in memory and sends them over HTTPS through its same-origin proxy.

`ENABLE_PUBLISHED_RUNTIME` requires private credential authentication. Production
continues rejecting `ENABLE_LOCAL_RUNTIME` and `ENABLE_DEMO_AUTH`. Public requests
can only execute a published version through the existing exact-hash approval
gate and invocation grants. Trusted evaluation execution remains internal to the
evaluation runner; no public request can set its evaluation ID/channel.
Evaluations still use isolated synthetic invoices and real authorization.

Railway IaC declares exactly three services and one PostgreSQL volume. Docker
build contexts remain at repository root. The API default Docker stage is now
production, rather than the final test stage. Predeploy runs only Alembic.
Provisioning is an explicit offline operator action, never an automatic deploy
side effect. `provision-identities` requires a hash-only manifest declaring fixed
least-privilege roles/permissions; existing identities and credentials cannot be
overwritten, reactivated or extended. The separate `load` operation creates data
only, with no users, tokens, invocation/retrieval grants, agent approvals or
publications. An immutable audit receipt makes replay read-only; a transaction
and savepoints roll back the entire dataset on ingestion failure. Reserved
resource collisions fail without overwriting. An explicit `revoke-access`
disables only the managed demonstration identities and revokes their credentials,
including rotations, while retaining history. See
[production demo bootstrap](../production-demo-bootstrap.md).
The initial generator is deterministic and explicitly labeled. Embeddings are
the existing pinned real local model; no paid model credentials are copied.

Trade-offs: private bearer credentials require secure manual distribution and
rotation, and provide no SSO/MFA or login rate limiting. This does not certify
enterprise production readiness. PostgreSQL app/migration credentials are not
yet separated; backups, recovery, availability and abuse controls need separate
validation. Railway itself must still be authenticated, planned and deployed
by the account owner, then verified through public URLs and the UI smoke test.
