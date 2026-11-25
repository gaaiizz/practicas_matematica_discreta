"""
grafo.py

Matemática Discreta - IMAT
ICAI, Universidad Pontificia Comillas

Grupo: GPxxx
Integrantes:
    - XX
    - XX

Descripción:
Librería para el análisis de grafos pesados.
"""

from typing import List,Tuple,Dict,Callable,Union
import networkx as nx
import sys

import heapq #Librería para la creación de colas de prioridad

INFTY=sys.float_info.max #Distincia "infinita" entre nodos de un grafo

"""
En las siguientes funciones, las funciones de peso son funciones que reciben un grafo o digrafo y dos vértices y devuelven un real (su peso)
Por ejemplo, si las aristas del grafo contienen en sus datos un campo llamado 'valor', una posible función de peso sería:

def mi_peso(G:nx.Graph,u:object, v:object):
    return G[u][v]['valor']

y, en tal caso, para calcular Dijkstra con dicho parámetro haríamos

camino=dijkstra(G,mi_peso,origen, destino)


"""

def dijkstra(G:Union[nx.Graph, nx.DiGraph], peso:Union[Callable[[nx.Graph,object,object],float], Callable[[nx.DiGraph,object,object],float]], origen:object)-> Dict[object,object]:
    """ Calcula un Árbol de Caminos Mínimos para el grafo pesado partiendo
    del vértice "origen" usando el algoritmo de Dijkstra. Calcula únicamente
    el árbol de la componente conexa que contiene a "origen".
    
    Args:
        origen (object): vértice del grafo de origen
    Returns:
        Dict[object,object]: Devuelve un diccionario que indica, para cada vértice alcanzable
            desde "origen", qué vértice es su padre en el árbol de caminos mínimos.
    Raises:
        TypeError: Si origen no es "hashable".
    Example:
        Si G.dijksra(1)={2:1, 3:2, 4:1} entonces 1 es padre de 2 y de 4 y 2 es padre de 3.
        En particular, un camino mínimo desde 1 hasta 3 sería 1->2->3.
    """
    pass


def camino_minimo(G:Union[nx.Graph, nx.DiGraph], peso:Union[Callable[[nx.Graph,object,object],float], Callable[[nx.DiGraph,object,object],float]] ,origen:object,destino:object)->List[object]:
    """ Calcula el camino mínimo desde el vértice origen hasta el vértice
    destino utilizando el algoritmo de Dijkstra.
    
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
    """
    pass