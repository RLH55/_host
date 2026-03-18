import os
import json
import re
import subprocess
import psutil
import socket
import sys
import hashlib
import secrets
import time
import threading
import requests as req_lib
from datetime import datetime, timedelta
from flask import Flask, send_from_directory, request, jsonify, session, redirect, url_for, make_response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "USERS")
os.makedirs(USERS_DIR, exist_ok=True)

app = Flask(__name__, static_folder=BASE_DIR)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# مخزن العمليات (Processes)
running_procs = {}
USERS_FILE = os.path.join(BASE_DIR, "users.json")
REMEMBER_TOKENS_FILE = os.path.join(BASE_DIR, "remember_tokens.json")

# الحساب الرئيسي (المسؤول)
ADMIN_USERNAME = "OMAR_ADMIN"
ADMIN_PASSWORD = "OMAR_2026_BRO"

# ============== Helper Functions ==============

def init_users_db():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            admin_data = {
                ADMIN_USERNAME: {
                    "password": hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest(),
                    "created_at": datetime.now().isoformat(),
                    "last_login": None,
                    "theme": "premium",
                    "is_admin": True,
                    "can_create_users": True
                }
            }
            json.dump(admin_data, f, indent=2)
    else:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
        if ADMIN_USERNAME not in users:
            users[ADMIN_USERNAME] = {
                "password": hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest(),
                "created_at": datetime.now().isoformat(),
                "last_login": None,
                "theme": "premium",
                "is_admin": True,
                "can_create_users": True
            }
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(users, f, indent=2)

def init_tokens_db():
    if not os.path.exists(REMEMBER_TOKENS_FILE):
        with open(REMEMBER_TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

def get_user_servers_dir(username):
    path = os.path.join(USERS_DIR, username, "SERVERS")
    os.makedirs(path, exist_ok=True)
    return path

# --- نظام التشغيل التلقائي (Auto-Restart) ---
def monitor_servers():
    """مراقبة السيرفرات وإعادة تشغيلها إذا توقفت فجأة"""
    while True:
        for username in list(running_procs.keys()):
            for server_folder in list(running_procs[username].keys()):
                proc_info = running_procs[username][server_folder]
                # إذا كان السيرفر مفترض أنه يعمل ولكن العملية توقفت
                if proc_info.get('status') == 'running':
                    proc = proc_info.get('proc')
                    if proc is None or proc.poll() is not None:
                        print(f"⚠️ [Auto-Restart] Server {server_folder} for user {username} stopped. Restarting...")
                        # إعادة التشغيل التلقائي
                        try:
                            startup_file = proc_info.get('startup_file')
                            if startup_file:
                                server_path = os.path.join(get_user_servers_dir(username), server_folder)
                                if startup_file.endswith('.py'):
                                    cmd = [sys.executable, startup_file]
                                elif startup_file.endswith('.js'):
                                    cmd = ["node", startup_file]
                                else:
                                    continue
                                
                                log_file = open(os.path.join(server_path, "server.log"), "a", encoding="utf-8")
                                new_proc = subprocess.Popen(cmd, cwd=server_path, stdout=log_file, stderr=subprocess.STDOUT)
                                proc_info['proc'] = new_proc
                                proc_info['start_time'] = datetime.now().isoformat()
                        except Exception as e:
                            print(f"❌ Failed to auto-restart {server_folder}: {e}")
        time.sleep(15)

# بدء خيط المراقبة
threading.Thread(target=monitor_servers, daemon=True).start()

# --- سكريبت Keep-Alive لمنع توقف الموقع ---
def keep_alive_ping():
    """إرسال طلب لنفس الموقع لمنع وضع النوم في Render"""
    url = os.environ.get('RENDER_EXTERNAL_URL')
    while True:
        if url:
            try:
                req_lib.get(f"{url}/health", timeout=10)
                print(f"✅ [Keep-Alive] Pinged {url}")
            except:
                pass
        time.sleep(600) # كل 10 دقائق

threading.Thread(target=keep_alive_ping, daemon=True).start()

# --- نظام البروكسي (Proxy System) ---
@app.route("/proxy/<port>/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def proxy(port, path):
    try:
        port = int(port)
        if port < 1024 or port > 65535:
            return jsonify({"error": "Invalid port"}), 400
        
        query_string = request.query_string.decode('utf-8')
        url = f"http://localhost:{port}/{path}"
        if query_string:
            url += f"?{query_string}"
        
        headers = {key: value for key, value in request.headers if key.lower() != 'host'}
        
        method = request.method
        data = request.get_data()
        
        resp = req_lib.request(method, url, headers=headers, data=data, timeout=30)
        
        response = make_response(resp.content)
        response.status_code = resp.status_code
        for key, value in resp.headers.items():
            if key.lower() not in ['content-encoding', 'content-length', 'transfer-encoding', 'connection']:
                response.headers[key] = value
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============== Routes ==============

@app.route("/")
def home():
    if 'username' not in session:
        return redirect(url_for('login_page'))
    
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
    
    if users.get(session['username'], {}).get('is_admin'):
        return send_from_directory(BASE_DIR, "admin_panel.html")
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/login", methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        init_users_db()
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
            
        if username in users and users[username]['password'] == hashlib.sha256(password.encode()).hexdigest():
            session['username'] = username
            session.permanent = True
            return jsonify({"status": "success", "is_admin": users[username].get('is_admin', False)})
        return jsonify({"status": "error", "message": "بيانات الدخول غير صحيحة"}), 401
    
    return send_from_directory(BASE_DIR, "login.html")

@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

@app.route("/api/logout", methods=['POST'])
def logout():
    session.pop('username', None)
    return jsonify({"status": "success"})

# إضافة باقي الـ APIs المطلوبة لإدارة السيرفرات والمستخدمين (مختصرة للسرعة)
@app.route("/api/admin/create_user", methods=['POST'])
def admin_create_user():
    if 'username' not in session: return jsonify({"error": "Unauthorized"}), 401
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
    if not users.get(session['username'], {}).get('is_admin'):
        return jsonify({"error": "Forbidden"}), 403
        
    data = request.json
    new_user = data.get('username')
    new_pass = data.get('password')
    
    if new_user in users:
        return jsonify({"error": "المستخدم موجود"}), 400
        
    users[new_user] = {
        "password": hashlib.sha256(new_pass.encode()).hexdigest(),
        "created_at": datetime.now().isoformat(),
        "is_admin": False
    }
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)
    
    os.makedirs(os.path.join(USERS_DIR, new_user, "SERVERS"), exist_ok=True)
    return jsonify({"status": "success"})

@app.route("/api/servers/list")
def list_servers():
    if 'username' not in session: return jsonify([])
    user_servers_dir = get_user_servers_dir(session['username'])
    servers = []
    for folder in os.listdir(user_servers_dir):
        if os.path.isdir(os.path.join(user_servers_dir, folder)):
            status = "offline"
            if session['username'] in running_procs and folder in running_procs[session['username']]:
                status = running_procs[session['username']][folder]['status']
            servers.append({"name": folder, "status": status})
    return jsonify(servers)

@app.route("/api/servers/create", methods=['POST'])
def api_create_server():
    if 'username' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    name = re.sub(r"[^A-Za-z0-9\-\_]", "", data.get('name', ''))
    if not name: return jsonify({"error": "اسم غير صالح"}), 400
    
    path = os.path.join(get_user_servers_dir(session['username']), name)
    if os.path.exists(path): return jsonify({"error": "موجود بالفعل"}), 400
    
    os.makedirs(path)
    with open(os.path.join(path, "meta.json"), "w") as f:
        json.dump({"display_name": name, "startup_file": ""}, f)
    return jsonify({"status": "success"})

@app.route("/api/servers/action", methods=['POST'])
def api_server_action():
    if 'username' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    name = data.get('name')
    action = data.get('action')
    username = session['username']
    
    server_path = os.path.join(get_user_servers_dir(username), name)
    
    if action == 'start':
        startup_file = None
        for f in os.listdir(server_path):
            if f in ['app.py', 'main.py', 'bot.py', 'index.js', 'server.js']:
                startup_file = f
                break
        
        if not startup_file: return jsonify({"error": "لم يتم العثور على ملف تشغيل"}), 400
        
        if username not in running_procs: running_procs[username] = {}
        
        cmd = [sys.executable, startup_file] if startup_file.endswith('.py') else ["node", startup_file]
        log_file = open(os.path.join(server_path, "server.log"), "a", encoding="utf-8")
        proc = subprocess.Popen(cmd, cwd=server_path, stdout=log_file, stderr=subprocess.STDOUT)
        
        running_procs[username][name] = {
            "proc": proc,
            "status": "running",
            "startup_file": startup_file,
            "start_time": datetime.now().isoformat()
        }
        return jsonify({"status": "success"})
        
    elif action == 'stop':
        if username in running_procs and name in running_procs[username]:
            proc_info = running_procs[username][name]
            proc_info['status'] = 'offline' # تعيينها يدوياً لمنع إعادة التشغيل
            try:
                proc_info['proc'].terminate()
            except: pass
            del running_procs[username][name]
            return jsonify({"status": "success"})
            
    return jsonify({"error": "Unknown action"}), 400

if __name__ == "__main__":
    init_users_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
