"""Pruebas de aceptación de la HU 03 (EG-12) sobre data/samples/f1_muestra.csv."""

import uuid
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from sonoraplay.catalogo import __main__ as cli
from sonoraplay.catalogo.asignar_titulares import (
    asignar_titulares,
    generar_titulares,
    titular_id,
)
from sonoraplay.catalogo.limpiar_f1 import (
    descartar_invalidas,
    limpiar,
    normalizar,
    unificar_duplicados,
)
from sonoraplay.catalogo.muestra import construir_muestra
from sonoraplay.config import N_TITULARES
from sonoraplay.seed.f3_suscripciones import NAMESPACE

MUESTRA = Path(__file__).resolve().parents[2] / "data" / "samples" / "f1_muestra.csv"
INVALIDA = "1kR4gIb7nGxHPI3D2ifs59"  # sin artists ni track_name, duration_ms = 0
HOMONIMAS = ("Casi Te Envidio", "Andy Montañez")  # mismo nombre y artista, 2 track_id
N_PEQUENO = 20  # la muestra tiene menos artistas que N_TITULARES


@pytest.fixture(scope="module")
def crudo() -> pd.DataFrame:
    return pd.read_csv(MUESTRA)


@pytest.fixture(scope="module")
def validas(crudo) -> pd.DataFrame:
    return descartar_invalidas(normalizar(crudo))[0]


@pytest.fixture(scope="module")
def unificado(validas) -> tuple[pd.DataFrame, pd.DataFrame]:
    return unificar_duplicados(validas)


def correr(crudo: pd.DataFrame) -> tuple[pd.DataFrame, ...]:
    catalogo, track_generos, _ = limpiar(crudo)
    titulares = generar_titulares(N_PEQUENO)
    return asignar_titulares(catalogo, titulares), track_generos, titulares


# Criterio 1 — cada track_id aparece una sola vez
def test_track_id_unico_tras_unificar(validas, unificado):
    catalogo, _ = unificado
    assert validas["track_id"].duplicated().any()  # la muestra sí trae repetidos
    assert catalogo["track_id"].is_unique
    assert set(catalogo["track_id"]) == set(validas["track_id"])


@pytest.mark.parametrize(
    ("track_id", "esperado"),
    [
        ("1VyiUi0mRnSKgtHa5dBoUd", "rock"),  # rock tiene popularidad 64, el resto 63
        ("16usJl9JyY13eBN0qj95uC", "minimal-techno"),  # 14 frente a 13
        ("0tNLlw94DIrCECnp0dSUUz", "hip-hop"),  # empate en 5 géneros → alfabético
        ("2Ns9vtFyKhGoI0vCFLHQOR", "rock"),  # empate rock/ska en el máximo; alt-rock no
        ("5A6E9cVlxYAmEvdbEE4w9Y", "piano"),  # duplicado exacto, un solo género
    ],
)
def test_genero_principal(unificado, track_id, esperado):
    catalogo, _ = unificado
    assert catalogo.set_index("track_id").at[track_id, "genero_principal"] == esperado


def test_track_generos_conserva_todos_los_generos(validas, unificado):
    catalogo, track_generos = unificado
    esperado = validas.groupby("track_id")["track_genre"].apply(set)
    obtenido = track_generos.groupby("track_id")["genero"].apply(set)
    assert obtenido.sort_index().equals(esperado.sort_index())
    assert not track_generos.duplicated().any()
    assert (catalogo.set_index("track_id")["n_generos"] == obtenido.map(len)).all()


def test_descartar_invalidas_saca_la_fila_invalida(crudo):
    validas, descartadas = descartar_invalidas(normalizar(crudo))
    assert INVALIDA not in set(validas["track_id"])
    assert descartadas["track_id"].tolist() == [INVALIDA]
    assert descartadas["motivo"].tolist() == ["sin_artists"]
    assert len(validas) + len(descartadas) == len(crudo)


def test_descarta_duracion_no_positiva_y_recorta_espacios(crudo):
    df = crudo[crudo["track_id"] != INVALIDA].head(3).copy()
    df.loc[df.index[0], "duration_ms"] = 0
    df.loc[df.index[1], "artists"] = "  Terra "
    validas, descartadas = descartar_invalidas(normalizar(df))
    assert descartadas["motivo"].tolist() == ["duration_ms<=0"]
    assert "Terra" in set(validas["artists"])
    assert "Unnamed: 0" not in validas.columns


def test_distinto_track_id_no_se_fusiona(unificado):
    catalogo, _ = unificado
    nombre, artista = HOMONIMAS
    mismas = catalogo[(catalogo["track_name"] == nombre) & (catalogo["artists"] == artista)]
    assert mismas["track_id"].nunique() == len(mismas) == 2


# Criterios 2 y 5 — un titular por pista y el mismo para todas las pistas del artista
def test_cada_pista_tiene_un_titular_compartido_por_artista(crudo):
    catalogo, _, titulares = correr(crudo)
    assert catalogo["titular_id"].notna().all()
    assert catalogo["titular_id"].isin(titulares["titular_id"]).all()
    assert (catalogo.groupby("artista_principal")["titular_id"].nunique() == 1).all()


def test_1500_titulares_unicos_y_ninguno_vacio():
    artistas = pd.DataFrame({"artista_principal": [f"artista-{i}" for i in range(17_648)]})
    titulares = generar_titulares(N_TITULARES)
    catalogo = asignar_titulares(artistas, titulares)
    assert N_TITULARES == 1_500
    assert titulares["titular_id"].is_unique and len(titulares) == N_TITULARES
    assert set(catalogo["titular_id"]) == set(titulares["titular_id"])
    assert set(titulares["tipo"]) == {"sello", "distribuidora", "sociedad_gestion"}
    # Skew tipo Zipf: el titular más grande concentra muchos más artistas que la mediana
    por_titular = catalogo["titular_id"].value_counts()
    assert por_titular.max() > 50 * por_titular.median()


def test_falla_si_hay_menos_artistas_que_titulares():
    artistas = pd.DataFrame({"artista_principal": ["a", "b"]})
    with pytest.raises(ValueError, match="2 artistas para 3 titulares"):
        asignar_titulares(artistas, generar_titulares(3))


# Criterio 3 — correr dos veces da el mismo resultado
def test_dos_ejecuciones_identicas(crudo):
    for a, b in zip(correr(crudo), correr(crudo), strict=True):
        assert_frame_equal(a, b)


def test_titular_id_determinista():
    assert titular_id(7) == titular_id(7) == str(uuid.uuid5(NAMESPACE, "titular-7"))
    assert titular_id(7) != titular_id(8)
    assert generar_titulares(5)["titular_id"].tolist() == [titular_id(n) for n in range(1, 6)]


def test_comando_escribe_los_tres_parquet(tmp_path):
    cli.main(["--entrada", str(MUESTRA), "--salida", str(tmp_path), "--titulares", "20"])
    catalogo = pd.read_parquet(tmp_path / "catalogo_f1.parquet")
    assert catalogo["track_id"].is_unique and catalogo["titular_id"].notna().all()
    assert len(pd.read_parquet(tmp_path / "titulares.parquet")) == 20
    assert (tmp_path / "track_generos.parquet").exists()


def test_muestra_incluye_los_casos_dificiles_y_es_reproducible():
    crudo = pd.read_csv(MUESTRA, index_col=0)
    muestra = construir_muestra(crudo, tamano=60)
    assert_frame_equal(muestra, construir_muestra(crudo, tamano=60))
    assert len(muestra) == 60
    assert INVALIDA in set(muestra["track_id"])
    # 6 con empate + 3 con popularidad distinta (las de 4+ géneros pueden coincidir)
    assert (muestra.groupby("track_id")["track_genre"].nunique() >= 2).sum() >= 9
    nombre, artista = HOMONIMAS
    assert ((muestra["track_name"] == nombre) & (muestra["artists"] == artista)).sum() == 2
