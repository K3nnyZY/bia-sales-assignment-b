"""Knowledge Registry, immutable document evidence and pgvector."""

from alembic import op

revision = "0005_knowledge_rag"
down_revision = "0004_quality_governance"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
    op.execute(
        """
CREATE TABLE knowledge_collections (
	id VARCHAR(80) NOT NULL,
	name VARCHAR(160) NOT NULL,
	owner_id VARCHAR(80) NOT NULL,
	classification VARCHAR(20) NOT NULL,
	enabled BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_knowledge_collections PRIMARY KEY (id),
        CONSTRAINT ck_knowledge_collections_classification CHECK (classification IN
('internal','restricted')),
	CONSTRAINT fk_knowledge_collections_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id)
)

"""
    )
    op.execute(
        """
CREATE TABLE knowledge_grants (
	collection_id VARCHAR(80) NOT NULL,
	user_id VARCHAR(80) NOT NULL,
	clearance VARCHAR(20) NOT NULL,
	enabled BOOLEAN NOT NULL,
	CONSTRAINT pk_knowledge_grants PRIMARY KEY (collection_id, user_id),
	CONSTRAINT ck_knowledge_grants_clearance CHECK (clearance IN ('internal','restricted')),
        CONSTRAINT fk_knowledge_grants_collection_id_knowledge_collections FOREIGN
KEY(collection_id) REFERENCES knowledge_collections (id),
	CONSTRAINT fk_knowledge_grants_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
)

"""
    )
    op.execute(
        """
CREATE TABLE knowledge_objects (
	key VARCHAR(64) NOT NULL,
	content BYTEA NOT NULL,
	CONSTRAINT pk_knowledge_objects PRIMARY KEY (key),
	CONSTRAINT ck_knowledge_objects_size CHECK (octet_length(content) <= 2097152)
)

"""
    )
    op.execute(
        """
CREATE TABLE knowledge_documents (
	id VARCHAR(80) NOT NULL,
	collection_id VARCHAR(80) NOT NULL,
	title VARCHAR(160) NOT NULL,
	owner_id VARCHAR(80) NOT NULL,
	next_version INTEGER NOT NULL,
	CONSTRAINT pk_knowledge_documents PRIMARY KEY (id),
	CONSTRAINT uq_knowledge_documents_id UNIQUE (id, collection_id),
        CONSTRAINT fk_knowledge_documents_collection_id_knowledge_collections FOREIGN
KEY(collection_id) REFERENCES knowledge_collections (id),
	CONSTRAINT fk_knowledge_documents_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id)
)

"""
    )
    op.execute(
        "CREATE INDEX ix_knowledge_documents_collection_id ON knowledge_documents (collection_id)"
    )
    op.execute(
        """
CREATE TABLE knowledge_versions (
	document_id VARCHAR(80) NOT NULL,
	number INTEGER NOT NULL,
	collection_id VARCHAR(80) NOT NULL,
	object_key VARCHAR(64) NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	filename VARCHAR(160) NOT NULL,
	source VARCHAR(240) NOT NULL,
	valid_from DATE NOT NULL,
	valid_to DATE NOT NULL,
	status VARCHAR(20) NOT NULL,
	approval VARCHAR(20) NOT NULL,
	embedding_version VARCHAR(200) NOT NULL,
	pipeline_version VARCHAR(40) NOT NULL,
	chunk_count INTEGER NOT NULL,
	error_code VARCHAR(80),
	created_by VARCHAR(80) NOT NULL,
	approved_by VARCHAR(80),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_knowledge_versions PRIMARY KEY (document_id, number),
	CONSTRAINT uq_knowledge_version_scope UNIQUE (document_id, number, collection_id),
        CONSTRAINT uq_knowledge_collection_content UNIQUE (collection_id, content_hash,
valid_from, valid_to),
        CONSTRAINT fk_knowledge_versions_document_id_knowledge_documents FOREIGN
KEY(document_id, collection_id) REFERENCES knowledge_documents (id, collection_id),
	CONSTRAINT ck_knowledge_versions_version_dates CHECK (number >= 1 AND valid_to >= valid_from),
        CONSTRAINT ck_knowledge_versions_status CHECK (status IN
('pending','ready','failed','rejected')),
        CONSTRAINT ck_knowledge_versions_approval CHECK (approval IN
('pending','approved','revoked')),
        CONSTRAINT ck_knowledge_versions_ready_approval CHECK (approval <> 'approved' OR status
= 'ready'),
        CONSTRAINT fk_knowledge_versions_object_key_knowledge_objects FOREIGN KEY(object_key)
REFERENCES knowledge_objects (key),
        CONSTRAINT fk_knowledge_versions_created_by_users FOREIGN KEY(created_by) REFERENCES
users (id),
        CONSTRAINT fk_knowledge_versions_approved_by_users FOREIGN KEY(approved_by) REFERENCES
users (id)
)

"""
    )
    op.execute(
        "CREATE INDEX ix_knowledge_versions_collection_id ON knowledge_versions (collection_id)"
    )
    op.execute(
        """
CREATE TABLE knowledge_chunks (
	document_id VARCHAR(80) NOT NULL,
	version_number INTEGER NOT NULL,
	ordinal INTEGER NOT NULL,
	collection_id VARCHAR(80) NOT NULL,
	content TEXT NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	char_start INTEGER NOT NULL,
	char_end INTEGER NOT NULL,
	embedding VECTOR(256) NOT NULL,
	CONSTRAINT pk_knowledge_chunks PRIMARY KEY (document_id, version_number, ordinal),
        CONSTRAINT fk_knowledge_chunks_document_id_knowledge_versions FOREIGN KEY(document_id,
version_number, collection_id) REFERENCES knowledge_versions (document_id, number,
collection_id),
        CONSTRAINT ck_knowledge_chunks_offsets CHECK (ordinal >= 0 AND char_start >= 0 AND
char_end > char_start)
)

"""
    )
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_lexical ON knowledge_chunks "
        "USING gin (to_tsvector('spanish', content))"
    )
    op.execute(
        """
CREATE TABLE knowledge_searches (
	id VARCHAR(80) NOT NULL,
	caller_id VARCHAR(80) NOT NULL,
	run_id VARCHAR(40),
	query_hash VARCHAR(64) NOT NULL,
	as_of DATE NOT NULL,
	collection_ids JSONB NOT NULL,
	"references" JSONB NOT NULL,
	embedding_version VARCHAR(200) NOT NULL,
	mode VARCHAR(40) NOT NULL,
	duration_ms INTEGER NOT NULL,
	error_code VARCHAR(80),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_knowledge_searches PRIMARY KEY (id),
	CONSTRAINT fk_knowledge_searches_caller_id_users FOREIGN KEY(caller_id) REFERENCES users (id),
        CONSTRAINT fk_knowledge_searches_run_id_agent_runs FOREIGN KEY(run_id) REFERENCES
agent_runs (id)
)

"""
    )
    op.execute("CREATE INDEX ix_knowledge_searches_run_id ON knowledge_searches (run_id)")

    op.execute(
        "ALTER TABLE knowledge_objects ADD CONSTRAINT ck_knowledge_objects_hash "
        "CHECK (key = encode(sha256(content), 'hex'))"
    )
    op.execute(
        "ALTER TABLE knowledge_versions ADD CONSTRAINT ck_knowledge_versions_object_hash "
        "CHECK (content_hash = object_key)"
    )
    op.execute("""
    CREATE FUNCTION protect_knowledge() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'knowledge history is immutable'; END IF;
      IF TG_TABLE_NAME IN ('knowledge_chunks', 'knowledge_objects', 'knowledge_searches') THEN
        RAISE EXCEPTION 'knowledge evidence and logs are immutable';
      ELSIF TG_TABLE_NAME = 'knowledge_documents' THEN
        IF (to_jsonb(NEW) - 'next_version') IS DISTINCT FROM (to_jsonb(OLD) - 'next_version')
THEN
          RAISE EXCEPTION 'document identity is immutable'; END IF;
      ELSIF TG_TABLE_NAME = 'knowledge_collections' THEN
        IF (to_jsonb(NEW) - 'enabled') IS DISTINCT FROM (to_jsonb(OLD) - 'enabled') THEN
          RAISE EXCEPTION 'collection policy is immutable'; END IF;
      ELSIF TG_TABLE_NAME = 'knowledge_versions' THEN
        IF (to_jsonb(NEW) - ARRAY['status','approval','approved_by','chunk_count','error_code'])
          IS DISTINCT FROM (to_jsonb(OLD) -
ARRAY['status','approval','approved_by','chunk_count','error_code']) THEN
          RAISE EXCEPTION 'document version metadata is immutable'; END IF;
        IF OLD.status IN ('ready','rejected') AND
          (to_jsonb(NEW) - ARRAY['approval','approved_by']) IS DISTINCT FROM
          (to_jsonb(OLD) - ARRAY['approval','approved_by']) THEN
          RAISE EXCEPTION 'ingested document version is immutable'; END IF;
        IF OLD.approval = 'revoked' AND NEW.approval <> 'revoked' THEN
          RAISE EXCEPTION 'revocation is terminal'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    """)
    for table in [
        "knowledge_objects",
        "knowledge_documents",
        "knowledge_collections",
        "knowledge_versions",
        "knowledge_chunks",
        "knowledge_searches",
    ]:
        op.execute(
            f"CREATE TRIGGER protect_{table} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION protect_knowledge()"
        )
    op.execute("""
    CREATE FUNCTION check_knowledge_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE v knowledge_versions%ROWTYPE;
    BEGIN
      SELECT * INTO v FROM knowledge_versions WHERE document_id=NEW.document_id AND
number=NEW.version_number FOR SHARE;
      IF v.status <> 'pending' AND v.status <> 'failed' THEN
        RAISE EXCEPTION 'cannot append chunks to a completed ingestion'; END IF;
      IF NEW.content_hash <> encode(sha256(convert_to(NEW.content, 'UTF8')), 'hex') THEN
        RAISE EXCEPTION 'chunk hash mismatch'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER check_knowledge_chunk BEFORE INSERT ON knowledge_chunks
      FOR EACH ROW EXECUTE FUNCTION check_knowledge_evidence();
    CREATE FUNCTION check_knowledge_version() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE v knowledge_versions%ROWTYPE;
    BEGIN
      SELECT * INTO v FROM knowledge_versions WHERE document_id=NEW.document_id AND
number=NEW.number;
      IF v.status = 'ready' AND (v.chunk_count < 1 OR v.chunk_count <>
        (SELECT count(*) FROM knowledge_chunks WHERE document_id=v.document_id AND
version_number=v.number)) THEN
        RAISE EXCEPTION 'ready documents require complete chunks'; END IF;
      IF v.approval = 'approved' AND NOT EXISTS (
        SELECT 1 FROM users WHERE id=v.approved_by AND active AND role IN
('administrator','reviewer')) THEN
        RAISE EXCEPTION 'approval requires an authorized reviewer'; END IF;
      RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER check_knowledge_ready AFTER INSERT OR UPDATE ON knowledge_versions
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_knowledge_version();
    """)


def downgrade():
    op.execute("DROP FUNCTION check_knowledge_version() CASCADE")
    op.execute("DROP FUNCTION check_knowledge_evidence() CASCADE")
    op.execute("DROP FUNCTION protect_knowledge() CASCADE")
    op.drop_table("knowledge_searches")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_versions")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_objects")
    op.drop_table("knowledge_grants")
    op.drop_table("knowledge_collections")
    # Shared vector extension is retained: other schemas may use it.
