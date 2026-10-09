-- 002_f4_contratos.sql · F4 contratos de titulares (PostgreSQL 16)
-- EG-14 · RN-06 / RN-07 / RN-08 · Condiciones contractuales con vigencia y territorio opcional

CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE IF NOT EXISTS titulares_derechos (
    titular_id uuid PRIMARY KEY,
    nombre     text NOT NULL,
    tipo       text NOT NULL CHECK (tipo IN ('sello', 'distribuidora', 'sociedad_gestion')),
    pais       char(2) NOT NULL
);

CREATE TABLE IF NOT EXISTS contratos (
    contrato_id uuid PRIMARY KEY,
    titular_id  uuid NOT NULL REFERENCES titulares_derechos (titular_id),
    track_id    varchar(22) NOT NULL,
    porcentaje  numeric(5,2) NOT NULL CHECK (porcentaje BETWEEN 0 AND 100),
    territorio  char(2),
    valido_desde date NOT NULL,
    valido_hasta date,
    CHECK (valido_hasta IS NULL OR valido_hasta >= valido_desde)
);

-- RN-07: una misma condición (titular + pista + territorio) no puede tener vigencias solapadas.
-- COALESCE permite tratar la condición general (territorio NULL) como una clave comparable.
ALTER TABLE contratos DROP CONSTRAINT IF EXISTS ex_contratos_vigencia;
ALTER TABLE contratos ADD CONSTRAINT ex_contratos_vigencia
EXCLUDE USING gist (
    titular_id WITH =,
    track_id WITH =,
    (COALESCE(territorio, '')) WITH =,
    daterange(valido_desde, COALESCE(valido_hasta + 1, 'infinity'::date), '[)') WITH &&
);

CREATE INDEX IF NOT EXISTS ix_contratos_titular ON contratos (titular_id);
CREATE INDEX IF NOT EXISTS ix_contratos_track ON contratos (track_id);

CREATE TABLE IF NOT EXISTS exclusiones_territoriales (
    contrato_id uuid NOT NULL REFERENCES contratos (contrato_id) ON DELETE CASCADE,
    pais        char(2) NOT NULL,
    PRIMARY KEY (contrato_id, pais)
);
