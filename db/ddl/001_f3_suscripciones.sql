-- 001_f3_suscripciones.sql · F3 suscripciones (PostgreSQL 16)
-- HU 04 · EG-13 · Seed reproducible e idempotente de F3
-- Todas las sentencias usan IF NOT EXISTS / OR REPLACE: el script es seguro de correr dos veces.

CREATE TABLE IF NOT EXISTS planes (
    plan_id      smallint PRIMARY KEY,
    codigo       text NOT NULL UNIQUE
                 CHECK (codigo IN ('free', 'individual', 'familiar', 'estudiante')),
    nombre       text NOT NULL,
    precio_usd   numeric(8,2) NOT NULL CHECK (precio_usd >= 0),
    max_miembros smallint NOT NULL CHECK (max_miembros BETWEEN 1 AND 6)
);

CREATE TABLE IF NOT EXISTS usuarios (
    usuario_id       uuid PRIMARY KEY,
    nombre           text NOT NULL,
    email            text NOT NULL,      -- sin UNIQUE: el seed inyecta duplicados (sección 5.3)
    pais_facturacion char(2),            -- NULL permitido: defecto inyectable
    fecha_alta       timestamptz NOT NULL,
    fecha_baja       timestamptz,
    CHECK (fecha_baja IS NULL OR fecha_baja >= fecha_alta)
);
CREATE INDEX IF NOT EXISTS ix_usuarios_email ON usuarios (email);

CREATE TABLE IF NOT EXISTS grupos_familiares (
    grupo_id   uuid PRIMARY KEY,
    titular_id uuid NOT NULL UNIQUE REFERENCES usuarios (usuario_id),
    creado_en  timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS miembros_familia (
    grupo_id    uuid NOT NULL REFERENCES grupos_familiares (grupo_id),
    usuario_id  uuid NOT NULL UNIQUE REFERENCES usuarios (usuario_id), -- un usuario, un grupo
    rol         text NOT NULL CHECK (rol IN ('titular', 'miembro')),
    fecha_union timestamptz NOT NULL,
    PRIMARY KEY (grupo_id, usuario_id)
);

-- Máximo 6 miembros por grupo (un CHECK no puede contar filas de otras filas)
CREATE OR REPLACE FUNCTION fn_max_6_miembros() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- Re-ejecución del seed: la fila ya existe y ON CONFLICT DO NOTHING la descartará
    IF EXISTS (SELECT 1 FROM miembros_familia
               WHERE grupo_id = NEW.grupo_id AND usuario_id = NEW.usuario_id) THEN
        RETURN NEW;
    END IF;
    IF (SELECT count(*) FROM miembros_familia WHERE grupo_id = NEW.grupo_id) >= 6 THEN
        RAISE EXCEPTION 'El grupo % ya tiene 6 miembros', NEW.grupo_id
              USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_max_6_miembros ON miembros_familia;
CREATE TRIGGER trg_max_6_miembros
    BEFORE INSERT ON miembros_familia
    FOR EACH ROW EXECUTE FUNCTION fn_max_6_miembros();

CREATE TABLE IF NOT EXISTS suscripciones (
    suscripcion_id uuid PRIMARY KEY,
    usuario_id     uuid NOT NULL REFERENCES usuarios (usuario_id),
    plan_id        smallint NOT NULL REFERENCES planes (plan_id),
    grupo_id       uuid REFERENCES grupos_familiares (grupo_id),
    fecha_inicio   date NOT NULL,
    fecha_fin      date,
    motivo_fin     text CHECK (motivo_fin IN ('cambio_plan', 'cancelacion', 'no_renovacion')),
    CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio),
    CHECK ((fecha_fin IS NULL) = (motivo_fin IS NULL)),
    CHECK ((plan_id = 3) = (grupo_id IS NOT NULL))   -- 3 = familiar
);
-- Solo una suscripción abierta por usuario
CREATE UNIQUE INDEX IF NOT EXISTS ux_suscripcion_activa
    ON suscripciones (usuario_id) WHERE fecha_fin IS NULL;
CREATE INDEX IF NOT EXISTS ix_suscripciones_plan_inicio
    ON suscripciones (plan_id, fecha_inicio);

CREATE TABLE IF NOT EXISTS pagos (
    pago_id        uuid PRIMARY KEY,
    suscripcion_id uuid NOT NULL REFERENCES suscripciones (suscripcion_id),
    fecha_pago     date NOT NULL,
    monto_usd      numeric(10,2) NOT NULL CHECK (monto_usd >= 0),
    estado         text NOT NULL CHECK (estado IN ('aprobado', 'rechazado'))
);
CREATE INDEX IF NOT EXISTS ix_pagos_suscripcion ON pagos (suscripcion_id);

-- Registro de defectos inyectados (trazabilidad de calidad de datos)
CREATE TABLE IF NOT EXISTS seed_defectos (
    entidad    text NOT NULL,
    entidad_id uuid NOT NULL,
    tipo       text NOT NULL CHECK (tipo IN ('email_duplicado', 'pais_facturacion_nulo')),
    PRIMARY KEY (entidad, entidad_id, tipo)
);
