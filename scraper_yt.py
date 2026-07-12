import csv
import os
import re
import sys

# Consola Windows (cp1252) no soporta emojis de los títulos.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import glob
import shutil
import datetime
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from httplib2 import Http

# Carga las variables definidas en el archivo .env (si existe) al entorno del proceso.
load_dotenv()

API_KEY = os.environ.get("YOUTUBE_API_KEY")
if not API_KEY:
    raise SystemExit(
        "Falta la variable de entorno YOUTUBE_API_KEY.\n"
        "1. Copia .env.example como .env\n"
        "2. Pega tu API key ahí\n"
        "3. Vuelve a ejecutar el script."
    )

CARPETA_BASE = "videosYT"

# Http(...) desactiva la verificación SSL (red corporativa con proxy/inspección).
# Si no estás en una red con ese proxy, puedes quitar el parámetro http= por completo.
youtube = build("youtube", "v3", developerKey=API_KEY,
                http=Http(disable_ssl_certificate_validation=True))


def canal_id_por_handle(handle):
    """Resuelve un handle (@canal) al channelId UC... (los UC... pasan directo)."""
    if handle.startswith("UC"):
        return handle
    response = youtube.channels().list(part="id", forHandle=handle).execute()
    items = response.get("items", [])
    return items[0]["id"] if items else None


def buscar_videos(query=None, max_videos=50, category_id=None, channel_id=None):
    """IDs de videos (por consulta o por canal), publicados en los últimos 3 años."""
    print(f"Buscando videos para: '{query or channel_id}'...")
    encontrados = []
    next_page_token = None
    desde = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(days=3 * 365)).isoformat().replace("+00:00", "Z")

    while len(encontrados) < max_videos:
        try:
            kwargs = dict(part="id", type="video", publishedAfter=desde,
                          regionCode="PE", relevanceLanguage="es",
                          maxResults=min(50, max_videos - len(encontrados)))
            if query:
                kwargs["q"] = query
            if channel_id:
                kwargs["channelId"] = channel_id
            if next_page_token:
                kwargs["pageToken"] = next_page_token
            if category_id:
                kwargs["videoCategoryId"] = category_id

            response = youtube.search().list(**kwargs).execute()
            for item in response.get("items", []):
                if item["id"].get("kind") == "youtube#video" and item["id"].get("videoId"):
                    encontrados.append(item["id"]["videoId"])

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
        except HttpError as e:
            print(e.content.decode("utf-8", errors="ignore"))
            break

    print(f"-> {len(encontrados)} videos hallados.")
    return encontrados


def _duracion_iso8601_a_segundos(duracion):
    """Convierte 'PT1H2M3S' (formato ISO 8601 de YouTube) a segundos totales."""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duracion or "")
    if not match:
        return 0
    horas, minutos, segundos = (int(g) if g else 0 for g in match.groups())
    return horas * 3600 + minutos * 60 + segundos


def top_por_comentarios(video_ids, top_n=5):
    """Los top_n videos con más comentarios (videos.list admite 50 IDs por llamada).

    Se pide contentDetails en la misma llamada (sin costo extra de cuota) para
    registrar la duración de cada video y poder llevar el conteo de horas del equipo.
    """
    print(f"Evaluando {len(video_ids)} videos para hallar los {top_n} con más comentarios...")
    stats = []
    for inicio in range(0, len(video_ids), 50):
        try:
            response = youtube.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(video_ids[inicio:inicio + 50])
            ).execute()
            for item in response.get("items", []):
                duracion_seg = _duracion_iso8601_a_segundos(
                    item.get("contentDetails", {}).get("duration"))
                stats.append({
                    "video_id": item.get("id"),
                    "titulo": item.get("snippet", {}).get("title", "Sin título"),
                    "comentarios": int(item.get("statistics", {}).get("commentCount", 0)),
                    "duracion_seg": duracion_seg,
                    "duracion_min": round(duracion_seg / 60, 1),
                })
        except HttpError as e:
            print(f"Error en lote de estadísticas: {e}")

    top = sorted(stats, key=lambda v: v["comentarios"], reverse=True)[:top_n]
    print("-> Top seleccionado:")
    for pos, v in enumerate(top, 1):
        print(f"   {pos}. [{v['comentarios']} comentarios] {v['titulo']} ({v['video_id']})")
    return top


def _paginar_comentarios(metodo, **kwargs):
    """Itera snippets de comentarios sobre cualquier endpoint paginado (.list)."""
    token = None
    while True:
        response = metodo(maxResults=100, textFormat="plainText", pageToken=token, **kwargs).execute()
        for item in response.get("items", []):
            yield item
        token = response.get("nextPageToken")
        if not token:
            break


def escribir_fila(escritores, snippet):
    fila = {"Fecha": snippet.get("publishedAt", ""),
            "Comentario": snippet.get("textDisplay", ""),
            "Likes": snippet.get("likeCount", 0)}
    for w in escritores:
        w.writerow(fila)


def extraer_comentarios(video_id, escritores):
    """Comentarios de nivel superior + todas sus respuestas -> escritores CSV."""
    print(f"Extrayendo comentarios del video {video_id}...")
    contador = 0
    try:
        for item in _paginar_comentarios(youtube.commentThreads().list,
                                         part="snippet", videoId=video_id):
            top = item["snippet"]["topLevelComment"]["snippet"]
            escribir_fila(escritores, top)
            contador += 1

            if item["snippet"].get("totalReplyCount", 0) > 0:
                for reply in _paginar_comentarios(youtube.comments().list,
                                                  part="snippet", parentId=item["id"]):
                    escribir_fila(escritores, reply["snippet"])
                    contador += 1
    except HttpError as e:
        if e.resp.status == 403 and "commentsDisabled" in str(e.content):
            print(f"  [X] Comentarios deshabilitados en {video_id}. Omitiendo...")
        elif e.resp.status == 404:
            print(f"  [X] Video {video_id} no existe (404). Omitiendo...")
        else:
            print(f"  [X] Error {e.resp.status} en {video_id}.")

    print(f"  -> +{contador} comentarios.")
    return contador


def sanear_nombre(nombre):
    """Título/consulta -> nombre de carpeta válido en Windows."""
    nombre = re.sub(r'[<>:"/\\|?*]', "", nombre)
    return re.sub(r"\s+", "_", nombre.strip())[:80] or "video"


def localizar_ffmpeg():
    """Ruta a ffmpeg (PATH o instalación winget). Sin él, yt-dlp cae a ~720p."""
    en_path = shutil.which("ffmpeg")
    if en_path:
        return en_path
    patron = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet",
                          "Packages", "Gyan.FFmpeg*", "**", "bin", "ffmpeg.exe")
    encontrados = glob.glob(patron, recursive=True)
    return encontrados[0] if encontrados else None


def descargar_video(video_id, carpeta_destino):
    """Descarga el video (<=1080p, fusión a MKV) con yt-dlp."""
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        print("  [!] Falta yt-dlp. Ejecuta: pip install yt-dlp")
        return False

    ffmpeg = localizar_ffmpeg()
    if not ffmpeg:
        print("  [!] Sin ffmpeg la calidad puede limitarse a ~720p (winget install Gyan.FFmpeg).")

    opciones = {
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "merge_output_format": "mkv",
        "outtmpl": os.path.join(carpeta_destino, "video.%(ext)s"),
        "nocheckcertificate": True,
        "quiet": True,
        "no_warnings": True,
    }
    if ffmpeg:
        opciones["ffmpeg_location"] = os.path.dirname(ffmpeg)

    try:
        print(f"  Descargando video {video_id}...")
        with YoutubeDL(opciones) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        print("  -> Video descargado.")
        return True
    except Exception as e:
        print(f"  [X] No se pudo descargar {video_id}: {e}")
        return False


COLUMNAS = ("Fecha", "Comentario", "Likes")
LIMITE_DESCARGA_BYTES = 2 * 1024 ** 3  # 2 GB por corrida de script
_bytes_descargados = 0  # acumulado de toda la corrida

# Registro de avance del equipo: cada corrida agrega filas acá, listas para
# copiar y pegar en el Google Sheet compartido. No se sobreescribe entre corridas.
#
# Tipo_Fuente distingue si el video es del canal OFICIAL de la institución o de
# un TERCERO (vlogger, canal de noticias, egresado, comparativa, etc.) que habla
# de su oferta. scraper_canales.py siempre cosecha canal oficial -> se llena solo.
# scraper_consulta.py puede traer una mezcla -> se deja en blanco para que la
# persona revise cada video y lo marque a mano en el Sheet antes de subirlo.
ARCHIVO_REGISTRO_EQUIPO = "registro_avance_equipo.csv"
COLUMNAS_REGISTRO = ("Fecha_scrapeo", "Persona", "Pais", "Institucion", "Tipo_Fuente",
                     "Bloque_Busqueda", "Video_id", "Titulo", "Duracion_min", "Comentarios")


def registrar_avance(persona, pais, institucion, top_videos, tipo_fuente="", bloque_busqueda=""):
    """Agrega una fila por video al registro compartido (para pegar en el Sheet)."""
    existe = os.path.isfile(ARCHIVO_REGISTRO_EQUIPO)
    with open(ARCHIVO_REGISTRO_EQUIPO, "a", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS_REGISTRO)
        if not existe:
            escritor.writeheader()
        hoy = datetime.date.today().isoformat()
        for info in top_videos:
            escritor.writerow({
                "Fecha_scrapeo": hoy,
                "Persona": persona,
                "Pais": pais,
                "Institucion": institucion,
                "Tipo_Fuente": tipo_fuente,
                "Bloque_Busqueda": bloque_busqueda,
                "Video_id": info["video_id"],
                "Titulo": info["titulo"],
                "Duracion_min": info.get("duracion_min", ""),
                "Comentarios": info["comentarios"],
            })

    minutos_corrida = sum(v.get("duracion_min", 0) for v in top_videos)
    aviso_tipo_fuente = ("" if tipo_fuente else
                         " Revisa cada video y marca Tipo_Fuente (Oficial/Tercero) en el Sheet.")
    print(f"\n[Registro] +{len(top_videos)} videos ({minutos_corrida/60:.1f} horas) "
          f"agregados a '{ARCHIVO_REGISTRO_EQUIPO}'. Copia estas filas al Sheet compartido."
          f"{aviso_tipo_fuente}")


def procesar_corrida(nombre, top_videos, columnas=COLUMNAS,
                     persona=None, pais=None, institucion=None,
                     tipo_fuente="", bloque_busqueda=""):
    """Carpeta de corrida + carpeta por video (mkv + csv) + csv general.

    Si se pasan persona/pais/institucion, además registra el avance en
    ARCHIVO_REGISTRO_EQUIPO para consolidar horas de todo el equipo.
    """
    global _bytes_descargados
    carpeta_corrida = os.path.join(CARPETA_BASE, sanear_nombre(nombre))
    archivo_general = os.path.join(carpeta_corrida, "comentarios_masivos_yt.csv")
    os.makedirs(carpeta_corrida, exist_ok=True)

    total = 0
    with open(archivo_general, "w", newline="", encoding="utf-8-sig") as f_general:
        escritor_general = csv.DictWriter(f_general, fieldnames=columnas)
        escritor_general.writeheader()

        for pos, info in enumerate(top_videos, 1):
            carpeta = os.path.join(carpeta_corrida, f"{pos:02d}_{sanear_nombre(info['titulo'])}")
            os.makedirs(carpeta, exist_ok=True)
            print(f"\n=== Video {pos}/{len(top_videos)}: {info['titulo']} ===")

            if _bytes_descargados >= LIMITE_DESCARGA_BYTES:
                print(f"  [!] Límite de {LIMITE_DESCARGA_BYTES // 1024**3} GB alcanzado: "
                      "se omite la descarga, solo comentarios.")
            elif descargar_video(info["video_id"], carpeta):
                _bytes_descargados += sum(
                    os.path.getsize(p) for p in glob.glob(os.path.join(carpeta, "video.*")))
                print(f"  (acumulado: {_bytes_descargados / 1024**2:.0f} MB)")

            with open(os.path.join(carpeta, "comentarios.csv"), "w",
                      newline="", encoding="utf-8-sig") as f_video:
                escritor_video = csv.DictWriter(f_video, fieldnames=columnas)
                escritor_video.writeheader()
                total += extraer_comentarios(info["video_id"], [escritor_video, escritor_general])

    print(f"\nListo: {len(top_videos)} videos en '{carpeta_corrida}'.")
    print(f"{total} comentarios en '{archivo_general}'.")

    if persona and pais and institucion:
        registrar_avance(persona, pais, institucion, top_videos,
                         tipo_fuente=tipo_fuente, bloque_busqueda=bloque_busqueda)
    else:
        print("[!] No se registró avance de equipo (falta persona/pais/institucion). "
              "Pasa estos datos a procesar_corrida() para llevar el conteo de horas.")
