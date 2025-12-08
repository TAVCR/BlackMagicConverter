import os
import subprocess
import threading
from flask import Flask, render_template_string, request, redirect, url_for

app = Flask(__name__)

# RUTA BASE: Empezamos buscando en la carpeta DCIM general
BASE_DIR = '/storage/emulated/0/DCIM'
PORT = 8080

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Video Compressor</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #000; color: #fff; padding: 20px; }
        h1 { color: #32d74b; text-align: center; text-transform: uppercase; }
        .path { color: #888; font-size: 0.8em; text-align: center; margin-bottom: 20px; word-break: break-all; }
        
        /* Estilos para Carpetas */
        .folder-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 10px; margin-bottom: 30px; }
        .folder { background: #333; padding: 15px; border-radius: 10px; text-align: center; text-decoration: none; color: white; font-weight: bold; }
        .folder:hover { background: #444; }
        .folder-icon { font-size: 2em; display: block; margin-bottom: 5px; }

        /* Estilos para Videos */
        .video-card { background: #1c1c1e; padding: 15px; margin-bottom: 10px; border-radius: 8px; border: 1px solid #333; display: flex; justify-content: space-between; align-items: center; }
        .btn { background: #32d74b; color: #000; border: none; padding: 10px 20px; border-radius: 6px; font-weight: bold; cursor: pointer; }
        
        .alert { background: #333; padding: 10px; border-left: 4px solid #32d74b; margin-bottom: 20px; }
        
        /* Etiquetas de tipo */
        .tag { font-size: 0.7em; padding: 2px 6px; border-radius: 4px; margin-left: 5px; }
        .tag-mp4 { background: #2979ff; }
        .tag-mov { background: #ff9100; color: black; }
    </style>
</head>
<body>
    <h1>🎬 Compresor de Video</h1>
    <div class="path">📂 {{ current_path }}</div>

    {% if message %}
    <div class="alert">{{ message }}</div>
    {% endif %}

    <!-- SECCIÓN DE CARPETAS -->
    {% if folders %}
    <h3>Carpetas:</h3>
    <div class="folder-list">
        {% for folder in folders %}
        <a href="/browse?path={{ current_path }}/{{ folder }}" class="folder">
            <span class="folder-icon">📁</span>
            {{ folder }}
        </a>
        {% endfor %}
    </div>
    {% endif %}

    <!-- SECCIÓN DE VIDEOS -->
    {% if files %}
    <h3>Videos (MP4/MOV):</h3>
    {% for file in files %}
    <div class="video-card">
        <div>
            <strong>{{ file.name }}</strong>
            {% if file.name.endswith('.mp4') or file.name.endswith('.MP4') %}
                <span class="tag tag-mp4">MP4</span>
            {% else %}
                <span class="tag tag-mov">MOV</span>
            {% endif %}
            <br>
            <small style="color:#888">{{ file.size }} MB</small>
        </div>
        <form action="/convert" method="post">
            <input type="hidden" name="filepath" value="{{ current_path }}/{{ file.name }}">
            <input type="hidden" name="return_path" value="{{ current_path }}">
            <button type="submit" class="btn">⚡ COMPRIMIR</button>
        </form>
    </div>
    {% endfor %}
    {% endif %}

    {% if not folders and not files %}
    <p style="text-align:center; color:#666; margin-top:50px;">
        Carpeta vacía o sin videos compatibles.<br>
        <a href="/" style="color:#32d74b">Volver al inicio (DCIM)</a>
    </p>
    {% endif %}
    
    {% if current_path != base_dir %}
    <br>
    <a href="/" style="display:block; text-align:center; color:#888; text-decoration:none;">⬅ Volver a DCIM</a>
    {% endif %}
</body>
</html>
"""

def scan_media(filepath):
    try: subprocess.run(['termux-media-scan', filepath], check=False)
    except: pass

def run_ffmpeg(input_path, output_path):
    cmd = [
        'ffmpeg', '-y', '-i', input_path,
        '-c:v', 'libx265',      # Codec H.265 (Alta compresión)
        '-preset', 'medium',    # Balance velocidad/compresión
        '-crf', '23',           # Factor de calidad (23 es estándar para redes, 28 es más ligero)
        '-vf', 'format=yuv420p',# Formato compatible con redes sociales
        '-c:a', 'aac',          # Audio AAC compatible
        '-b:a', '192k',         # Bitrate audio estándar
        output_path
    ]
    subprocess.run(cmd)
    scan_media(output_path)

@app.route('/')
def home():
    return browse(BASE_DIR)

@app.route('/browse')
def browse(path_arg=None):
    target_path = request.args.get('path', BASE_DIR)
    
    # Seguridad básica
    if not target_path.startswith(BASE_DIR): target_path = BASE_DIR

    folders = []
    files = []
    
    try:
        items = os.listdir(target_path)
        items.sort()
        for item in items:
            full_path = os.path.join(target_path, item)
            # Detección de carpetas
            if os.path.isdir(full_path):
                folders.append(item)
            # Detección de videos (MP4 y MOV)
            elif item.lower().endswith(('.mp4', '.mov')):
                # Ignorar los archivos que ya convertimos nosotros (terminan en _social.mp4)
                if not item.endswith('_social.mp4'):
                    size = round(os.path.getsize(full_path) / (1024*1024), 1)
                    files.append({'name': item, 'size': size})
    except Exception as e:
        return f"Error: {e} <br><a href='/'>Volver</a>"

    return render_template_string(HTML_TEMPLATE, folders=folders, files=files, current_path=target_path, base_dir=BASE_DIR, message=request.args.get('msg'))

@app.route('/convert', methods=['POST'])
def convert():
    filepath = request.form.get('filepath')
    return_path = request.form.get('return_path')
    
    if not filepath: return redirect(url_for('home'))

    # El nuevo archivo se llamará video_social.mp4
    out_path = os.path.splitext(filepath)[0] + "_social.mp4"
    threading.Thread(target=run_ffmpeg, args=(filepath, out_path)).start()
    
    return redirect(url_for('browse', path=return_path, msg=f"⏳ Comprimiendo video para Redes..."))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
