# Modelo F4 · Contratos (EG-14)

F4 modela las condiciones contractuales usadas para liquidar regalías. El seed **no inventa identificadores de negocio**: lee `titular_id` de `titulares.parquet` y `track_id` de `catalogo_f1.parquet`, ambos producidos por EG-12.

## Modelo

```mermaid
erDiagram
    titulares_derechos ||--|{ contratos : "tiene"
    contratos ||--o{ exclusiones_territoriales : "excluye"

    titulares_derechos {
      uuid titular_id PK
      text nombre
      text tipo
      char pais
    }
    contratos {
      uuid contrato_id PK
      uuid titular_id FK
      varchar track_id
      numeric porcentaje
      char territorio
      date valido_desde
      date valido_hasta
    }
    exclusiones_territoriales {
      uuid contrato_id PK
      char pais PK
    }
```

## Reglas

- **Integridad con F1:** cada titular y pista vienen de los Parquet de EG-12. Cada titular recibe al menos una condición contractual.
- **RN-07 (vigencia):** algunos titulares cambian porcentaje a mitad de mes. El primer período termina el día 14 y el siguiente comienza el 15; PostgreSQL además impide solapamientos para la misma combinación titular/pista/territorio.
- **RN-08 (exclusiones):** algunos contratos excluyen un país. La exclusión se guarda separada para que EG-20/EG-23 puedan consultarla sin codificar listas dentro de una columna.
- **Porcentaje:** `CHECK (porcentaje BETWEEN 0 AND 100)`.
- **Q7 (supuesto):** `territorio IS NULL` representa una condición general. Cuando el contrato define explícitamente un territorio, la condición se limita a ese país. La condición territorial no sustituye las exclusiones de RN-08.
- **Reproducibilidad:** semilla 42 por defecto y UUID5. La aleatoriedad se deriva de `semilla + titular_id`, por lo que una nueva ejecución produce las mismas filas.
- **Idempotencia:** las PK deterministas y `ON CONFLICT DO NOTHING` permiten reejecutar el seed sin aumentar los conteos.

Q7 sigue siendo un **supuesto del equipo pendiente de validación del instructor** (EG-11). Si la respuesta cambia, deben actualizarse modelo, seed, pruebas y las reglas de liquidación.

## Parámetros

`ContratosConfig` centraliza la semilla, fecha de inicio, fracción de titulares con cambio de porcentaje, fracción con exclusiones, fracción con condición territorial y rango permitido para los porcentajes. Esto evita valores de negocio dispersos por el código.

## Consumo futuro

EG-20 expondrá F4 mediante FastAPI + SQLModel. EG-23/EG-37 seleccionarán la condición vigente para la fecha de reproducción, aplicarán el porcentaje correspondiente y descartarán reproducciones cuyo país esté excluido.
