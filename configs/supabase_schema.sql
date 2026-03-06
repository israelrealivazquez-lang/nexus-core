-- ============================================================
-- NEXUS BRAIN — Supabase Schema
-- Ejecutar en Supabase SQL Editor (supabase.com > SQL Editor)
-- ============================================================

-- Extension para vectores
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- Tabla: nexus_locks (State Lock para concurrencia multi-nodo)
-- ============================================================
CREATE TABLE IF NOT EXISTS nexus_locks (
    task_id VARCHAR(255) PRIMARY KEY,
    node_id VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    lock_ttl TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '1 hour'),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indice para busqueda rapida por status
CREATE INDEX IF NOT EXISTS idx_locks_status ON nexus_locks(status);
CREATE INDEX IF NOT EXISTS idx_locks_node ON nexus_locks(node_id);

-- ============================================================
-- Tabla: vector_knowledge (Embeddings + Chunks deduplicados)
-- ============================================================
CREATE TABLE IF NOT EXISTS vector_knowledge (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file VARCHAR(500) NOT NULL,
    source_type VARCHAR(50) DEFAULT 'unknown',
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL UNIQUE,
    embedding vector(1024),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indice IVFFlat para busqueda vectorial rapida
-- Nota: Crear DESPUES de insertar al menos 100 filas
-- CREATE INDEX idx_vector_cosine ON vector_knowledge
--   USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);

-- Indice para idempotencia por hash
CREATE INDEX IF NOT EXISTS idx_knowledge_hash ON vector_knowledge(content_hash);
CREATE INDEX IF NOT EXISTS idx_knowledge_source ON vector_knowledge(source_file);

-- ============================================================
-- Tabla: dead_letter_queue (Errores no recuperables)
-- ============================================================
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    error_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_name VARCHAR(255) NOT NULL,
    node_id VARCHAR(100),
    payload JSONB DEFAULT '{}',
    error_message TEXT,
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 3,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_dlq_task ON dead_letter_queue(task_name);
CREATE INDEX IF NOT EXISTS idx_dlq_unresolved ON dead_letter_queue(resolved_at) WHERE resolved_at IS NULL;

-- ============================================================
-- Tabla: migration_log (Historial de migraciones del Nomada)
-- ============================================================
CREATE TABLE IF NOT EXISTS migration_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_provider VARCHAR(100),
    to_provider VARCHAR(100) NOT NULL,
    trigger_reason VARCHAR(255),
    backup_status VARCHAR(20) DEFAULT 'pending',
    restore_status VARCHAR(20) DEFAULT 'pending',
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT
);

-- ============================================================
-- Tabla: backup_markers (Registro de backups exitosos)
-- ============================================================
CREATE TABLE IF NOT EXISTS backup_markers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id VARCHAR(100) NOT NULL,
    backup_type VARCHAR(50) NOT NULL,
    commit_hash VARCHAR(40),
    files_count INT DEFAULT 0,
    total_bytes BIGINT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backup_node ON backup_markers(node_id);

-- ============================================================
-- Row Level Security (RLS) — opcional pero recomendado
-- ============================================================
-- ALTER TABLE nexus_locks ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE vector_knowledge ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE dead_letter_queue ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- Funcion helper: buscar chunks similares
-- ============================================================
CREATE OR REPLACE FUNCTION match_knowledge(
    query_embedding vector(1024),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    chunk_id UUID,
    source_file VARCHAR(500),
    content TEXT,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        vk.chunk_id,
        vk.source_file,
        vk.content,
        1 - (vk.embedding <=> query_embedding) AS similarity
    FROM vector_knowledge vk
    WHERE 1 - (vk.embedding <=> query_embedding) > match_threshold
    ORDER BY vk.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
