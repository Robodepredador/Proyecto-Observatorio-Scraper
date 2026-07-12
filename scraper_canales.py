"""Scraping por canal oficial verificado (Fase 3 del protocolo: cosecha).

Por cada canal: top N videos con más comentarios (últimos 3 años) ->
carpeta por canal con subcarpeta por video (video.mkv + comentarios.csv)
+ CSV general. Descarga limitada a 2 GB por corrida.

IMPORTANTE (protocolo de equipo):
- PERSONA/PAIS deben ser tuyos, según la institución que te fue asignada
  en el registro compartido. No corras canales que no te correspondan:
  eso duplica trabajo entre compañeros.
- Cada canal en CANALES ya debe estar verificado como oficial (checklist
  del protocolo) antes de aparecer aquí.
"""
from scraper_yt import (buscar_videos, canal_id_por_handle,
                        procesar_corrida, top_por_comentarios)

# --- Configuración de quién corre esto (para el registro de equipo) ---
PERSONA = "Nombre_Apellido"   # reemplaza con tu nombre, tal como aparece en el Sheet
PAIS = "Peru"                 # país que te fue asignado

# --- Canales YA VERIFICADOS como oficiales para las instituciones que te tocan ---
# Formato: (handle_o_channelId, nombre_institucion)
CANALES = [
    ("@handle_institucion_1", "Nombre_Institucion_1"),
    ("@handle_institucion_2", "Nombre_Institucion_2"),
]
MAX_VIDEOS = 50
TOP_N = 25

if __name__ == "__main__":
    for handle, nombre in CANALES:
        print(f"\n########## Canal: {nombre} ({handle}) ##########")
        channel_id = canal_id_por_handle(handle)
        if not channel_id:
            print(f"[X] No se pudo resolver el handle {handle}. Omitiendo...")
            continue

        videos = buscar_videos(max_videos=MAX_VIDEOS, channel_id=channel_id)
        if not videos:
            print(f"[X] Sin videos para {handle}. Omitiendo...")
            continue

        top_videos = top_por_comentarios(videos, TOP_N)
        if top_videos:
            procesar_corrida(nombre, top_videos,
                             persona=PERSONA, pais=PAIS, institucion=nombre,
                             tipo_fuente="Oficial", bloque_busqueda="N/A (canal oficial)")
