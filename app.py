import os
import subprocess
import threading
import re
import time
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# --- CONFIGURACIÓN ---
BASE_DIR = '/storage/emulated/0/DCIM'
PORT = 8080

# --- ESTADO GLOBAL ---
conversion_status = {
    'converting': False,
    'filename': '',
    'percent': 0
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Compresor Pro</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #000; color: #fff; padding: 20px; margin: 0; }
        h1 { color: #32d74b; text-align: center; margin-bottom: 20px; }
        .path { color: #666; font-size: 0.8em; text-align: center; margin-bottom: 20px; word-break: break-all; }
        
        .item { background: #1c1c1e; padding: 15px; margin-bottom: 10px; border-radius: 10px; display: flex; align-items: center; justify-content: space-between; border: 1px solid #333; }
        .btn { border: none; padding: 10px 15px; border-radius: 8px; font-weight: bold; cursor: pointer; text-decoration: none; }
        .btn-folder { background: #333; color: #fff; }
        .btn-action { background: #32d74b; color: #000; }
        .btn-done { background: #1b5e20; color: #a5d6a7; border: 1px solid #2e7d32; }
        
        .badge { font-size: 0.7em; padding: 2px 6px; border-radius: 4px; margin-left: 5px; vertical-align: middle; }
        .badge-ok { background: #4caf50; color: #000; font-weight:bold; }

        /* PANTALLA PROGRESO */
        #overlay {
            display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.95); z-index: 9999;
            flex-direction: column; justify-content: center; align-items: center; text-align: center;
        }
        .progress-text { font-size: 4rem; font-weight: bold; color: #32d74b; }
        .progress-info { color: #fff; margin-top: 20px; font-size: 1.2rem; }
    </style>
</head>
<body>
    <h1>🎬 Compresor</h1>
    <div class="path">📂 {{ current_path }}</div>

    <div id="overlay">
        <div class="progress-text" id="prog-percent">0%</div>
        <div class="progress-info" id="prog-name">Iniciando...</div>
        <div style="color:#666; margin-top:30px;">⚠️ No cierres esta pestaña</div>
    </div>

    <!-- CARPETAS -->
    {% for folder in folders %}
    <div class="item">
        <span>📁 {{ folder }}</span>
        <a href="/browse?path={{ current_path }}/{{ folder }}" class="btn btn-folder">ABRIR</a>
    </div>
    {% endfor %}

    <!-- VIDEOS -->
    {% for file in files %}
    <div class="item">
        <div>
            <strong>{{ file.name }}</strong>
            {% if file.is_done %}
                <span class="badge badge-ok">✅ LISTO</span>
            {% endif %}
            <br>
            <small style="color:#888">{{ file.size }} MB</small>
        </div>
        
        {% if file.is_done %}
            <button class="btn btn-done" onclick="startConvert('{{ current_path }}/{{ file.name }}')">RE-HACER</button>
        {% else %}
            <button class="btn btn-action" onclick="startConvert('{{ current_path }}/{{ file.name }}')">COMPRIMIR</button>
        {% endif %}
    </div>
    {% endfor %}

    {% if current_path != base_dir %}
    <br><a href="/" style="display:block; text-align:center; color:#888; text-decoration:none;">⬅ Volver al Inicio</a>
    {% endif %}

    <script>
        function startConvert(path) {
            if(!confirm('¿Comprimir video?')) return;
            document.getElementById('overlay').style.display = 'flex';
            
            fetch('/convert', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'filepath=' + encodeURIComponent(path)
            });
            checkStatus();
        }

        function checkStatus() {
            const interval = setInterval(() => {
                fetch('/status').then(r => r.json()).then(data => {
                    if (data.converting) {
                        document.getElementById('prog-percent').innerText = data.percent + "%";
                        document.getElementById('prog-name').innerText = data.filename;
                    } else {
                        clearInterval(interval);
                        alert('✅ ¡Listo!');
                        location.reload();
                    }
                }).catch(e => console.error(e));
            }, 1000);
        }
    </script>
</body>
</html>
"""

def parse_time(time_str):
    try:
        h, m, s = time_str.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    except: return 0

def run_ffmpeg_progress(input_path, output_path, filename):
    global conversion_status
    conversion_status['converting'] = True
    conversion_status['filename'] = filename
    conversion_status['percent'] = 0

    cmd = [
        'ffmpeg', '-y', '-i', input_path,
        '-c:v', 'libx265', '-preset', 'ultrafast', '-crf', '24',
        '-vf', 'format=yuv420p', '-c:a', 'aac', '-b:a', '128k',
        output_path
    ]

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    
    duration = 0
    for line in process.stdout:
        if 'Duration:' in line and duration == 0:
            match = re.search(r'Duration: (\d{2}:\d{2}:\d{2}\.\d{2})', line)
            if match: duration = parse_time(match.group(1))
        
        if 'time=' in line and duration > 0:
            match = re.search(r'time=(\d{2}:\d{2}:\d{2}\.\d{2})', line)
            if match:
                current_time = parse_time(match.group(1))
                conversion_status['percent'] = int((current_time / duration) * 100)
    
    process.wait()
    try: subprocess.run(['termux-media-scan', output_path], check=False)
    except: pass
    
    conversion_status['converting'] = False
    conversion_status['percent'] = 100

@app.route('/')
def home(): return browse(BASE_DIR)

@app.route('/browse')
def browse():
    path = request.args.get('path', BASE_DIR)
    if not path.startswith(BASE_DIR): path = BASE_DIR
    
    folders, files = [], []
    try:
        # Primero escaneamos qué archivos YA existen (los que terminan en _social.mp4)
        all_items = os.listdir(path)
        existing_socials = {f for f in all_items if f.endswith('_social.mp4')}

        for item in sorted(all_items):
            full = os.path.join(path, item)
            if os.path.isdir(full): 
                folders.append(item)
            # Solo mostramos los originales (MP4/MOV) que NO son los comprimidos
            elif item.lower().endswith(('.mp4', '.mov')) and not item.endswith('_social.mp4'):
                # Verificamos si este original ya tiene su pareja
                social_name = os.path.splitext(item)[0] + "_social.mp4"
                is_done = social_name in existing_socials
                
                files.append({
                    'name': item, 
                    'size': round(os.path.getsize(full)/1048576, 1),
                    'is_done': is_done
                })
    except: pass
    return render_template_string(HTML_TEMPLATE, folders=folders, files=files, current_path=path, base_dir=BASE_DIR)

@app.route('/convert', methods=['POST'])
def convert():
    if conversion_status['converting']: return "Busy", 400
    filepath = request.form.get('filepath')
    threading.Thread(target=run_ffmpeg_progress, args=(filepath, os.path.splitext(filepath)[0] + "_social.mp4", os.path.basename(filepath))).start()
    return "OK"

@app.route('/status')
def status(): return jsonify(conversion_status)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
