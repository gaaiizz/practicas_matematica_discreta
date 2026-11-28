"""
grafo_pesado.py

Matemática Discreta - IMAT
ICAI, Universidad Pontificia Comillas

Grupo: GP02A
Integrantes:
    - Carlos Fracaro Solo de Zaldívar
    - Luis Adrián García Ruiz

Descripción:
Librería para el análisis de grafos pesados: árbol de caminos mínimos y
camino mínimo entre dos vértices con el algoritmo de Dijkstra.

El algoritmo usa una cola de prioridad (montículo binario, módulo heapq) para
elegir en cada paso el vértice no visitado más cercano al origen. Con n vértices
y m aristas, el coste es O((n + m) log n), frente a O(n^2) si ese vértice se
busca recorriendo todos los vértices en cada paso.
"""

from typing import List, Tuple, Dict, Callable, Union, Optional
import networkx as nx
import sys

import heapq  # Librería para la creación de colas de prioridad
from itertools import count

INFTY = sys.float_info.max  # Distancia "infinita" entre nodos de un grafo

"""
En las siguientes funciones, las funciones de peso son funciones que reciben un grafo o digrafo y dos vértices y devuelven un real (su peso)
Por ejemplo, si las aristas del grafo contienen en sus datos un campo llamado 'valor', una posible función de peso sería:

def mi_peso(G:nx.Graph,u:object, v:object):
    return G[u][v]['valor']

y, en tal caso, para calcular Dijkstra con dicho parámetro haríamos

camino=dijkstra(G,mi_peso,origen, destino)


"""

FuncionPeso = Union[Callable[[nx.Graph, object, object], float],
                    Callable[[nx.DiGraph, object, object], float]]


def _dijkstra(G: Union[nx.Graph, nx.DiGraph], peso: FuncionPeso, origen: object,
              destino: Optional[object] = None) -> Dict[object, object]:
    """ Algoritmo de Dijkstra desde "origen", según el pseudocódigo del tema 6. Si se
    indica "destino", se detiene en cuanto "destino" pasa a ser permanente (es lo
    único que necesita camino_minimo).

    Correspondencia con el pseudocódigo:
        d[v]       -> distancia[v] (los vértices que no aparecen tienen d[v] = INFTY)
        P          -> permanentes: vértices cuya distancia ya es definitiva
        Tr         -> los vértices que no están en P (no hace falta guardarlos aparte)
        padre de v -> padre[v]; al acabar, es el árbol de caminos mínimos
    Paso 1 (buscar el v_k de Tr con d mínima) se hace con un montículo ("cola") de
    tuplas (distancia, desempate, vértice) en lugar de recorrer Tr entero: así cada
    búsqueda cuesta O(log n) en vez de O(n), y el algoritmo O((n + m) log n) en vez
    de O(n^2).

    Notas de implementación:
        - heapq no permite rebajar la prioridad de un elemento que ya está en el
          montículo. Cuando d[v] mejora en el paso 2, se añade una entrada nueva y,
          al sacar en el paso 1 una entrada de un vértice que ya es permanente, se
          descarta (es una entrada obsoleta). El montículo puede llegar a tener m
          entradas: el coste es O(m log m) = O(m log n), porque m <= n^2.
        - En el paso 2 basta con mirar los vecinos de v_k que siguen en Tr: para
          los demás vértices w(v_k v_j) = infinito y d[v_j] no cambia.
        - El algoritmo termina cuando el montículo se vacía: todos los vértices
          alcanzables desde el origen son ya permanentes. Los no alcanzables nunca
          entran (su d sigue siendo infinita), así que el árbol es el de la
          componente del origen.
        - El contador de desempate evita que, con dos distancias iguales, Python
          compare los vértices: pueden ser de tipos no comparables entre sí
          (p. ej. 1 y 'a') y daría TypeError.

    Raises:
        TypeError: si origen no es "hashable".
        nx.NodeNotFound: si origen no es un vértice de G.
        ValueError: si alguna arista explorada tiene peso negativo (Dijkstra no es
            válido con pesos negativos).
    """
    hash(origen)  # TypeError si origen no es hashable
    if origen not in G:
        raise nx.NodeNotFound(f"El vértice {origen!r} no está en el grafo")

    # Paso 0: d[o] = 0. El resto de vértices empieza con d = infinito y, en la primera
    # vuelta, el paso 2 aplicado al origen les da d[v_j] = w(o v_j), como en el pseudocódigo.
    distancia: Dict[object, float] = {origen: 0}
    padre: Dict[object, object] = {}
    permanentes = set()  # P
    desempate = count()
    cola: List[Tuple[float, int, object]] = [(0, next(desempate), origen)]

    while cola:  # mientras quede algún vértice de Tr alcanzable
        # Paso 1: v_k = vértice de Tr con d mínima; pasa de Tr a P
        d_k, _, v_k = heapq.heappop(cola)
        if v_k in permanentes:
            continue  # entrada obsoleta: v_k ya salió antes con una distancia menor
        permanentes.add(v_k)

        if v_k == destino:
            break

        # Paso 2: d[v_j] = min(d[v_j], d[v_k] + w(v_k v_j)) para los v_j de Tr vecinos
        # de v_k (en un grafo dirigido, G.neighbors(v_k) son los sucesores de v_k)
        for v_j in G.neighbors(v_k):
            if v_j in permanentes:
                continue
            w_kj = peso(G, v_k, v_j)
            if w_kj < 0:
                raise ValueError(f"La arista ({v_k!r}, {v_j!r}) tiene peso negativo: {w_kj}")
            nueva = d_k + w_kj
            if nueva < distancia.get(v_j, INFTY):
                distancia[v_j] = nueva
                padre[v_j] = v_k  # v_k pasa a ser el padre de v_j
                heapq.heappush(cola, (nueva, next(desempate), v_j))

    return padre


def dijkstra(G: Union[nx.Graph, nx.DiGraph], peso: FuncionPeso, origen: object) -> Dict[object, object]:
    """ Calcula un Árbol de Caminos Mínimos para el grafo pesado partiendo
    del vértice "origen" usando el algoritmo de Dijkstra. Calcula únicamente
    el árbol de la componente conexa que contiene a "origen".

    Args:
        G (nx.Graph o nx.DiGraph): grafo o grafo dirigido
        peso (función): función que recibe un grafo o grafo dirigido y dos vértices del mismo
            y devuelve el peso (no negativo) de la arista que los conecta
        origen (object): vértice del grafo de origen
    Returns:
        Dict[object,object]: Devuelve un diccionario que indica, para cada vértice alcanzable
            desde "origen", qué vértice es su padre en el árbol de caminos mínimos.
    Raises:
        TypeError: Si origen no es "hashable".
        nx.NodeNotFound: Si origen no es un vértice del grafo.
        ValueError: Si alguna arista alcanzable tiene peso negativo.
    Example:
        Si G.dijksra(1)={2:1, 3:2, 4:1} entonces 1 es padre de 2 y de 4 y 2 es padre de 3.
        En particular, un camino mínimo desde 1 hasta 3 sería 1->2->3.
    """
    return _dijkstra(G, peso, origen)


def camino_minimo(G: Union[nx.Graph, nx.DiGraph], peso: FuncionPeso,
                  origen: object, destino: object) -> List[object]:
    """ Calcula el camino mínimo desde el vértice origen hasta el vértice
    destino utilizando el algoritmo de Dijkstra.

    Dijkstra se detiene en cuanto "destino" pasa a ser permanente: en ese momento
    todos los vértices del camino ya son permanentes, así que no hace falta calcular
    el árbol completo. El camino se obtiene como en el tema 6: el padre de destino,
    el padre de ese padre... hasta llegar al origen.

    Args:
        G (nx.Graph o nx.Digraph): grafo a grado dirigido
        peso (función): función que recibe un grafo o grafo dirigido y dos vértices del mismo y devuelve el peso de la arista que los conecta
        origen (object): vértice del grafo de origen
        destino (object): vértice del grafo de destino
    Returns:
        List[object]: Devuelve una lista con los vértices del grafo por los que pasa
            el camino más corto entre el origen y el destino. El primer elemento de
            la lista es origen y el último destino.
    Example:
        Si dijksra(G,peso,1,4)=[1,5,2,4] entonces el camino más corto en G entre 1 y 4 es 1->5->2->4.
    Raises:
        TypeError: Si origen o destino no son "hashable".
        nx.NodeNotFound: Si origen o destino no son vértices del grafo.
        nx.NetworkXNoPath: Si no hay ningún camino de origen a destino.
        ValueError: Si alguna arista explorada tiene peso negativo.
    """
    hash(destino)  # TypeError si destino no es hashable
    if destino not in G:
        raise nx.NodeNotFound(f"El vértice {destino!r} no está en el grafo")

    padre = _dijkstra(G, peso, origen, destino)
    if destino != origen and destino not in padre:
        raise nx.NetworkXNoPath(f"No hay camino de {origen!r} a {destino!r}")

    # Se reconstruye el camino subiendo por el árbol desde destino hasta origen
    camino = [destino]
    while camino[-1] != origen:
        camino.append(padre[camino[-1]])
    camino.reverse()
    return camino
