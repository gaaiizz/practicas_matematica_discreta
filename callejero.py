"""
callejero.py

Matemática Discreta - IMAT
ICAI, Universidad Pontificia Comillas

Grupo: GPxxx
Integrantes:
    - XX
    - XX

Descripción:
Librería con herramientas y clases auxiliares necesarias para la representación de un callejero en un grafo.

Complétese esta descripción según las funcionalidades agregadas por el grupo.
"""

import osmnx as ox
import networkx as nx
import pandas as pd
from pathlib import Path

from typing import Tuple

STREET_FILE_NAME="direcciones.csv"

PLACE_NAME = "Madrid, Spain"
MAP_FILE_NAME="madrid.graphml"

MAX_SPEEDS={'living_street': '20',
'residential': '30',
'primary_link': '40',
'unclassified': '40',
'secondary_link': '40',
'trunk_link': '40',
'secondary': '50',
'tertiary': '50',
'primary': '50',
'trunk': '50',
'tertiary_link':'50',
'busway': '50',
'motorway_link': '70',
'motorway': '100'}


class ServiceNotAvailableError(Exception):
    "Excepción que indica que la navegación no está disponible en este momento"
    pass


class AddressNotFoundError(Exception):
    "Excepción que indica que una dirección buscada no existe en la base de datos"
    pass


############## Parte 2 ##############

def comprobar_fichero():
    
    origen_path = Path("direcciones.csv")
    temporal_path = Path("direcciones_2_utf8.csv")

    try:
        # Comprueba si ya es UTF-8 válido
        with origen_path.open("r", encoding="utf-8", newline="") as f:
            pass

    except UnicodeDecodeError:
        # Si no era UTF-8 (p. ej., cp1252), lo convertimos y reemplazamos
        with origen_path.open("r", encoding="cp1252", newline="") as origen:
            contenido = origen.read()

        with temporal_path.open("w", encoding="utf-8", newline="") as destino:
            destino.write(contenido)

        origen_path.unlink()
        temporal_path.rename(origen_path)
        print("Convertido de cp1252 a UTF-8 y reemplazado direcciones.csv.")


def carga_callejero() -> pd.DataFrame:
    """ Función que carga el callejero de Madrid, lo procesa y devuelve
    un DataFrame con los datos procesados
    
    Args: None
    Returns:
        DataFrame: dataframe con los datos del callejero procesados.
    Raises:
        FileNotFoundError si el fichero csv con las direcciones no existe
    """

    try:
        columnas_str = [
            'Clase de la via',
            'Nombre de la vía',
            'Literal de numeracion',
            'Partícula de la vía'
        ]

        columnas_float = [
            'Latitud en S R  ETRS89 WGS84',
            'Longitud en S R  ETRS89 WGS84'
        ]

        columnas = columnas_str + columnas_float

        raw = pd.read_csv('direcciones.csv', delimiter=';', usecols= columnas, skipinitialspace=True)
        callejero = raw.copy()

        callejero.rename(columns={
            'Clase de la via':'clase',
            'Nombre de la vía':'nombre',
            'Literal de numeracion':'numero',
            'Latitud en S R  ETRS89 WGS84':'latitud',
            'Longitud en S R  ETRS89 WGS84':'longitud',
            'Partícula de la vía':'particula'
        }, inplace=True)

        for col in ('clase', 'particula', 'nombre', 'numero'):
            callejero[col] = callejero[col].str.strip().str.upper()

        callejero['latitud'] = callejero['latitud'].map(dms_a_decimal)
        callejero['longitud'] = callejero['longitud'].map(dms_a_decimal)

        return callejero



    except FileNotFoundError:
        print('--- ERROR ---\n\t - El fichero de callejero no existe')

def dms_a_decimal(valor: str) -> float:
    texto = valor.strip().upper()
    signo = -1.0 if ("S" in texto or "W" in texto or "O" in texto) else 1.0

    for sep in ("º", "°", "'", '"', "N", "S", "E", "W", "O"):
        texto = texto.replace(sep, " ")

    partes = [float(p) for p in texto.split() if p]
    grados = partes[0] if len(partes) > 0 else 0.0
    minutos = partes[1] if len(partes) > 1 else 0.0
    segundos = partes[2] if len(partes) > 2 else 0.0

    return signo * (grados + minutos / 60.0 + segundos / 3600.0)

def busca_direccion(direccion: str, callejero: pd.DataFrame) -> tuple[float, float]:
    """
    Función que busca una dirección, dada en el formato
        calle, numero
    en el DataFrame callejero de Madrid y devuelve el par (latitud, longitud) en grados de la
    ubicación geográfica de dicha dirección.

    Args:
        direccion (str): Nombre completo de la calle con número, en formato "Calle, num"
        callejero (DataFrame): DataFrame con la información de las calles

    Returns:
        Tuple[float, float]: Par de float (latitud, longitud) de la dirección buscada, expresados en grados

    Raises:
        AddressNotFoundError: Si la dirección no existe en la base de datos

    Example:
        busca_direccion("Calle de Alberto Aguilera, 23", data) = (40.42998055555555, -3.7112583333333333)
        busca_direccion("Calle de Alberto Aguilera, 25", data) = (40.43013055555555, -3.7126916666666667)
    """
    direccion_limpia = direccion.strip().upper().replace(',', '')
    direccion_lista = [tok for tok in direccion_limpia.split(' ') if tok]

    if len(direccion_lista) < 3:
        raise AddressNotFoundError('La dirección pasada no tiene una estructura válida para buscar')

    clase = direccion_lista[0]  # toda clase es de longitud uno

    available_particles = ('DE', 'DEL', 'DE LA', 'DE LOS', 'DE LAS', '', 'A LA', 'AL')

    cand_1 = direccion_lista[1] if direccion_lista[1] in available_particles else ''
    cand_2 = direccion_lista[2] if (cand_1 and len(direccion_lista) > 2) else ''

    particula, i = determinar_particula(cand_1, cand_2, available_particles)

    nombre, numero = determinar_nombre(direccion_lista[i:])
    if not nombre or not numero.isdecimal():
        raise AddressNotFoundError(f'No se encontró la dirección: {direccion_limpia}')

    literal_buscado = f'NUM{int(numero):06d}'  # genera el número usando el prefijo y rellenando con ceros

    candidatas = callejero[
        (callejero['clase'] == clase)
        & (callejero['nombre'] == nombre)
        & (callejero['particula'] == particula)
        & (callejero['numero'] == literal_buscado)
    ]

    if candidatas.empty:
        raise AddressNotFoundError(f'No se encontró la dirección: {direccion_limpia}')

    lat = float(candidatas.iloc[0]['latitud'])
    lon = float(candidatas.iloc[0]['longitud'])

    return (lat, lon)

def determinar_particula(candidato_1: str, candidato_2: str, posibilidades: tuple[str, ...]) -> tuple[str, int]:
    """
    Función que determina la partícula de la calle pasada por argumento
    a la función buscar dirección.

    Args:
        candidato_1: str
        candidato_2: str
        posibilidades: tuple[str, ...]

    Returns:
        tuple[str, int]: se devuelve la partícula y el índice siguiente (2 o 3)

    Raises: None
    """
    concat = candidato_1 + ' ' + candidato_2  # se concatena la otra posible combinación de candidatos
    concat = concat.strip()  # Evitamos espacios al final en caso de que candidato 2 venga vacío

    # Si la concatenación es una posibilidad, quiere decir que es la partícula de longitud 2
    if concat in posibilidades:
        return (concat, 3)

    # Si no, miramos si el candidato uno es una posibilidad
    elif candidato_1 in posibilidades:
        return (candidato_1, 2)

    # Si no, es que no tenemos partícula
    else:
        return ('', 1)


def determinar_nombre(direccion_lista: list[str]) -> tuple[str, str]:
    """
    Función que devuelve el nombre de la calle y el número de la dirección pasada.

    Args:
        direccion_lista: list[str]

    Returns:
        tuple[str, str]: nombre de la calle pasada por argumento y número

    Raises: None
    """
    if not direccion_lista:
        return ('', '')

    # Se establece el límite máximo de indexación para el nombre
    i, limite = 0, len(direccion_lista) - 1
    nombre = ''

    # Mientras que el elemento no sea un número, se añade al nombre
    while not direccion_lista[i].isdecimal():
        nombre += direccion_lista[i] + ' '

        # Si al indexar el siguiente valor se sale de la lista, para el bucle ---> no hay número en la dirección
        if i + 1 > limite:
            break
        else:
            i += 1

    if direccion_lista[i].isdecimal():
        number = direccion_lista[i]
    else:
        number = ''

    # Devuelve el nombre sin espacio final y el número encontrado (o cadena vacía)
    return (nombre.strip(), number)



############## Parte 4 ##############


def carga_grafo() -> nx.MultiDiGraph:
    """ Función que recupera el quiver de calles de Madrid de OpenStreetMap.
    Args: None
    Returns:
        nx.MultiDiGraph: Quiver de las calles de Madrid.
    Raises:
        ServiceNotAvailableError: Si no es posible recuperar el grafo de OpenStreetMap.
    """
    pass


def procesa_grafo(multidigrafo:nx.MultiDiGraph) -> nx.DiGraph:
    """ Función que recupera el quiver de calles de Madrid de OpenStreetMap.
    Args:
        multidigrafo: multidigrafo de las calles de Madrid obtenido de OpenStreetMap.
    Returns:
        nx.DiGraph: Grafo dirigido y sin bucles asociado al multidigrafo dado.
    Raises: None
    """
    pass