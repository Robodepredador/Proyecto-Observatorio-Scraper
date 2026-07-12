"""Scraping por consulta de texto — descubrimiento + cosecha en un solo paso.

Busca en TODO YouTube (canal oficial de la institucion O terceros: vloggers,
noticias, testimonios, comparativas) videos que hablen de la oferta de una
institucion especifica. Descarga video + comentarios directamente.

IMPORTANTE (protocolo de equipo):
- Usa esto para una institución que TE FUE ASIGNADA. No busques instituciones
  de otros países/personas: revisa el registro compartido antes de correr.
- Después de cada corrida, REVISA cada video antes de subir el registro al
  Sheet: marca en la columna Tipo_Fuente si es "Oficial" (canal de la propia
  institución) o "Tercero" (cualquier otro canal). El script no puede saberlo
  solo -> queda en blanco a propósito para que tú lo confirmes.
- Corre esto varias veces por institución, una por cada BLOQUE_ACTUAL, para
  cubrir las 12 etiquetas de la guía de anotación (ver tabla más abajo).
"""
from scraper_yt import buscar_videos, procesar_corrida, top_por_comentarios

# --- Configuración de quién corre esto (para el registro de equipo) ---
PERSONA = "Nombre_Apellido"        # reemplaza con tu nombre, tal como en el Sheet
PAIS = "Peru"                      # país asignado
INSTITUCION = "Nombre_Institucion"  # institución asignada que estás explorando

# --- Bloques de búsqueda: cubren las 12 etiquetas de la guía en 6 corridas ---
# Cambia BLOQUE_ACTUAL y vuelve a correr el script para cada bloque.
BLOQUES = {
    "Ingreso":     ("matricula admision", "Matricula, Admision"),
    "Dinero":      ("pension beca costo", "Costo, Beca"),
    "Programas":   ("carreras maestria posgrado", "Carrera, Postgrado"),
    "Calidad":     ("acreditacion docentes", "CalidadAcademica, Docente"),
    "Vida_Campus": ("campus laboratorios vida universitaria", "Infraestructura, VidaUniversitaria"),
    "Experiencia": ("modalidad virtual experiencia estudiante", "Modalidad, Testimonio"),
}
BLOQUE_ACTUAL = "Ingreso"  # <- cambia esto en cada corrida: Ingreso / Dinero / Programas / Calidad / Vida_Campus / Experiencia

# Valores reducidos para la PRIMERA PRUEBA (barato en cuota).
# Cuando confirmes que todo funciona, puedes subir estos números.
MAX_VIDEOS = 5
TOP_N = 2

if __name__ == "__main__":
    terminos, etiquetas_cubiertas = BLOQUES[BLOQUE_ACTUAL]
    CONSULTA = f"{INSTITUCION} {terminos}"
    print(f"Bloque: {BLOQUE_ACTUAL} (cubre etiquetas: {etiquetas_cubiertas})")
    print(f"Consulta: {CONSULTA}")

    videos = buscar_videos(query=CONSULTA, max_videos=MAX_VIDEOS)
    if not videos:
        raise SystemExit("Sin IDs válidos para explorar.")

    top_videos = top_por_comentarios(videos, TOP_N)
    if not top_videos:
        raise SystemExit("No se pudieron obtener estadísticas.")

    procesar_corrida(f"{INSTITUCION}_{BLOQUE_ACTUAL}", top_videos,
                     persona=PERSONA, pais=PAIS, institucion=INSTITUCION,
                     bloque_busqueda=BLOQUE_ACTUAL)
