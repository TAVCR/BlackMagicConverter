import os
import subprocess
import threading
from flask import Flask, render_template_string, request, redirect, url_for

app = Flask(__name__)

# --- CORRECCIÓN IMPORTANTE AQUÍ ABAJO ---
# Ruta exacta basada en lo que me dijiste:
VIDEO_DIR = '/storage/emulated/0/DCIM/Blackmagic Camera'
PORT = 8080

# --- INTERFAZ GRÁFICA ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Blackmagic Converter</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #000; color: #fff; padding: 20px; text-align: center; }
        h1 { color: #32d74b; margin-bottom: 20px; text-transform: uppercase; letter-spacing: 1px; }
        .folder-name { color: #666; font-size: 0.8em; margin-bottom: 20px; word-break: break-all; }
        .card { background: #1c1c1e; padding: 15px; margin-bottom: 15px; border-radius: 12px; border: 1px solid #333; text-align: left; }
        .filename { font-weight: bold; font-size: 1.1em; color: #fff; word-break: break-all; margin-bottom: 5px; }
        .meta { color: #888; font-size: 0.9em; margin-bottom: 15px; }
        .btn { width: 100%; padding: 15px; background: #32d74b; color: #000; border: none; border-radius: 8px; font-weight: bold; font-size: 16px; cursor: pointer; transition: 0.2s; }
        .status-box { background: #333; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #32d74b; }
        .refresh { display: inline-block; margin-top: 30px; color: #32d74b; text-decoration: none; border: 1px solid #32d74b; padding: 8px 16px; border-radius: 20px; }
    </style>
</head>
<body>
    <h1>🎬 Blackmagic Tools</h1>
    <div class="folder-name">📂 {{ folder }}</div>
    
    {% if message %}
    <div class="status-box">{{ message }}</div>
    {% endif %}

    {% for file in files %}
    <div class="card">
        <div class="filename">{{ file.name }}</div>
        <div class="meta">{{ file.size }} MB</div>
        <form action="/convert" method="post">
            <input type="hidden" name="filename" value="{{ file.name }}">
            <button type="submit" class="btn">⚡ Convertir a H.265</button>
        </form>
    </div>
    {% endfor %}
    
    {% if not files %}
    <div style="padding: 40px; color: #666;">
        No se encontraron archivos .mov
        <br><br>
        <small>Buscando en: {{ folder }}</small>
    </div>
    {% endif %}

    <a href="/" class="refresh">🔄 Actualizar Lista</a>
</body>
</html>
"""

def scan_media(filepath):
    try: subprocess.run(['termux-media-scan', filepath], check=False)
    except: pass

def run_ffmpeg(input_path, output_path):
    cmd = [
        'ffmpeg', '-y', '-i', input_path,
        '-c:v', 'libx265', '-preset', 'slow', '-crf', '20',
        '-vf', 'format=yuv420p10le', '-c:a', 'aac', '-b:a', '320k',
        output_path
    ]
    subprocess.run(cmd)
    scan_media(output_path)

@app.route('/')
def index():
    files_data = []
    if os.path.exists(VIDEO_DIR):
        try:
            raw_files = [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith('.mov')]
            raw_files.sort(key=lambda x: os.path.getmtime(os.path.join(VIDEO_DIR, x)), reverse=True)
            for f in raw_files:
                path = os.path.join(VIDEO_DIR, f)
                size_mb = round(os.path.getsize(path) / (1024 * 1024), 1)
                files_data.append({'name': f, 'size': size_mb})
        except: pass
    return render_template_string(HTML_TEMPLATE, files=files_data, folder=VIDEO_DIR, message=request.args.get('msg'))

@app.route('/convert', methods=['POST'])
def convert():
    filename = request.form.get('filename')
    if not filename: return redirect(url_for('index'))
    in_path = os.path.join(VIDEO_DIR, filename)
    out_path = os.path.join(VIDEO_DIR, os.path.splitext(filename)[0] + "_h265.mp4")
    threading.Thread(target=run_ffmpeg, args=(in_path, out_path)).start()
    return redirect(url_for('index', msg=f"⏳ Procesando {filename}..."))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
