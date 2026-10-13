#!/bin/sh
# Seed completo en orden (EG-25): catálogo F1 -> seed F3 -> seed F4. Corta en el primer error.
# Reejecutarlo no duplica filas: los seeds usan uuid5 + ON CONFLICT DO NOTHING.
set -eu

F1_ENTRADA="${F1_ENTRADA:-/datos/entrada/samples/f1_muestra.csv}"
F1_TITULARES="${F1_TITULARES:-50}"
F3_MODO="${F3_MODO:-dev}"
SALIDA=/datos/procesados

echo "== 1/3 Catálogo F1 ($F1_ENTRADA, $F1_TITULARES titulares)"
python -m sonoraplay.catalogo --entrada "$F1_ENTRADA" --salida "$SALIDA" --titulares "$F1_TITULARES"

echo "== 2/3 Seed F3 de suscripciones (modo $F3_MODO)"
python -m sonoraplay.seed --modo "$F3_MODO"

echo "== 3/3 Seed F4 de contratos"
python -m sonoraplay.seed.f4_contratos --datos-f1 "$SALIDA"

echo "== Seed terminado"
