# ADR-XXXX · Título corto en forma de decisión

> Copia este archivo como `docs/adr/NNNN-titulo-en-kebab-case.md` y registra el ADR en [README.md](README.md).

| Campo | Valor |
|---|---|
| Estado | Propuesto · Aceptado · Rechazado · Reemplazado por ADR-YYYY |
| Fecha | AAAA-MM-DD |
| Historia que lo origina | HU NN · EG-NN |
| Responsable | Nombre |
| Revisó | Nombre de otra persona del equipo |
| Referencias | RN-xx, RF-xx, RNF-xx, CA-xx, E-xx, tema N |

## 1. Contexto

¿Qué problema hay que resolver y por qué ahora? Describe los hechos (volumen, restricciones, reglas de negocio), no la solución.

## 2. Qué debe cumplir la decisión

Cada criterio se conecta con una regla de negocio, un requisito o un costo. Esto es lo que evalúa la rúbrica.

- **Negocio:** p. ej. RN-04: las reproducciones offline se atribuyen al mes real.
- **Requisito:** p. ej. RNF-01: la liquidación corre en menos de 1 hora.
- **Costo:** p. ej. el servicio queda prendido 24/7; el presupuesto del proyecto es de X USD al mes.
- **Equipo:** p. ej. el equipo ya conoce la herramienta, o ya la vio en un tema del curso.

## 3. Opciones consideradas

| Opción | A favor | En contra | Costo aprox. USD/mes |
|---|---|---|---|
| A · … | | | |
| B · … | | | |
| C · … | | | |

## 4. Decisión

**Elegimos la opción X** porque … (una o dos frases que citen los criterios de la sección 2).

## 5. Consecuencias

- **Positivas:** …
- **Negativas / lo que aceptamos:** …
- **Riesgos y mitigación:** …

## 6. Cómo sabremos que funciona

La prueba, métrica o criterio de aceptación que confirma la decisión. P. ej.: «reiniciar el consumidor a mitad de carga no pierde ni duplica eventos (HU 20)».

## 7. Fuentes

Documentación oficial consultada (AWS, PostgreSQL, Spark, etc.), con enlace.
