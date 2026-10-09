-- 003_reportes_regalias.sql · Reporte de regalías por titular (PostgreSQL 16)
-- EG-21 · RF-05 / RN-11 / CA-08 · Modelo de lectura de la API de sellos
-- Contrato de lectura definido en EG-21; la EG-23 / EG-37 lo llenan. Cambios coordinados con ADR-0007.
-- Unidades, redondeo y ejemplo: docs/servicios/api-titulares.md ("Contrato para la EG-23 / EG-37").

-- Una fila por cada liquidación de un mes. Re-liquidar un mes crea una liquidación nueva
-- (append-only, ADR-0007); la API muestra la de mayor publicada_en.
CREATE TABLE IF NOT EXISTS liquidaciones (
    liquidacion_id uuid PRIMARY KEY,
    -- Primer día del mes UTC (ADR-0002).
    periodo        date NOT NULL CHECK (periodo = date_trunc('month', periodo)::date),
    creada_en      timestamptz NOT NULL DEFAULT now(),
    -- NULL = en proceso: quien escribe en lotes (Spark, EG-37) la publica al terminar.
    -- La API nunca muestra una liquidación sin publicar.
    publicada_en   timestamptz,
    CHECK (publicada_en IS NULL OR publicada_en >= creada_en),
    -- Destino de la FK compuesta de reporte_regalias: el periodo de cada fila coincide con el
    -- de su liquidación.
    UNIQUE (liquidacion_id, periodo)
);

CREATE INDEX IF NOT EXISTS ix_liquidaciones_periodo ON liquidaciones (periodo, publicada_en);

-- Una fila por titular, país de facturación (Q6), componente de la bolsa (Q8) y % contractual.
-- El % va en la PK porque un titular puede tener dos % en el mismo mes (cambio de contrato a
-- mitad de mes, RN-07, o pistas con % distintos): así cada fila cumple
-- regalia_usd = bolsa × participacion × porcentaje_contractual / 100.
CREATE TABLE IF NOT EXISTS reporte_regalias (
    liquidacion_id         uuid NOT NULL,
    titular_id             uuid NOT NULL REFERENCES titulares_derechos (titular_id),
    periodo                date NOT NULL,
    pais                   char(2) NOT NULL CHECK (pais ~ '^[A-Z]{2}$'),
    componente             text NOT NULL CHECK (componente IN ('suscripcion', 'publicidad')),
    reproducciones_validas integer NOT NULL CHECK (reproducciones_validas >= 0),
    -- Fracción de las reproducciones válidas del componente en ese país: de 0 a 1.
    participacion          numeric(9,6) NOT NULL CHECK (participacion BETWEEN 0 AND 1),
    -- De 0 a 100 (80.00 = 80 %), como contratos.porcentaje.
    porcentaje_contractual numeric(5,2) NOT NULL CHECK (porcentaje_contractual BETWEEN 0 AND 100),
    -- 2 decimales, ROUND_HALF_UP (RNF-02).
    regalia_usd            numeric(14,2) NOT NULL CHECK (regalia_usd >= 0),
    PRIMARY KEY (liquidacion_id, titular_id, pais, componente, porcentaje_contractual),
    FOREIGN KEY (liquidacion_id, periodo) REFERENCES liquidaciones (liquidacion_id, periodo)
);

CREATE INDEX IF NOT EXISTS ix_reporte_regalias_titular ON reporte_regalias (titular_id, periodo);
