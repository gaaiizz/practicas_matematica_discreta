"""
navegacion.py

Matemática Discreta - IMAT
ICAI, Universidad Pontificia Comillas

Grupo: GP02A
Integrantes:
    - Carlos Fracaro Solo de Zaldívar
    - Luis Adrián García Ruiz

Descripción:
Librería con la lógica del navegador (parte 6), separada de la interfaz de
gps.py para poder probarla por partes:
    - Funciones de peso para los tres modos de ruta (corta, rápida, ecológica).
    - Búsqueda del vértice del grafo más cercano a unas coordenadas.
    - Cálculo de la ruta óptima con grafo_pesado.
    - Generación de las instrucciones de navegación.
    - Búsqueda de direcciones tolerante (acentos, sugerencias).
    - Dibujo de la ruta sobre el callejero.
"""

import bisect
import difflib
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

import callejero
import grafo_pesado


RADIO_TIERRA = 6_371_000.0  # metros

# Distancia (m) hacia atrás y hacia delante sobre la ruta que se usa para medir
# la dirección de llegada y de salida en un cruce. Suaviza las curvas de la
# geometría y los tramos de pocos metros dentro de los cruces grandes.
DISTANCIA_RUMBO = 25.0

# Tramos más cortos que esto (m) se consideran parte del cruce, no una calle por
# la que se circula (p. ej. cruzar la mediana de una avenida de doble calzada).
TRAMO_CORTO = 25.0

# Una plaza o glorieta de hasta esta longitud (m) que se cruza en línea recta entre
# dos tramos de la misma calle se considera parte de esa calle.
PLAZA_DE_PASO = 150.0

# Ángulo mínimo (grados) para avisar de un giro sin cambiar de calle, cuando en
# ese cruce se podría seguir por otro sitio.
GIRO_MISMA_VIA = 45.0

# Límites (grados) para clasificar los giros
LIMITE_RECTO = 25.0
LIMITE_LIGERO = 60.0
LIMITE_NORMAL = 135.0
LIMITE_BRUSCO = 165.0

TIPOS_AUTOVIA = {"motorway", "trunk"}
VALORES_ROTONDA = {"roundabout", "circular"}


class RutaNoEncontradaError(Exception):
    "Excepción que indica que no existe una ruta entre los vértices pedidos"
    pass


############## Funciones de peso ##############

def peso_distancia(G: nx.DiGraph, u: object, v: object) -> float:
    """Longitud de la arista u -> v en metros (ruta más corta)."""
    return G[u][v]["length"]


def peso_tiempo(G: nx.DiGraph, u: object, v: object) -> float:
    """Tiempo en segundos para recorrer u -> v a la velocidad máxima (ruta más rápida)."""
    return G[u][v]["tiempo"]


def peso_consumo(G: nx.DiGraph, u: object, v: object) -> float:
    """Litros de carburante para recorrer u -> v a la velocidad máxima (ruta ecológica)."""
    return G[u][v]["consumo"]


@dataclass(frozen=True)
class Modo:
    """Modo de cálculo de ruta: su nombre y la función de peso que minimiza."""
    nombre: str
    peso: Callable[[nx.DiGraph, object, object], float]


MODOS: Dict[str, Modo] = {
    "1": Modo("más corta", peso_distancia),
    "2": Modo("más rápida", peso_tiempo),
    "3": Modo("más ecológica", peso_consumo),
}


############## Geometría ##############

def distancia_metros(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Distancia (m) sobre la superficie terrestre entre dos puntos (fórmula del haversine)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * RADIO_TIERRA * math.asin(math.sqrt(a))


def rumbo(origen: Tuple[float, float], destino: Tuple[float, float]) -> Optional[float]:
    """ Rumbo (grados, 0 = norte, 90 = este) para ir de origen a destino, dados como (lon, lat).

    En distancias de pocos metros se puede tratar la Tierra como plana: un grado
    de longitud mide cos(latitud) veces lo que un grado de latitud.

    Returns:
        Optional[float]: rumbo en [0, 360), o None si los dos puntos coinciden.
    """
    lat_media = math.radians((origen[1] + destino[1]) / 2)
    dx = (destino[0] - origen[0]) * math.cos(lat_media)
    dy = destino[1] - origen[1]
    if dx == 0 and dy == 0:
        return None
    return math.degrees(math.atan2(dx, dy)) % 360


def angulo_giro(rumbo_llegada: Optional[float], rumbo_salida: Optional[float]) -> float:
    """ Ángulo de giro en (-180, 180]: positivo a la derecha, negativo a la izquierda.

    Es la diferencia de rumbos llevada al intervalo (-180, 180]: el giro más
    corto que lleva de la dirección de llegada a la de salida.
    """
    if rumbo_llegada is None or rumbo_salida is None:
        return 0.0
    diferencia = (rumbo_salida - rumbo_llegada) % 360
    return diferencia - 360 if diferencia > 180 else diferencia


def punto_cardinal(rumbo_grados: Optional[float]) -> str:
    """Punto cardinal (de 8) más cercano a un rumbo."""
    puntos = ["norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste"]
    if rumbo_grados is None:
        return "norte"
    return puntos[round(rumbo_grados / 45) % 8]


def puntos_arista(G: nx.DiGraph, u: object, v: object) -> List[Tuple[float, float]]:
    """ Puntos (lon, lat) de la arista u -> v en el sentido de circulación.

    Si la arista tiene geometría (calles curvas), se usan sus puntos; si no, es
    un segmento recto entre los dos vértices.
    """
    inicio = (G.nodes[u]["x"], G.nodes[u]["y"])
    fin = (G.nodes[v]["x"], G.nodes[v]["y"])
    geometria = G[u][v].get("geometry")
    if geometria is None:
        return [inicio, fin]

    puntos = [tuple(p[:2]) for p in geometria.coords]
    # Por seguridad, se orienta la geometría de u a v
    if distancia_metros(*puntos[0], *inicio) > distancia_metros(*puntos[-1], *inicio):
        puntos.reverse()
    return puntos


class Trazado:
    """ Polilínea de una ruta (con la geometría real de las calles), que permite
    medir distancias a lo largo de la ruta y rumbos de llegada y salida en cada vértice.

    Attributes:
        puntos (List[Tuple[float, float]]): puntos (lon, lat) de la ruta en orden.
        acumulada (List[float]): distancia (m) desde el origen hasta cada punto.
        posicion_vertice (List[float]): distancia (m) desde el origen hasta cada vértice del camino.
    """

    def __init__(self, G: nx.DiGraph, vertices: Sequence[object]):
        primero = vertices[0]
        self.puntos = [(G.nodes[primero]["x"], G.nodes[primero]["y"])]
        self.acumulada = [0.0]
        self.posicion_vertice = [0.0]

        for u, v in zip(vertices, vertices[1:]):
            for punto in puntos_arista(G, u, v)[1:]:
                anterior = self.puntos[-1]
                self.acumulada.append(self.acumulada[-1] + distancia_metros(*anterior, *punto))
                self.puntos.append(punto)
            self.posicion_vertice.append(self.acumulada[-1])

    @property
    def longitud(self) -> float:
        return self.acumulada[-1]

    def punto_a(self, distancia: float) -> Tuple[float, float]:
        """Punto de la ruta a la distancia dada del origen (interpolando entre puntos)."""
        distancia = min(max(distancia, 0.0), self.longitud)
        j = bisect.bisect_right(self.acumulada, distancia)
        if j >= len(self.puntos):
            return self.puntos[-1]
        d0, d1 = self.acumulada[j - 1], self.acumulada[j]
        t = 0.0 if d1 == d0 else (distancia - d0) / (d1 - d0)
        (x0, y0), (x1, y1) = self.puntos[j - 1], self.puntos[j]
        return (x0 + t * (x1 - x0), y0 + t * (y1 - y0))

    def rumbo_llegada(self, i: int, distancia: float = DISTANCIA_RUMBO) -> Optional[float]:
        """Rumbo con el que se llega al vértice i-ésimo del camino."""
        s = self.posicion_vertice[i]
        return rumbo(self.punto_a(s - distancia), self.punto_a(s))

    def rumbo_salida(self, i: int, distancia: float = DISTANCIA_RUMBO) -> Optional[float]:
        """Rumbo con el que se sale del vértice i-ésimo del camino."""
        s = self.posicion_vertice[i]
        return rumbo(self.punto_a(s), self.punto_a(s + distancia))


############## Vértice más cercano ##############

class IndiceVertices:
    """ Búsqueda del vértice del grafo más cercano a unas coordenadas.

    Guarda las coordenadas de todos los vértices en arrays de numpy y calcula
    a la vez la distancia (haversine) a todos ellos: con ~31.000 vértices tarda
    milisegundos y no necesita scikit-learn (que ox.distance.nearest_nodes
    exige para grafos no proyectados y no está en requirements_gps.txt).
    """

    def __init__(self, G: nx.Graph):
        self.vertices = list(G.nodes)
        self.lat = np.radians([G.nodes[v]["y"] for v in self.vertices])
        self.lon = np.radians([G.nodes[v]["x"] for v in self.vertices])

    def mas_cercano(self, latitud: float, longitud: float) -> Tuple[object, float]:
        """ Vértice más cercano al punto dado y su distancia en metros.

        Args:
            latitud (float), longitud (float): coordenadas del punto en grados.
        Returns:
            Tuple[object, float]: (vértice, distancia en metros).
        """
        phi, lam = math.radians(latitud), math.radians(longitud)
        a = (np.sin((self.lat - phi) / 2) ** 2
             + math.cos(phi) * np.cos(self.lat) * np.sin((self.lon - lam) / 2) ** 2)
        i = int(np.argmin(a))  # la distancia es creciente en a: basta minimizar a
        return self.vertices[i], 2 * RADIO_TIERRA * math.asin(math.sqrt(a[i]))


############## Ruta ##############

@dataclass
class Ruta:
    """ Ruta calculada entre dos vértices.

    Attributes:
        vertices (List[object]): vértices del camino, del origen al destino.
        longitud (float): metros.
        tiempo (float): segundos, a la velocidad máxima de cada vía.
        consumo (float): litros de carburante.
    """
    vertices: List[object]
    longitud: float
    tiempo: float
    consumo: float


def calcula_ruta(G: nx.DiGraph, origen: object, destino: object,
                peso: Callable[[nx.DiGraph, object, object], float]) -> Ruta:
    """ Calcula con grafo_pesado el camino mínimo de origen a destino para la función de peso
    dada, y sus totales de distancia, tiempo y consumo.

    Raises:
        RutaNoEncontradaError: si no hay camino entre origen y destino.
    """
    try:
        vertices = grafo_pesado.camino_minimo(G, peso, origen, destino)
    except nx.NetworkXNoPath as error:
        raise RutaNoEncontradaError("No hay ruta entre el origen y el destino") from error

    if not vertices or vertices[0] != origen or vertices[-1] != destino:
        raise RutaNoEncontradaError("No hay ruta entre el origen y el destino")

    aristas = [G[u][v] for u, v in zip(vertices, vertices[1:])]
    return Ruta(
        vertices=list(vertices),
        longitud=sum(a["length"] for a in aristas),
        tiempo=sum(a["tiempo"] for a in aristas),
        consumo=sum(a["consumo"] for a in aristas),
    )


############## Instrucciones de navegación ##############

def es_rotonda(datos: dict) -> bool:
    """True si la arista forma parte de una rotonda (atributo "junction" de OSM)."""
    valor = datos.get("junction")
    valores = valor if isinstance(valor, list) else [valor]
    return any(v in VALORES_ROTONDA for v in valores)


def tipos_via(datos: dict) -> Set[str]:
    """Tipos de vía ("highway") de una arista, como conjunto."""
    valor = datos.get("highway")
    return set(valor) if isinstance(valor, list) else {valor}


def misma_via(nombre_a: str, nombre_b: str) -> bool:
    """ True si dos nombres de vía corresponden (al menos en parte) a la misma vía.

    OSMnx une con " / " los nombres de los tramos de calle que junta en una
    sola arista (p. ej. "Calle Mayor / Calle de Esparteros"): se considera la
    misma vía si comparten algún nombre. Las vías sin nombre no son la misma
    vía que ninguna otra.
    """
    if callejero.NOMBRE_DESCONOCIDO in (nombre_a, nombre_b):
        return False
    return bool(set(nombre_a.split(" / ")) & set(nombre_b.split(" / ")))


@dataclass
class Tramo:
    """ Parte de la ruta que se recorre sin necesitar instrucciones.

    Los índices se refieren a la lista de vértices del camino: el tramo va del
    vértice "inicio" al vértice "fin". "giro_hasta" es el índice del vértice
    donde termina la maniobra con la que se entra en el tramo (distinto de
    "inicio" si se le ha unido un tramo corto del cruce).
    """
    nombre: str
    inicio: int
    fin: int
    longitud: float
    rotonda: bool
    tipos: Set[str] = field(default_factory=set)
    giro_hasta: Optional[int] = None
    zigzag: Optional[Tuple[str, str]] = None  # lados de un giro doble ("izquierda", "derecha")

    @property
    def vertice_giro(self) -> int:
        return self.inicio if self.giro_hasta is None else self.giro_hasta

    def une(self, otro: "Tramo") -> None:
        """Añade a este tramo el tramo siguiente (que debe empezar donde acaba este)."""
        self.fin = otro.fin
        self.longitud += otro.longitud
        self.tipos |= otro.tipos


def es_enlace(tramo: Tramo) -> bool:
    """True si el tramo es un enlace (incorporación o salida, "*_link" en OSM)."""
    return any(isinstance(t, str) and t.endswith("_link") for t in tramo.tipos)


def tramos_iniciales(G: nx.DiGraph, vertices: Sequence[object]) -> List[Tramo]:
    """ Agrupa las aristas consecutivas del camino que tienen el mismo nombre de vía.

    Las aristas de una rotonda forman un único tramo aunque cambie el nombre.
    """
    tramos: List[Tramo] = []
    for i, (u, v) in enumerate(zip(vertices, vertices[1:])):
        datos = G[u][v]
        rotonda = es_rotonda(datos)
        nombre = datos["nombre"]
        ultimo = tramos[-1] if tramos else None

        mismo_tramo = ultimo is not None and ultimo.rotonda == rotonda and (
            rotonda or ultimo.nombre == nombre)
        if mismo_tramo:
            ultimo.fin = i + 1
            ultimo.longitud += datos["length"]
            ultimo.tipos |= tipos_via(datos)
            if ultimo.nombre == callejero.NOMBRE_DESCONOCIDO:
                ultimo.nombre = nombre  # rotonda: se queda con el primer nombre conocido
        else:
            tramos.append(Tramo(nombre, i, i + 1, datos["length"], rotonda, tipos_via(datos)))
    return tramos


def une_cruces(tramos: List[Tramo]) -> List[Tramo]:
    """ Une los tramos cortos o sin nombre que están entre dos tramos de la misma vía.

    P. ej. seguir recto por la calle A cruzando 10 m de la calle B (A, B, A):
    para el conductor es todo la calle A.
    """
    tramos = list(tramos)
    cambio = True
    while cambio:
        cambio = False
        for j in range(1, len(tramos) - 1):
            anterior, medio, siguiente = tramos[j - 1], tramos[j], tramos[j + 1]
            if (not (anterior.rotonda or medio.rotonda or siguiente.rotonda)
                    and misma_via(anterior.nombre, siguiente.nombre)
                    and (medio.longitud < TRAMO_CORTO or medio.nombre == callejero.NOMBRE_DESCONOCIDO)):
                anterior.une(medio)
                anterior.une(siguiente)
                del tramos[j:j + 2]
                cambio = True
                break
    return tramos


def absorbe_tramos_cortos(tramos: List[Tramo]) -> List[Tramo]:
    """ Une cada tramo corto intermedio al tramo siguiente (o al anterior si el siguiente es una
    rotonda): el tramo corto es parte de la maniobra, no una calle sobre la que dar una instrucción.

    P. ej. girar de la calle A a la calle C atravesando 10 m de la calle B: la
    instrucción es "gira de A a C", y el giro se mide desde la llegada a B
    hasta la salida hacia C.
    """
    resultado: List[Tramo] = []
    pendiente: Optional[Tramo] = None  # tramo corto que se unirá al siguiente

    for j, tramo in enumerate(tramos):
        if pendiente is not None:
            if tramo.giro_hasta is None:
                tramo.giro_hasta = tramo.inicio
            tramo.inicio = pendiente.inicio
            tramo.longitud += pendiente.longitud
            pendiente = None

        es_intermedio = 0 < j < len(tramos) - 1
        if es_intermedio and not tramo.rotonda and tramo.longitud < TRAMO_CORTO:
            if not tramos[j + 1].rotonda:
                pendiente = tramo
                continue
            if resultado and not resultado[-1].rotonda:
                resultado[-1].une(tramo)
                continue
        resultado.append(tramo)

    return resultado


def lado(angulo: float) -> str:
    return "derecha" if angulo > 0 else "izquierda"


def zigzag(trazado: Trazado, i: int, k: int) -> Optional[Tuple[str, str]]:
    """ Detecta un giro doble entre los vértices i y k del camino (separados pocos metros):
    dos giros fuertes en sentidos contrarios que casi no cambian la dirección final, como
    pasar del lateral a la calzada central de un paseo (izquierda y enseguida derecha).

    Los dos giros se miden con la distancia entre i y k como alcance, para que cada uno
    vea solo el tramo corto que los une.

    Returns:
        Optional[Tuple[str, str]]: lados del primer y del segundo giro, o None si no es un zigzag.
    """
    distancia = trazado.posicion_vertice[k] - trazado.posicion_vertice[i]
    if distancia <= 0:
        return None
    primero = angulo_giro(trazado.rumbo_llegada(i), trazado.rumbo_salida(i, distancia))
    segundo = angulo_giro(trazado.rumbo_llegada(k, distancia), trazado.rumbo_salida(k))
    total = angulo_giro(trazado.rumbo_llegada(i), trazado.rumbo_salida(k))
    if (abs(primero) >= GIRO_MISMA_VIA and abs(segundo) >= GIRO_MISMA_VIA
            and primero * segundo < 0 and abs(total) < LIMITE_LIGERO):
        return lado(primero), lado(segundo)
    return None


def une_continuaciones(trazado: Trazado, tramos: List[Tramo]) -> List[Tramo]:
    """ Une dos tramos seguidos de la misma vía (nombres compatibles, ver misma_via) cuando
    se pasa de uno a otro en línea recta: es la misma calle con un nombre compuesto en OSM,
    no hace falta una instrucción. Se conserva el nombre del primer tramo.
    """
    resultado: List[Tramo] = []
    for tramo in tramos:
        anterior = resultado[-1] if resultado else None
        if (anterior is not None and not anterior.rotonda and not tramo.rotonda
                and misma_via(anterior.nombre, tramo.nombre)):
            angulo = angulo_giro(trazado.rumbo_llegada(tramo.inicio),
                                trazado.rumbo_salida(tramo.vertice_giro))
            if abs(angulo) < LIMITE_RECTO:
                anterior.une(tramo)
                continue
        resultado.append(tramo)
    return resultado


def une_plazas_de_paso(trazado: Trazado, tramos: List[Tramo]) -> List[Tramo]:
    """ Une los tramos de hasta PLAZA_DE_PASO metros que se cruzan en línea recta entre
    dos tramos de la misma calle (p. ej. la Castellana cruzando la glorieta de
    Emilio Castelar): para el conductor es seguir recto por la misma calle.
    """
    def recto(tramo: Tramo) -> bool:
        return abs(angulo_giro(trazado.rumbo_llegada(tramo.inicio),
                            trazado.rumbo_salida(tramo.vertice_giro))) < LIMITE_RECTO

    tramos = list(tramos)
    j = 1
    while j < len(tramos) - 1:
        anterior, medio, siguiente = tramos[j - 1], tramos[j], tramos[j + 1]
        if (not (anterior.rotonda or medio.rotonda or siguiente.rotonda)
                and misma_via(anterior.nombre, siguiente.nombre)
                and medio.longitud <= PLAZA_DE_PASO
                and recto(medio) and recto(siguiente)):
            anterior.une(medio)
            anterior.une(siguiente)
            del tramos[j:j + 2]
        else:
            j += 1
    return tramos


def divide_giros_misma_via(G: nx.DiGraph, vertices: Sequence[object],
                        trazado: Trazado, tramos: List[Tramo]) -> List[Tramo]:
    """ Divide un tramo en los cruces donde la ruta gira sin cambiar de calle.

    Solo se divide si en ese cruce hay otra opción (si no, es una simple curva
    de la calle y no hace falta avisar), el giro es de al menos GIRO_MISMA_VIA
    grados y las dos partes miden al menos TRAMO_CORTO: un giro a pocos metros
    de otra maniobra ya queda recogido en el ángulo de esa maniobra (que se mide
    a DISTANCIA_RUMBO metros), y avisar de él daría instrucciones de pocos metros.

    También se divide donde empieza un zigzag (ver zigzag), aunque el ángulo
    medido sea pequeño: hay que avisar de los dos giros.
    """
    resultado: List[Tramo] = []
    for tramo in tramos:
        if tramo.rotonda:
            resultado.append(tramo)
            continue

        actual = tramo
        i = tramo.vertice_giro + 1
        while i < tramo.fin:
            anterior, vertice = vertices[i - 1], vertices[i]
            alternativas = [w for w in G.successors(vertice) if w != anterior]
            angulo = angulo_giro(trazado.rumbo_llegada(i), trazado.rumbo_salida(i))
            antes = trazado.posicion_vertice[i] - trazado.posicion_vertice[actual.inicio]
            despues = trazado.posicion_vertice[actual.fin] - trazado.posicion_vertice[i]
            if len(alternativas) < 2 or min(antes, despues) < TRAMO_CORTO:
                i += 1
                continue

            # ¿Empieza aquí un zigzag? Se busca el segundo giro a menos de TRAMO_CORTO.
            # Se comprueba antes que el ángulo normal porque, en un zigzag, la medida a
            # DISTANCIA_RUMBO metros mezcla los dos giros y los atenúa.
            doble, k = None, i + 1
            while k < actual.fin and (trazado.posicion_vertice[k]
                                    - trazado.posicion_vertice[i]) < TRAMO_CORTO:
                doble = zigzag(trazado, i, k)
                if doble:
                    break
                k += 1

            if doble is None and abs(angulo) < GIRO_MISMA_VIA:
                i += 1
                continue

            # La longitud de las aristas ("length") y la del trazado casi coinciden;
            # se reparte la longitud del tramo en proporción al trazado.
            proporcion = antes / max(antes + despues, 1e-9)
            primera = Tramo(actual.nombre, actual.inicio, i, actual.longitud * proporcion,
                            False, set(actual.tipos), actual.giro_hasta, actual.zigzag)
            actual = Tramo(actual.nombre, i, actual.fin, actual.longitud * (1 - proporcion),
                        False, set(actual.tipos), zigzag=doble)
            resultado.append(primera)
            i = k + 1 if doble else i + 1
        resultado.append(actual)
    return resultado


def calcula_tramos(G: nx.DiGraph, vertices: Sequence[object], trazado: Trazado) -> List[Tramo]:
    """Divide el camino en tramos sobre los que no hacen falta instrucciones."""
    tramos = tramos_iniciales(G, vertices)
    tramos = une_cruces(tramos)
    tramos = absorbe_tramos_cortos(tramos)
    tramos = une_continuaciones(trazado, tramos)
    tramos = une_plazas_de_paso(trazado, tramos)
    return divide_giros_misma_via(G, vertices, trazado, tramos)


def con_preposicion(preposicion: str, nombre: str) -> str:
    """ Une una preposición y un nombre con las contracciones del español:
    "a" + "el enlace" -> "al enlace", "de" + "el enlace" -> "del enlace".
    """
    if nombre.startswith("el ") and preposicion in ("a", "de"):
        return f"{preposicion}l {nombre[3:]}"
    return f"{preposicion} {nombre}"


def describe_giro(angulo: float) -> str:
    """Verbo del giro según su ángulo (positivo a la derecha)."""
    lado = "derecha" if angulo > 0 else "izquierda"
    a = abs(angulo)
    if a < LIMITE_RECTO:
        return "Sigue recto"
    if a < LIMITE_LIGERO:
        return f"Gira ligeramente a la {lado}"
    if a < LIMITE_NORMAL:
        return f"Gira a la {lado}"
    if a < LIMITE_BRUSCO:
        return f"Gira bruscamente a la {lado}"
    return "Cambia de sentido"


def formatea_distancia(metros: float) -> str:
    """Distancia legible: redondeada a 5 m, a 10 m o en km con un decimal."""
    paso = 5 if metros < 100 else 10
    redondeada = max(paso, paso * round(metros / paso))
    if redondeada >= 1000:
        return f"{metros / 1000:.1f} km".replace(".", ",")
    return f"{redondeada} m"


def formatea_tiempo(segundos: float) -> str:
    """Tiempo legible en segundos, minutos u horas."""
    if segundos < 60:
        return f"{round(segundos)} s"
    minutos = round(segundos / 60)
    if minutos < 60:
        return f"{minutos} min"
    return f"{minutos // 60} h {minutos % 60} min"


def ordinal(n: int) -> str:
    return f"{n}.ª"


@dataclass
class Instruccion:
    """ Instrucción de navegación.

    Attributes:
        texto (str): texto para el conductor.
        indice (int): índice en el camino del vértice donde se hace la maniobra.
        distancia (float): metros que se recorren después de la maniobra.
    """
    texto: str
    indice: int
    distancia: float


class GeneradorInstrucciones:
    """Convierte un camino del grafo de calles en instrucciones de navegación."""

    def __init__(self, G: nx.DiGraph, vertices: Sequence[object]):
        self.G = G
        self.vertices = list(vertices)
        self.trazado = Trazado(G, self.vertices)
        self.tramos = calcula_tramos(G, self.vertices, self.trazado)

    # --- Nombres ---

    def nombre_mostrado(self, j: int) -> str:
        """ Nombre con el que se menciona el tramo j-ésimo. Si la vía no tiene
        nombre, se describe por su tipo y por la siguiente vía con nombre.
        """
        tramo = self.tramos[j]
        if tramo.nombre != callejero.NOMBRE_DESCONOCIDO:
            return tramo.nombre

        base = "el enlace" if es_enlace(tramo) else "la vía sin nombre"
        siguiente = next((t.nombre for t in self.tramos[j + 1:]
                        if t.nombre != callejero.NOMBRE_DESCONOCIDO), None)
        return f"{base} hacia {siguiente}" if siguiente else base

    # --- Maniobras ---

    def angulo_entrada(self, tramo: Tramo) -> float:
        return angulo_giro(self.trazado.rumbo_llegada(tramo.inicio),
                        self.trazado.rumbo_salida(tramo.vertice_giro))

    def hay_semaforo(self, tramo: Tramo) -> bool:
        """True si hay un semáforo en el cruce donde se entra en el tramo."""
        return any(self.G.nodes[self.vertices[i]].get("highway") == "traffic_signals"
                for i in range(tramo.inicio, tramo.vertice_giro + 1))

    def salida_autovia(self, j: int) -> Optional[str]:
        """ Si el tramo j-ésimo sale de una autovía, número de la salida ("" si no se conoce).
        Si no es una salida de autovía, None.
        """
        anterior, tramo = self.tramos[j - 1], self.tramos[j]
        if not (anterior.tipos & TIPOS_AUTOVIA) or (tramo.tipos & TIPOS_AUTOVIA):
            return None
        datos_vertice = self.G.nodes[self.vertices[tramo.inicio]]
        if datos_vertice.get("highway") == "motorway_junction":
            ref = datos_vertice.get("ref")
            return f" {ref}" if isinstance(ref, str) and ref else ""
        # Sin salida numerada, solo se habla de "salida" al dejar una autopista por un
        # enlace: las vías "trunk" incluyen avenidas urbanas (Castellana, Paseo del Prado...)
        if "motorway" in anterior.tipos and es_enlace(tramo):
            return ""
        return None

    def entra_en_autovia(self, j: int) -> bool:
        """True si el tramo j-ésimo es una autovía a la que se llega por un enlace."""
        anterior, tramo = self.tramos[j - 1], self.tramos[j]
        return bool(tramo.tipos & TIPOS_AUTOVIA) and es_enlace(anterior)

    def cuenta_salidas_rotonda(self, tramo: Tramo) -> int:
        """ Número de la salida por la que se abandona la rotonda.

        Se recorren los vértices de la rotonda desde el siguiente al de entrada
        hasta el de salida, y se cuentan los que tienen alguna arista que sale
        de la rotonda (las calles que solo entran en ella no son salidas).
        """
        salidas = 0
        for i in range(tramo.inicio + 1, tramo.fin + 1):
            vertice = self.vertices[i]
            if any(not es_rotonda(self.G[vertice][w]) for w in self.G.successors(vertice)):
                salidas += 1
        return max(salidas, 1)

    def maniobra(self, j: int) -> str:
        """Texto de la maniobra con la que se entra en el tramo j-ésimo (j >= 1, no rotonda)."""
        tramo = self.tramos[j]
        nombre = self.nombre_mostrado(j)

        salida = self.salida_autovia(j)
        if salida is not None:
            return f"Toma la salida{salida} por {nombre}"
        if self.entra_en_autovia(j):
            return f"Incorpórate {con_preposicion('a', nombre)}"

        angulo = self.angulo_entrada(tramo)
        verbo = describe_giro(angulo)
        doble = tramo.zigzag
        if doble is None and tramo.giro_hasta is not None:
            doble = zigzag(self.trazado, tramo.inicio, tramo.giro_hasta)
        if doble:
            verbo = f"Gira a la {doble[0]} y enseguida a la {doble[1]}"
        if misma_via(tramo.nombre, self.tramos[j - 1].nombre):
            texto = f"{verbo} para seguir por {nombre}"
        else:
            if verbo == "Cambia de sentido":
                # Volver hacia atrás por otra calle es un giro muy cerrado, no un cambio de sentido
                verbo = f"Gira bruscamente a la {'derecha' if angulo > 0 else 'izquierda'}"
            texto = f"{verbo} por {nombre}"

        if self.hay_semaforo(tramo) and not verbo.startswith("Sigue"):
            texto = "En el semáforo, " + texto[0].lower() + texto[1:]
        return texto

    # --- Instrucciones ---

    def instrucciones(self) -> List[Instruccion]:
        """Lista de instrucciones desde el origen hasta la llegada al destino."""
        if len(self.vertices) < 2:
            return [Instruccion("Ya estás en tu destino.", 0, 0.0)]

        resultado: List[Instruccion] = []
        j = 0
        while j < len(self.tramos):
            tramo = self.tramos[j]

            if tramo.rotonda:
                texto, distancia, indice, j = self.instruccion_rotonda(j)
            elif j == 0:
                cardinal = punto_cardinal(self.trazado.rumbo_salida(0))
                texto = f"Sal hacia el {cardinal} por {self.nombre_mostrado(0)}"
                distancia, indice, j = tramo.longitud, tramo.inicio, j + 1
            else:
                texto = self.maniobra(j)
                distancia, indice, j = tramo.longitud, tramo.inicio, j + 1

            resultado.append(Instruccion(
                f"{texto} y continúa {formatea_distancia(distancia)}.", indice, distancia))

        resultado.append(Instruccion("Has llegado a tu destino.", len(self.vertices) - 1, 0.0))
        return resultado

    def instruccion_rotonda(self, j: int) -> Tuple[str, float, int, int]:
        """ Instrucción para la rotonda del tramo j-ésimo y la vía por la que se sale.

        Returns:
            (texto, distancia tras la maniobra, índice del vértice, siguiente tramo a tratar)
        """
        tramo = self.tramos[j]
        vecinas = [self.tramos[k].nombre for k in (j - 1, j + 1) if 0 <= k < len(self.tramos)]
        # El nombre de la rotonda solo se menciona si es propio (no el de una calle que llega a ella)
        nombre_propio = (tramo.nombre != callejero.NOMBRE_DESCONOCIDO
                        and not any(misma_via(tramo.nombre, v) for v in vecinas))
        nombre = f" ({tramo.nombre})" if nombre_propio else ""

        if j + 1 >= len(self.tramos):  # el destino está en la propia rotonda
            return f"Entra en la rotonda{nombre}", tramo.longitud, tramo.inicio, j + 1

        salida = self.cuenta_salidas_rotonda(tramo)
        texto = (f"En la rotonda{nombre}, toma la {ordinal(salida)} salida "
                f"hacia {self.nombre_mostrado(j + 1)}")
        return texto, self.tramos[j + 1].longitud, tramo.inicio, j + 2


def instrucciones_ruta(G: nx.DiGraph, vertices: Sequence[object]) -> List[Instruccion]:
    """ Instrucciones de navegación para recorrer el camino dado.

    Args:
        G (nx.DiGraph): grafo de calles procesado (callejero.procesa_grafo).
        vertices (Sequence[object]): vértices del camino, del origen al destino.
    Returns:
        List[Instruccion]: instrucciones en orden, terminando con la llegada.
    """
    return GeneradorInstrucciones(G, vertices).instrucciones()


############## Direcciones ##############

def normaliza_texto(texto: str) -> str:
    """ Pasa un texto al formato del callejero: mayúsculas, sin tildes y con espacios simples.

    Se quitan las tildes (á -> A) pero se conservan la Ñ y la Ü, que sí aparecen
    en el callejero.
    """
    resultado = []
    for caracter in unicodedata.normalize("NFD", texto.upper()):
        if caracter in ("́", "̀"):  # tilde aguda o grave
            continue
        resultado.append(caracter)
    texto = unicodedata.normalize("NFC", "".join(resultado))
    return re.sub(r"\s+", " ", texto).strip()


def separa_numero(texto: str) -> Tuple[str, Optional[int]]:
    """Separa "Calle de X, 12" en ("CALLE DE X", 12). Si no hay número, devuelve None."""
    texto = normaliza_texto(texto)
    coincidencia = re.fullmatch(r"(.*?)[\s,]*(\d+)\s*", texto)
    if coincidencia is None:
        return texto.rstrip(", "), None
    return coincidencia.group(1).rstrip(", "), int(coincidencia.group(2))


class CatalogoCalles:
    """ Calles del callejero y sus números, para sugerir alternativas cuando no se
    encuentra una dirección.
    """

    def __init__(self, direcciones: pd.DataFrame):
        calles = (direcciones["clase"] + " " + direcciones["particula"] + " " + direcciones["nombre"])
        calles = calles.str.replace(r"\s+", " ", regex=True).str.strip()
        numeros = pd.to_numeric(direcciones["numero"].str.extract(r"^NUM(\d+)$")[0], errors="coerce")

        tabla = pd.DataFrame({"calle": calles, "numero": numeros}).dropna()
        self.numeros: Dict[str, List[int]] = {
            calle: sorted(set(grupo.astype(int))) for calle, grupo in tabla.groupby("calle")["numero"]
        }
        self.calles = sorted(set(calles))

    def sugerencias(self, texto: str, maximo: int = 5) -> List[str]:
        """ Calles parecidas a la escrita: primero las que contienen todas sus palabras,
        después las más parecidas según difflib.
        """
        calle, _ = separa_numero(texto)
        if not calle:
            return []
        palabras = calle.split()
        contienen = sorted((c for c in self.calles if all(p in c.split() for p in palabras)), key=len)
        parecidas = difflib.get_close_matches(calle, self.calles, n=maximo, cutoff=0.6)
        resultado = list(dict.fromkeys(contienen[:maximo] + parecidas))
        return [formatea_calle(c) for c in resultado[:maximo]]

    def numeros_cercanos(self, texto: str, maximo: int = 6) -> Optional[List[int]]:
        """ Si la calle existe pero el número no, los números más cercanos que sí existen.
        Si la calle no existe, None.
        """
        calle, numero = separa_numero(texto)
        if calle not in self.numeros:
            return None
        disponibles = self.numeros[calle]
        if numero is None:
            return disponibles[:maximo]
        return sorted(sorted(disponibles, key=lambda n: abs(n - numero))[:maximo])


def formatea_calle(calle: str) -> str:
    """ "CALLE DE ALBERTO AGUILERA" -> "Calle de Alberto Aguilera" (para mostrar al usuario)."""
    minusculas = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y", "A", "AL"}
    palabras = calle.split()
    return " ".join(p.lower() if i > 0 and p in minusculas else p.capitalize()
                    for i, p in enumerate(palabras))


############## Dibujo ##############

def dibuja_ruta(G: nx.DiGraph, ruta: Ruta, instrucciones: List[Instruccion], titulo: str = ""):
    """ Dibuja el callejero con la ruta resaltada, el origen, el destino y los puntos de maniobra.

    La vista se centra en la ruta (con un margen) para que se vea con detalle.

    Returns:
        Los ejes de matplotlib.
    """
    _, ax = plt.subplots(figsize=(10, 10))
    callejero.dibuja_grafo(G, ax=ax, color="#c8c8c8", grosor=0.4)

    trazado = Trazado(G, ruta.vertices)
    xs, ys = zip(*trazado.puntos)
    ax.plot(xs, ys, color="#1f6fd1", linewidth=3, solid_capstyle="round", zorder=3)

    maniobras = [trazado.puntos[0]] + [
        (G.nodes[ruta.vertices[ins.indice]]["x"], G.nodes[ruta.vertices[ins.indice]]["y"])
        for ins in instrucciones[1:-1]
    ]
    ax.scatter(*zip(*maniobras), s=18, color="white", edgecolors="#1f6fd1", zorder=4)
    ax.scatter([xs[0]], [ys[0]], s=90, color="#2ca02c", edgecolors="black", zorder=5, label="Origen")
    ax.scatter([xs[-1]], [ys[-1]], s=90, color="#d62728", edgecolors="black", zorder=5, label="Destino")

    # Encuadre: la ruta con un margen del 15 % (mínimo unos 300 m)
    margen_x = max(0.15 * (max(xs) - min(xs)), 0.0035)
    margen_y = max(0.15 * (max(ys) - min(ys)), 0.0027)
    ax.set_xlim(min(xs) - margen_x, max(xs) + margen_x)
    ax.set_ylim(min(ys) - margen_y, max(ys) + margen_y)

    ax.legend(loc="upper right")
    ax.set_title(titulo)
    return ax
