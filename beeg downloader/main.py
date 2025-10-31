"""
Beeg Video Downloader v3.1
Descarga videos de beeg.com usando la API oficial
Compatible con Windows 11
Sin dependencias extras - solo requests
"""

import requests
import re
import json
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

class BeegDownloader:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://beeg.com/',
            'Accept': '*/*',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def extract_video_id(self, url):
        """Extrae el ID del video desde la URL"""
        match = re.search(r'beeg\.com(?:/video)?/(-?\d+)', url)
        if match:
            return match.group(1).lstrip('-')
        return None

    def get_video_data(self, video_id):
        """Obtiene los datos del video desde la API"""
        try:
            api_url = f'https://store.externulls.com/facts/file/{video_id}'
            print(f"[*] Consultando API: {api_url}")
            
            response = self.session.get(api_url, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            print(f"[✓] Datos del video obtenidos")
            return data
            
        except requests.exceptions.HTTPError as e:
            print(f"[!] Error HTTP {e.response.status_code}: {e}")
            return None
        except Exception as e:
            print(f"[!] Error al obtener datos: {e}")
            return None

    def parse_m3u8_simple(self, m3u8_url):
        """Parsea M3U8 sin librerías externas"""
        try:
            response = self.session.get(m3u8_url, timeout=15)
            response.raise_for_status()
            
            content = response.text
            base_url = m3u8_url.rsplit('/', 1)[0] + '/'
            
            segments = []
            for line in content.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    # segmento de video
                    if line.startswith('http'):
                        segments.append(line)
                    else:
                        segments.append(urljoin(base_url, line))
            
            return segments
            
        except Exception as e:
            print(f"[!] Error al parsear M3U8: {e}")
            return []

    def download_segments(self, segments, output_file):
        """Descarga todos los segmentos y los combina con reintentos"""
        try:
            total = len(segments)
            print(f"[*] Descargando {total} segmentos...")
            
            failed_segments = 0
            max_retries = 3
            
            with open(output_file, 'wb') as f:
                for idx, segment_url in enumerate(segments, 1):
                    success = False
                    
                    for retry in range(max_retries):
                        try:
                            response = self.session.get(segment_url, timeout=30)
                            response.raise_for_status()
                            f.write(response.content)
                            success = True
                            break
                            
                        except Exception as e:
                            if retry < max_retries - 1:
                                # Reint
                                continue
                            else:
                                # Último intento fail
                                print(f"\n[!] Segmento {idx} falló después de {max_retries} intentos")
                                failed_segments += 1
                    
                    # progreso barra W que bueno soy
                    percent = (idx / total) * 100
                    bar_length = 40
                    filled = int(bar_length * idx / total)
                    bar = '█' * filled + '-' * (bar_length - filled)
                    status = '✓' if success else '✗'
                    print(f'\r[{bar}] {percent:.1f}% ({idx}/{total}) {status}', end='', flush=True)
            
            print(f"\n[✓] Descarga completada ({total - failed_segments}/{total} segmentos OK)")
            
            if failed_segments > total * 0.1: 
                print(f"[!] Advertencia: {failed_segments} segmentos fallaron")
                return False
            
            return True
            
        except Exception as e:
            print(f"\n[!] Error durante la descarga: {e}")
            return False

    def download_direct(self, url, output_file):
        """Descarga directa sin segmentos"""
        try:
            print(f"[*] Descarga directa desde: {url}")
            response = self.session.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            block_size = 8192
            downloaded = 0
            
            with open(output_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=block_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            bar_length = 40
                            filled = int(bar_length * downloaded / total_size)
                            bar = '█' * filled + '-' * (bar_length - filled)
                            mb_down = downloaded / (1024 * 1024)
                            mb_total = total_size / (1024 * 1024)
                            print(f'\r[{bar}] {percent:.1f}% ({mb_down:.1f}MB/{mb_total:.1f}MB)', end='', flush=True)
            
            print(f"\n[✓] Descarga completada")
            return True
            
        except Exception as e:
            print(f"\n[!] Error en descarga directa: {e}")
            return False

    def process_url(self, url, output_dir='downloads', quality='best'):
        """Procesa y descarga el video"""
        print(f"\n{'='*60}")
        print(f"[*] Procesando: {url}")
        print(f"{'='*60}")
        
        # ID del video
        video_id = self.extract_video_id(url)
        if not video_id:
            print("[!] No se pudo extraer el ID del video")
            return False
        
        print(f"[*] Video ID: {video_id}")
        
        # datos del video
        video_data = self.get_video_data(video_id)
        if not video_data:
            print("[!] No se pudo obtener información del video")
            return False
        
        # print(f"\n[DEBUG] Claves en video_data: {list(video_data.keys())}")
        
        # Obtener título
        title = video_data.get('sf_title', video_data.get('title', f'video_{video_id}'))
        title = re.sub(r'[<>:"/\\|?*]', '', title)[:100]
        print(f"[*] Título: {title}")
        
        # HLS - Probar diferentes estructuras
        hls_resources = {}
        
        # fc_facts
        fc_facts = video_data.get('fc_facts', [])
        if fc_facts:
            # print(f"[DEBUG] Encontrado fc_facts con {len(fc_facts)} elementos")
            first_fact = fc_facts[0]
            # print(f"[DEBUG] Claves en first_fact: {list(first_fact.keys())}")
            hls_resources = first_fact.get('hls_resources', {})
        
        # file.hls_resources
        if not hls_resources:
            file_data = video_data.get('file', {})
            # if file_data:
            #     print(f"[DEBUG] Claves en file: {list(file_data.keys())}")
            hls_resources = file_data.get('hls_resources', {})
        
        # video_data
        if not hls_resources:
            hls_resources = video_data.get('hls_resources', {})
        
        
        if not hls_resources:
            print("[!] No se encontraron recursos de video")
            return False
        
        # calidades disponibles
        available_qualities = {}
        print(f"\n[*] Calidades disponibles:")
        for format_id, video_path in hls_resources.items():
            if not video_path:
                continue
            height_match = re.search(r'fl_cdn_(\d+)', format_id)
            if height_match:
                height = height_match.group(1)
                available_qualities[height] = video_path
                print(f"    - {height}p")
        
        if not available_qualities:
            print("[!] No hay calidades válidas disponibles")
            return False
        
        # calidad
        if quality == 'best':
            selected_quality = max(available_qualities.keys(), key=int)
        elif quality in available_qualities:
            selected_quality = quality
        else:
            selected_quality = max(available_qualities.keys(), key=int)
            print(f"[!] Calidad {quality} no disponible, usando {selected_quality}p")
        
        video_path = available_qualities[selected_quality]
        video_url = f'https://video.beeg.com/{video_path}'
        
        print(f"\n[*] Calidad seleccionada: {selected_quality}p")
        print(f"[*] URL del video: {video_url}")
        
        # directorio de salida
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        filename = f"{title}_{selected_quality}p.mp4"
        output_file = output_path / filename
        
        # Intentardescarga
        print(f"\n[*] Método: Descarga de M3U8 (HLS)")
        
        # M3U8
        segments = self.parse_m3u8_simple(video_url)
        
        if segments:
            success = self.download_segments(segments, output_file)
        else:
            # descarga directa si M3U8 f
            print(f"[*] Intentando descarga directa...")
            # URL M3U8 a MP4 directo
            mp4_url = video_url.replace('/index.m3u8', '.mp4').replace('.m3u8', '.mp4')
            success = self.download_direct(mp4_url, output_file)
        
        if success and os.path.exists(output_file):
            file_size = os.path.getsize(output_file) / (1024 * 1024)
            print(f"\n[✓] Video guardado exitosamente")
            print(f"[✓] Ubicación: {output_file}")
            print(f"[✓] Tamaño: {file_size:.2f} MB")
            return True
        else:
            print(f"\n[!] La descarga falló")
            if os.path.exists(output_file):
                os.remove(output_file)
            return False


def main():
    print("""
    ╔═══════════════════════════════════════════════════╗
    ║         Beeg Video Downloader                     ║
    ║         Hecho en windows 11                       ║
    ║              FUCK COPYRIGHT                       ║
    ╚═══════════════════════════════════════════════════╝
    """)
    
    downloader = BeegDownloader()
    
    # Modo línea de comandos
    if len(sys.argv) > 1:
        url = sys.argv[1]
        quality = sys.argv[2] if len(sys.argv) > 2 else 'best'
        downloader.process_url(url, quality=quality)
    else:
        # interactividad W
        while True:
            print("\n" + "="*60)
            url = input("Ingresa la URL del video de Beeg (o 'q' para salir): ").strip()
            
            if url.lower() == 'q':
                print("\n[*] Saliendo...")
                break
            
            if not url:
                continue
            
            print("\nCalidades: best, 1080, 720, 480, 360, 240")
            quality = input("Selecciona calidad (Enter = 'best'): ").strip() or 'best'
            
            downloader.process_url(url, quality=quality)
            
            continuar = input("\n¿Descargar otro video? (s/n): ").strip().lower()
            if continuar != 's':
                print("\n[*] Saliendo...")
                break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[!] Proceso interrumpido por el usuario")
        sys.exit(0)