"""
gps.py

Matemática Discreta - IMAT
ICAI, Universidad Pontificia Comillas

Grupo: GP02A
Integrantes:
    - Carlos Fracaro Solo de Zaldívar
    - Luis Adrián García Ruiz

Descripción:
Navegador por las calles de Madrid (parte 6). Al arrancar lee el callejero
(direcciones.csv) y construye el grafo de calles. Después, en bucle:
    1. Pide la dirección de origen y la de destino.
    2. Pide el tipo de ruta: más corta, más rápida o más ecológica.
    3. Calcula la ruta óptima con grafo_pesado y muestra las instrucciones.
    4. Dibuja la ruta sobre el callejero.
El programa termina cuando se deja vacío el origen o el destino.

Uso:
    python gps.py
"""

import time
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

import callejero
import navegacion as nav

# Si una dirección está más lejos que esto (m) del cruce más cercano, se avisa
DISTANCIA_AVISO = 100.0

EJEMPLO_DIRECCION = "Calle de Alberto Aguilera, 23"


def carga_datos() -> Optional[Tuple[pd.DataFrame, nx.DiGraph]]:
    """ Carga el callejero y el grafo de calles. Devuelve None si no es posible.

    Returns:
        Optional[Tuple[pd.DataFrame, nx.DiGraph]]: (direcciones, grafo de calles procesado).
    """
    inicio = time.time()
    print("Cargando el callejero...")
    direcciones = callejero.carga_callejero()
    if direcciones is None:
        print(f"No se encuentra el fichero {callejero.STREET_FILE_NAME}.")
        return None

    print("Cargando el grafo de calles (la primera vez se descarga y puede tardar)...")
    try:
        multidigrafo = callejero.carga_grafo()
    except callejero.ServiceNotAvailableError as error:
        print(f"{error}. Comprueba la conexión a internet y vuelve a intentarlo.")
        return None

    grafo = callejero.procesa_grafo(multidigrafo)
    print(f"Listo en {time.time() - inicio:.1f} s: {grafo.number_of_nodes()} cruces y "
            f"{grafo.number_of_edges()} tramos de calle.\n")
    return direcciones, grafo


def muestra_ayuda(texto: str, catalogo: nav.CatalogoCalles) -> None:
    """Explica por qué no se ha encontrado una dirección y sugiere alternativas."""
    numeros = catalogo.numeros_cercanos(texto)
    if numeros is not None:
        print("  Esa calle existe, pero no ese número. Números cercanos: "
            + ", ".join(map(str, numeros)))
        return

    sugerencias = catalogo.sugerencias(texto)
    if sugerencias:
        print("  No se ha encontrado esa dirección. ¿Quizás quisiste decir...?")
        for sugerencia in sugerencias:
            print(f"    - {sugerencia}")
    else:
        print(f"  No se ha encontrado esa dirección. Escríbela así: {EJEMPLO_DIRECCION}")


def pide_direccion(etiqueta: str, direcciones: pd.DataFrame, catalogo: nav.CatalogoCalles,
                indice: nav.IndiceVertices) -> Optional[Tuple[str, object]]:
    """ Pide una dirección hasta que se escribe una que existe.

    Returns:
        Optional[Tuple[str, object]]: (dirección escrita, vértice del grafo más cercano),
            o None si se deja vacía (para salir del programa).
    """
    while True:
        try:
            texto = input(f"{etiqueta} (vacío para salir): ").strip()
        except EOFError:
            return None
        if not texto:
            return None

        try:
            latitud, longitud = callejero.busca_direccion(nav.normaliza_texto(texto), direcciones)
        except callejero.AddressNotFoundError:
            muestra_ayuda(texto, catalogo)
            continue

        vertice, distancia = indice.mas_cercano(latitud, longitud)
        if distancia > DISTANCIA_AVISO:
            print(f"  Aviso: la dirección está a {nav.formatea_distancia(distancia)} "
                f"del cruce más cercano accesible en coche.")
        return texto, vertice


def pide_modo() -> nav.Modo:
    """Pide el tipo de ruta. Si se deja vacío, se usa la más corta."""
    opciones = "   ".join(f"[{clave}] {modo.nombre}" for clave, modo in nav.MODOS.items())
    while True:
        try:
            eleccion = input(f"Tipo de ruta: {opciones} (vacío = 1): ").strip() or "1"
        except EOFError:
            eleccion = "1"
        if eleccion in nav.MODOS:
            return nav.MODOS[eleccion]
        print("  Escribe 1, 2 o 3.")


def muestra_ruta(grafo: nx.DiGraph, ruta: nav.Ruta, modo: nav.Modo,
                origen: str, destino: str) -> None:
    """Escribe las instrucciones de la ruta y la dibuja sobre el callejero."""
    instrucciones = nav.instrucciones_ruta(grafo, ruta.vertices)
    resumen = (f"{nav.formatea_distancia(ruta.longitud)} · {nav.formatea_tiempo(ruta.tiempo)} · "
            f"{ruta.consumo:.2f} L".replace(".", ","))

    print(f"\nRuta {modo.nombre} de {origen} a {destino}")
    print(f"{resumen}\n")
    for numero, instruccion in enumerate(instrucciones, start=1):
        print(f"{numero:3}. {instruccion.texto}")

    nav.dibuja_ruta(grafo, ruta, instrucciones, f"Ruta {modo.nombre}: {resumen}")
    print("\nCierra la ventana del mapa para calcular otra ruta.\n")
    plt.show()
    plt.close("all")


def main() -> None:
    datos = carga_datos()
    if datos is None:
        return
    direcciones, grafo = datos
    indice = nav.IndiceVertices(grafo)
    catalogo = nav.CatalogoCalles(direcciones)

    print(f"Escribe las direcciones como en este ejemplo: {EJEMPLO_DIRECCION}\n")
    while True:
        origen = pide_direccion("Origen", direcciones, catalogo, indice)
        if origen is None:
            break
        destino = pide_direccion("Destino", direcciones, catalogo, indice)
        if destino is None:
            break
        modo = pide_modo()

        try:
            ruta = nav.calcula_ruta(grafo, origen[1], destino[1], modo.peso)
        except nav.RutaNoEncontradaError as error:
            print(f"  {error}.\n")
            continue

        muestra_ruta(grafo, ruta, modo, origen[0], destino[0])

    print("¡Hasta pronto!")


if __name__ == "__main__":
    main()
