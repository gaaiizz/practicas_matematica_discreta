"""
callejero.py

Matemática Discreta - IMAT
ICAI, Universidad Pontificia Comillas

Grupo: GP02A
Integrantes:
    - Carlos Fracaro Solo de Zaldívar
    - Luis Adrián García Ruiz

Descripción:
Librería con herramientas y clases auxiliares necesarias para la representación de un callejero en un grafo.

Complétese esta descripción según las funcionalidades agregadas por el grupo.
"""

import ast
import math
import re
from collections import Counter
from pathlib import Path
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox
import pandas as pd

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


VELOCIDAD_POR_DEFECTO = 50  # km/h para tipos de vía que no aparecen en MAX_SPEEDS
NOMBRE_DESCONOCIDO = "vía sin nombre"
KMH_POR_MPH = 1.609344

# Un valor de "maxspeed" válido: un número, opcionalmente seguido de "mph"
_PATRON_VELOCIDAD = re.compile(r"\s*(\d+(?:[.,]\d+)?)\s*(mph)?\s*", re.IGNORECASE)


def carga_grafo() -> nx.MultiDiGraph:
    """ Función que recupera el quiver de calles de Madrid de OpenStreetMap.

    Si el fichero MAP_FILE_NAME existe, el grafo se lee de él. Si no, se
    descarga de OpenStreetMap la red de vías para coches (network_type="drive")
    de PLACE_NAME y se guarda en MAP_FILE_NAME para no volver a descargarla.

    Args: None
    Returns:
        nx.MultiDiGraph: Quiver de las calles de Madrid.
    Raises:
        ServiceNotAvailableError: Si no es posible recuperar el grafo de OpenStreetMap.
    """
    fichero = Path(MAP_FILE_NAME)

    if fichero.exists():
        return ox.load_graphml(fichero)

    try:
        multidigrafo = ox.graph_from_place(PLACE_NAME, network_type="drive")
    except Exception as error:
        # Sin conexión, servidor caído, respuesta vacía... para el GPS todos
        # estos casos significan lo mismo: el servicio no está disponible.
        raise ServiceNotAvailableError(
            f"No se pudo descargar el grafo de '{PLACE_NAME}' de OpenStreetMap"
        ) from error

    ox.save_graphml(multidigrafo, fichero)
    return multidigrafo


def lee_velocidad(valor: object) -> Optional[float]:
    """ Interpreta un valor del atributo "maxspeed" de OpenStreetMap.

    OSM guarda este atributo como texto y de formas muy distintas: "50",
    "20 mph", "ES:urban", "30;50"... y OSMnx lo convierte en una lista cuando
    une varios tramos de una misma calle en una sola arista. Si hay varias
    velocidades, se toma la mínima: así nunca se supone que un tramo se puede
    recorrer más rápido que su parte más lenta.

    Args:
        valor (object): valor del atributo "maxspeed" (str, número, lista o None).
    Returns:
        Optional[float]: velocidad en km/h, o None si el valor no contiene
            ninguna velocidad numérica válida.
    Raises: None
    Example:
        lee_velocidad("50") = 50.0
        lee_velocidad(["30", "50"]) = 30.0
        lee_velocidad("ES:urban") = None
    """
    if valor is None or isinstance(valor, bool):
        return None

    if isinstance(valor, (list, tuple, set)):
        velocidades = [v for v in map(lee_velocidad, valor) if v is not None]
        return min(velocidades) if velocidades else None

    if isinstance(valor, (int, float)):
        if math.isnan(valor) or valor <= 0:
            return None
        return float(valor)

    texto = str(valor).strip()

    # Lista guardada como texto, p. ej. "['30', '50']"
    if texto.startswith("[") and texto.endswith("]"):
        try:
            return lee_velocidad(ast.literal_eval(texto))
        except (ValueError, SyntaxError):
            return None

    # Varias velocidades separadas, p. ej. "30;50"
    if ";" in texto or "|" in texto:
        return lee_velocidad(re.split(r"[;|]", texto))

    coincidencia = _PATRON_VELOCIDAD.fullmatch(texto)
    if coincidencia is None:
        return None

    velocidad = float(coincidencia.group(1).replace(",", "."))
    if coincidencia.group(2):  # el valor venía en millas por hora
        velocidad *= KMH_POR_MPH

    return velocidad if velocidad > 0 else None


def velocidad_arista(datos: dict) -> float:
    """ Velocidad máxima (km/h) a la que se puede circular por una arista.

    Orden de preferencia:
        1. El atributo "maxspeed" de OSM, si contiene una velocidad válida.
        2. La velocidad de MAX_SPEEDS para el tipo de vía ("highway").
        3. VELOCIDAD_POR_DEFECTO si el tipo de vía no está en MAX_SPEEDS.
    Si la arista tiene varios tipos de vía, se toma la mínima de sus velocidades.

    Args:
        datos (dict): diccionario de datos de la arista.
    Returns:
        float: velocidad máxima en km/h.
    Raises: None
    """
    velocidad = lee_velocidad(datos.get("maxspeed"))
    if velocidad is not None:
        return velocidad

    tipos = datos.get("highway")
    if not isinstance(tipos, list):
        tipos = [tipos]

    return min(float(MAX_SPEEDS.get(tipo, VELOCIDAD_POR_DEFECTO)) for tipo in tipos)


def consumo_combustible(distancia_km: float, velocidad_kmh: float) -> float:
    """ Consumo de carburante (L) de un turismo medio, según el modelo del enunciado:

        C(d, v) = d * (0.452 / v + 0.096 - 0.001 * v + 7e-6 * v**2)

    El consumo por kilómetro es positivo para toda v > 0 (su mínimo es de unos
    0.066 L/km, cerca de v = 78 km/h), así que sirve como peso para Dijkstra.

    Args:
        distancia_km (float): longitud del trayecto en kilómetros.
        velocidad_kmh (float): velocidad (constante) del trayecto en km/h.
    Returns:
        float: litros de carburante consumidos.
    Raises: None
    """
    v = velocidad_kmh
    return distancia_km * (0.452 / v + 0.096 - 0.001 * v + 7e-6 * v ** 2)


def _texto_osm(valor: object) -> Optional[str]:
    """ Convierte un atributo de texto de OSM en una única cadena.

    OSMnx convierte el atributo en una lista cuando une tramos con valores
    distintos; en ese caso se unen los valores (sin repetir) con " / ".

    Args:
        valor (object): valor del atributo (str, lista o None).
    Returns:
        Optional[str]: el texto, o None si el atributo no existe o está vacío.
    Raises: None
    """
    if isinstance(valor, list):
        # dict.fromkeys elimina repetidos conservando el orden
        textos = list(dict.fromkeys(
            t.strip() for t in valor if isinstance(t, str) and t.strip()
        ))
        return " / ".join(textos) if textos else None

    if isinstance(valor, str) and valor.strip():
        return valor.strip()

    return None


def nombre_via(datos: dict) -> str:
    """ Nombre de la vía de una arista, siempre como una única cadena.

    Se usa el nombre ("name"); si no tiene, la referencia de la vía ("ref",
    p. ej. "M-30" o "A-6"), que es como suelen estar identificadas las
    autovías y sus enlaces en OSM; si tampoco, NOMBRE_DESCONOCIDO.

    Args:
        datos (dict): diccionario de datos de la arista.
    Returns:
        str: nombre de la vía.
    Raises: None
    """
    return (_texto_osm(datos.get("name"))
            or _texto_osm(datos.get("ref"))
            or NOMBRE_DESCONOCIDO)


def datos_limpios(datos: dict) -> dict:
    """ Copia de los datos de una arista con los atributos que necesita el GPS.

    Atributos añadidos:
        "velocidad" (float): velocidad máxima en km/h.
        "tiempo" (float): tiempo de recorrido en segundos a esa velocidad.
        "consumo" (float): litros de carburante para recorrerla a esa velocidad.
        "nombre" (str): nombre de la vía.

    Args:
        datos (dict): diccionario de datos de una arista de OSMnx (con "length" en metros).
    Returns:
        dict: nuevo diccionario con los datos originales y los añadidos.
    Raises: None
    """
    nuevos = dict(datos)
    longitud = float(datos["length"])  # metros
    velocidad = velocidad_arista(datos)  # km/h

    nuevos["length"] = longitud
    nuevos["velocidad"] = velocidad
    nuevos["tiempo"] = longitud / (velocidad / 3.6)  # km/h -> m/s
    nuevos["consumo"] = consumo_combustible(longitud / 1000, velocidad)
    nuevos["nombre"] = nombre_via(datos)

    return nuevos


def procesa_grafo(multidigrafo: nx.MultiDiGraph) -> nx.DiGraph:
    """ Función que convierte el quiver de calles de Madrid en un grafo dirigido sin bucles.

    Pasos:
        1. Limpia los datos de cada arista (ver datos_limpios).
        2. Colapsa las aristas paralelas u -> v en una sola. Cada peso se queda
           con el mínimo de las paralelas ("length", "tiempo" y "consumo" por
           separado), lo que hace exacta la ruta óptima en los tres modos del GPS.
           El resto de atributos (nombre, tipo de vía...) se toman de la
           paralela más corta. ox.convert.to_digraph no sirve aquí porque solo
           minimiza un atributo.
        3. Elimina los bucles u -> u.
        4. Se queda con la mayor componente fuertemente conexa, de forma que
           existe una ruta entre cualquier par de vértices.

    Las estadísticas de cada paso se guardan en grafo.graph["estadisticas"].
    El multidigrafo original no se modifica.

    Args:
        multidigrafo: multidigrafo de las calles de Madrid obtenido de OpenStreetMap.
    Returns:
        nx.DiGraph: Grafo dirigido y sin bucles asociado al multidigrafo dado.
    Raises: None
    """
    digrafo = nx.DiGraph()
    digrafo.graph.update(multidigrafo.graph)
    digrafo.add_nodes_from(multidigrafo.nodes(data=True))

    # 1 y 2: limpiar cada arista y colapsar las paralelas
    for u, v, datos in multidigrafo.edges(data=True):
        nuevos = datos_limpios(datos)

        if not digrafo.has_edge(u, v):
            nuevos["paralelas"] = 1
            digrafo.add_edge(u, v, **nuevos)
            continue

        actual = digrafo[u][v]
        tiempo_minimo = min(actual["tiempo"], nuevos["tiempo"])
        consumo_minimo = min(actual["consumo"], nuevos["consumo"])
        paralelas = actual["paralelas"] + 1

        # Los atributos descriptivos se toman de la paralela más corta
        if nuevos["length"] < actual["length"]:
            actual.clear()
            actual.update(nuevos)

        actual["tiempo"] = tiempo_minimo
        actual["consumo"] = consumo_minimo
        actual["paralelas"] = paralelas

    aristas_colapsadas = multidigrafo.number_of_edges() - digrafo.number_of_edges()

    # 3: eliminar bucles
    bucles = list(nx.selfloop_edges(digrafo))
    digrafo.remove_edges_from(bucles)

    # 4: mayor componente fuertemente conexa
    componente = max(nx.strongly_connected_components(digrafo), key=len)
    vertices_descartados = digrafo.number_of_nodes() - len(componente)
    digrafo = digrafo.subgraph(componente).copy()

    digrafo.graph["estadisticas"] = {
        "vertices_originales": multidigrafo.number_of_nodes(),
        "aristas_originales": multidigrafo.number_of_edges(),
        "aristas_paralelas_colapsadas": aristas_colapsadas,
        "bucles_eliminados": len(bucles),
        "vertices_fuera_de_la_componente": vertices_descartados,
        "vertices_finales": digrafo.number_of_nodes(),
        "aristas_finales": digrafo.number_of_edges(),
    }

    return digrafo


def resumen_grafo(grafo: nx.Graph) -> dict:
    """ Resumen de los datos guardados en los vértices y aristas de un grafo de OSMnx.

    Sirve para explorar el grafo (apartado 3 de la parte 4): qué atributos
    tienen los vértices y las aristas, cuántas aristas tienen cada uno, qué
    tipos de vía hay y cuántas aristas traen su velocidad máxima de OSM.

    Args:
        grafo (nx.Graph): grafo (o multidigrafo) de OSMnx.
    Returns:
        dict: diccionario con el resumen.
    Raises: None
    """
    atributos_vertices = Counter()
    for _, datos in grafo.nodes(data=True):
        atributos_vertices.update(datos.keys())

    atributos_aristas = Counter()
    tipos_via = Counter()
    for _, _, datos in grafo.edges(data=True):
        atributos_aristas.update(datos.keys())
        tipos = datos.get("highway")
        tipos_via.update(tipos if isinstance(tipos, list) else [tipos])

    numero_aristas = grafo.number_of_edges()
    con_velocidad = atributos_aristas.get("maxspeed", 0)

    return {
        "vertices": grafo.number_of_nodes(),
        "aristas": numero_aristas,
        "atributos_vertices": dict(atributos_vertices),
        "atributos_aristas": dict(atributos_aristas),
        "tipos_via": dict(tipos_via.most_common()),
        "porcentaje_con_maxspeed": 100 * con_velocidad / numero_aristas if numero_aristas else 0.0,
    }


def dibuja_multidigrafo(multidigrafo: nx.MultiDiGraph):
    """ Dibuja el multidigrafo descargado de OSM con la función de dibujo de OSMnx.

    La figura no se muestra todavía: hay que llamar a plt.show() después, de
    forma que todas las figuras abiertas aparezcan a la vez.

    Args:
        multidigrafo (nx.MultiDiGraph): multidigrafo de OSMnx.
    Returns:
        Los ejes de matplotlib donde se ha dibujado.
    Raises: None
    """
    _, ax = ox.plot_graph(multidigrafo, node_size=0, edge_linewidth=0.5,
                          show=False, close=False)
    return ax


def dibuja_grafo(grafo: nx.DiGraph, ax=None, color: str = "#999999", grosor: float = 0.5):
    """ Dibuja el grafo de calles con NetworkX, situando cada vértice en su
    posición geográfica (atributos "x" = longitud e "y" = latitud).

    Las aristas se dibujan sin flechas: con flechas, NetworkX dibuja cada
    arista por separado y con cien mil aristas es lentísimo.

    Args:
        grafo (nx.DiGraph): grafo de calles.
        ax: ejes de matplotlib donde dibujar (si es None, se crea una figura nueva).
        color (str): color de las aristas.
        grosor (float): grosor de las aristas.
    Returns:
        Los ejes de matplotlib donde se ha dibujado, para poder añadir más cosas encima
        (p. ej. una ruta).
    Raises: None
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(10, 10))

    posiciones = {vertice: (datos["x"], datos["y"]) for vertice, datos in grafo.nodes(data=True)}
    nx.draw_networkx_edges(grafo, pos=posiciones, ax=ax, edge_color=color,
                           width=grosor, arrows=False)

    # Un grado de longitud mide cos(latitud) veces lo que un grado de latitud:
    # se corrige la proporción para que el mapa no salga estirado.
    latitud_media = sum(y for _, y in posiciones.values()) / len(posiciones)
    ax.set_aspect(1 / math.cos(math.radians(latitud_media)))
    ax.set_axis_off()

    return ax