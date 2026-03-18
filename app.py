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
import shutil
from datetime import datetime, timedelta
from flask import Flask, send_from_directory, request, jsonify, session, redirect, url_for, make_response
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "USERS")
os.makedirs(USERS_DIR, exist_ok=True)

app = Flask(__name__, static_folder=BASE_DIR)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

running_procs = {}
USERS_FILE = os.path.join(BASE_DIR, "users.json")
REMEMBER_TOKENS_FILE = os.path.join(BASE_DIR, "remember_tokens.json")

ADMIN_USERNAME = "BRO1983"
ADMIN_PASSWORD = "OMAROMAR19830"

# ============== Helper Functions ==============

def init_users_db():
    """تهيئة قاعدة بيانات المستخدمين"""
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
        # تأكد من وجود حساب الأدمن دائماً
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

def get_server_meta(server_path):
    """قراءة ملف meta.json للسيرفر"""
    meta_file = os.path.join(server_path, "meta.json")
    if os.path.exists(meta_file):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"display_name": "", "startup_file": ""}

def save_server_meta(server_path, meta):
    """حفظ ملف meta.json للسيرفر"""
    meta_file = os.path.join(server_path, "meta.json")
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

def find_startup_file(server_path, preferred=None):
    """إيجاد ملف التشغيل المناسب"""
    # إذا كان هناك ملف محدد مسبقاً
    if preferred and os.path.exists(os.path.join(server_path, preferred)):
        return preferred
    
    # البحث بالأولوية
    priority_files = ['main.py', 'app.py', 'bot.py', 'index.py', 'run.py',
                      'index.js', 'server.js', 'app.js', 'main.js', 'bot.js']
    
    for f in priority_files:
        if os.path.exists(os.path.join(server_path, f)):
            return f
    
    # البحث عن أي ملف .py أو .js
    for f in os.listdir(server_path):
        if f.endswith('.py') or f.endswith('.js'):
            if f != 'meta.json':
                return f
    
    return None

# ============== نظام Auto-Restart ==============

def monitor_servers():
    """مراقبة السيرفرات وإعادة تشغيلها تلقائياً إذا توقفت"""
    while True:
        try:
            for username in list(running_procs.keys()):
                for server_folder in list(running_procs.get(username, {}).keys()):
                    proc_info = running_procs[username].get(server_folder, {})
                    if proc_info.get('status') == 'running':
                        proc = proc_info.get('proc')
                        if proc is None or proc.poll() is not None:
                            print(f"⚠️ [Auto-Restart] السيرفر {server_folder} للمستخدم {username} توقف. جاري إعادة التشغيل...")
                            try:
                                startup_file = proc_info.get('startup_file')
                                if startup_file:
                                    server_path = os.path.join(get_user_servers_dir(username), server_folder)
                                    if startup_file.endswith('.py'):
                                        cmd = [sys.executable, startup_file]
                                    elif startup_file.endswith('.js'):
                                        cmd = ['node', startup_file]
                                    else:
                                        continue

                                    log_path = os.path.join(server_path, "server.log")
                                    log_file = open(log_path, "a", encoding="utf-8")
                                    log_file.write(f"\n[{datetime.now().isoformat()}] ⚠️ Auto-Restart triggered\n")
                                    log_file.flush()

                                    new_proc = subprocess.Popen(
                                        cmd, cwd=server_path,
                                        stdout=log_file, stderr=subprocess.STDOUT
                                    )
                                    proc_info['proc'] = new_proc
                                    proc_info['start_time'] = datetime.now().isoformat()
                                    proc_info['restart_count'] = proc_info.get('restart_count', 0) + 1
                                    print(f"✅ [Auto-Restart] تم إعادة تشغيل {server_folder} (مرة {proc_info['restart_count']})")
                            except Exception as e:
                                print(f"❌ [Auto-Restart] فشل إعادة تشغيل {server_folder}: {e}")
        except Exception as e:
            print(f"❌ [Monitor] خطأ في المراقبة: {e}")
        time.sleep(15)

threading.Thread(target=monitor_servers, daemon=True).start()

# ============== سكريبت Keep-Alive ==============

def keep_alive_ping():
    """إرسال طلبات دورية لمنع وضع النوم في Render"""
    # انتظر قليلاً حتى يبدأ السيرفر
    time.sleep(30)
    
    url = os.environ.get('RENDER_EXTERNAL_URL', '')
    
    # محاولة اكتشاف الرابط تلقائياً
    if not url:
        port = int(os.environ.get('PORT', 10000))
        url = f"http://localhost:{port}"
    
    ping_count = 0
    while True:
        try:
            response = req_lib.get(f"{url}/health", timeout=15)
            ping_count += 1
            if ping_count % 10 == 0:  # طباعة كل 10 طلبات
                print(f"✅ [Keep-Alive] Ping #{ping_count} - Status: {response.status_code}")
        except Exception as e:
            print(f"⚠️ [Keep-Alive] فشل الطلب: {e}")
        
        # كل 5 دقائق (300 ثانية) - أقل من حد Render البالغ 15 دقيقة
        time.sleep(300)

threading.Thread(target=keep_alive_ping, daemon=True).start()

# ============== نظام البروكسي ==============

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
        username = data.get('username', '').strip()
        password = data.get('password', '')

        init_users_db()
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)

        if username in users and users[username]['password'] == hashlib.sha256(password.encode()).hexdigest():
            session['username'] = username
            session.permanent = True
            # تحديث آخر تسجيل دخول
            users[username]['last_login'] = datetime.now().isoformat()
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(users, f, indent=2)
            return jsonify({"status": "success", "is_admin": users[username].get('is_admin', False)})
        return jsonify({"status": "error", "message": "❌ بيانات الدخول غير صحيحة"}), 401

    return send_from_directory(BASE_DIR, "login.html")

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "time": datetime.now().isoformat(),
        "uptime": "running",
        "servers_running": sum(
            1 for u in running_procs.values()
            for s in u.values()
            if s.get('status') == 'running'
        )
    })

@app.route("/avatar.png")
def serve_avatar():
    return send_from_directory(BASE_DIR, "avatar.png")

@app.route("/api/logout", methods=['POST'])
def logout():
    session.pop('username', None)
    return jsonify({"status": "success"})

# ============== Admin APIs ==============

@app.route("/api/admin/users", methods=['GET'])
def admin_get_users():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
    if not users.get(session['username'], {}).get('is_admin'):
        return jsonify({"error": "Forbidden"}), 403
    return jsonify(users)

@app.route("/api/admin/create_user", methods=['POST'])
def admin_create_user():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
    if not users.get(session['username'], {}).get('is_admin'):
        return jsonify({"error": "Forbidden"}), 403

    data = request.json
    new_user = data.get('username', '').strip()
    new_pass = data.get('password', '')

    if not new_user or not new_pass:
        return jsonify({"error": "البيانات غير مكتملة"}), 400

    if new_user in users:
        return jsonify({"error": "المستخدم موجود بالفعل"}), 400

    users[new_user] = {
        "password": hashlib.sha256(new_pass.encode()).hexdigest(),
        "created_at": datetime.now().isoformat(),
        "last_login": None,
        "is_admin": False
    }
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)

    os.makedirs(os.path.join(USERS_DIR, new_user, "SERVERS"), exist_ok=True)
    return jsonify({"status": "success"})

@app.route("/api/admin/delete_user", methods=['POST'])
def admin_delete_user():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
    if not users.get(session['username'], {}).get('is_admin'):
        return jsonify({"error": "Forbidden"}), 403

    data = request.json
    user_to_delete = data.get('username')

    if user_to_delete == ADMIN_USERNAME:
        return jsonify({"error": "لا يمكن حذف حساب المسؤول"}), 400
    if user_to_delete not in users:
        return jsonify({"error": "المستخدم غير موجود"}), 404

    del users[user_to_delete]
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)

    user_dir = os.path.join(USERS_DIR, user_to_delete)
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir)

    return jsonify({"status": "success"})

# ============== Servers APIs ==============

@app.route("/api/servers/list")
def list_servers():
    if 'username' not in session:
        return jsonify([])
    user_servers_dir = get_user_servers_dir(session['username'])
    servers = []
    for folder in os.listdir(user_servers_dir):
        folder_path = os.path.join(user_servers_dir, folder)
        if os.path.isdir(folder_path):
            status = "offline"
            startup_file = None

            # قراءة meta.json
            meta = get_server_meta(folder_path)
            startup_file = meta.get('startup_file') or find_startup_file(folder_path)

            if session['username'] in running_procs and folder in running_procs[session['username']]:
                proc_info = running_procs[session['username']][folder]
                status = proc_info.get('status', 'offline')
                # تحقق من أن العملية لا تزال تعمل
                proc = proc_info.get('proc')
                if proc and proc.poll() is not None:
                    status = 'offline'
                    proc_info['status'] = 'offline'

            servers.append({
                "name": folder,
                "status": status,
                "startup_file": startup_file
            })
    return jsonify(servers)

@app.route("/api/servers/create", methods=['POST'])
def api_create_server():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    name = re.sub(r"[^A-Za-z0-9\-\_]", "", data.get('name', ''))
    if not name:
        return jsonify({"error": "اسم غير صالح"}), 400

    path = os.path.join(get_user_servers_dir(session['username']), name)
    if os.path.exists(path):
        return jsonify({"error": "السيرفر موجود بالفعل"}), 400

    os.makedirs(path)
    save_server_meta(path, {"display_name": name, "startup_file": ""})
    return jsonify({"status": "success"})

@app.route("/api/servers/delete", methods=['POST'])
def api_delete_server():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    name = data.get('name')

    server_path = os.path.join(get_user_servers_dir(session['username']), name)
    if not os.path.exists(server_path):
        return jsonify({"error": "السيرفر غير موجود"}), 404

    username = session['username']
    if username in running_procs and name in running_procs[username]:
        try:
            running_procs[username][name]['proc'].terminate()
        except:
            pass
        del running_procs[username][name]

    shutil.rmtree(server_path)
    return jsonify({"status": "success"})

@app.route("/api/servers/info/<server_name>")
def get_server_info(server_name):
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    server_path = os.path.join(get_user_servers_dir(session['username']), server_name)
    if not os.path.exists(server_path):
        return jsonify({"error": "السيرفر غير موجود"}), 404

    meta = get_server_meta(server_path)
    startup_file = meta.get('startup_file') or find_startup_file(server_path)

    files = []
    total_size = 0
    for f in os.listdir(server_path):
        file_path = os.path.join(server_path, f)
        if os.path.isfile(file_path) and f != 'meta.json':
            size = os.path.getsize(file_path)
            total_size += size
            files.append({
                "name": f,
                "size": size,
                "modified": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
            })

    status = "offline"
    if session['username'] in running_procs and server_name in running_procs[session['username']]:
        proc_info = running_procs[session['username']][server_name]
        proc = proc_info.get('proc')
        if proc and proc.poll() is None:
            status = proc_info.get('status', 'offline')
        else:
            status = 'offline'

    return jsonify({
        "name": server_name,
        "status": status,
        "startup_file": startup_file,
        "files": files,
        "total_size": total_size,
        "file_count": len(files)
    })

@app.route("/api/servers/set_startup", methods=['POST'])
def set_startup_file():
    """تعيين ملف التشغيل للسيرفر"""
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    name = data.get('name')
    startup_file = data.get('startup_file')

    server_path = os.path.join(get_user_servers_dir(session['username']), name)
    if not os.path.exists(server_path):
        return jsonify({"error": "السيرفر غير موجود"}), 404

    file_path = os.path.join(server_path, startup_file)
    if not os.path.exists(file_path):
        return jsonify({"error": "الملف غير موجود"}), 404

    if not (startup_file.endswith('.py') or startup_file.endswith('.js')):
        return jsonify({"error": "يجب أن يكون الملف .py أو .js"}), 400

    meta = get_server_meta(server_path)
    meta['startup_file'] = startup_file
    save_server_meta(server_path, meta)

    return jsonify({"status": "success", "startup_file": startup_file})

@app.route("/api/servers/upload/<server_name>", methods=['POST'])
def upload_file(server_name):
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    server_path = os.path.join(get_user_servers_dir(session['username']), server_name)
    if not os.path.exists(server_path):
        return jsonify({"error": "السيرفر غير موجود"}), 404

    if 'file' not in request.files:
        return jsonify({"error": "لا يوجد ملف"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "لم يتم اختيار ملف"}), 400

    filename = secure_filename(file.filename)
    file.save(os.path.join(server_path, filename))

    # إذا كان أول ملف .py أو .js، عيّنه تلقائياً كملف تشغيل
    meta = get_server_meta(server_path)
    if not meta.get('startup_file') and (filename.endswith('.py') or filename.endswith('.js')):
        meta['startup_file'] = filename
        save_server_meta(server_path, meta)

    return jsonify({"status": "success", "filename": filename})

@app.route("/api/servers/delete_file/<server_name>/<filename>", methods=['POST'])
def delete_file(server_name, filename):
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    server_path = os.path.join(get_user_servers_dir(session['username']), server_name)
    file_path = os.path.join(server_path, secure_filename(filename))

    if not os.path.exists(file_path):
        return jsonify({"error": "الملف غير موجود"}), 404

    os.remove(file_path)

    # إذا كان ملف التشغيل المحذوف هو المحدد، أزله من meta
    meta = get_server_meta(server_path)
    if meta.get('startup_file') == filename:
        meta['startup_file'] = ''
        save_server_meta(server_path, meta)

    return jsonify({"status": "success"})

@app.route("/api/servers/action", methods=['POST'])
def api_server_action():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    name = data.get('name')
    action = data.get('action')
    username = session['username']

    server_path = os.path.join(get_user_servers_dir(username), name)
    if not os.path.exists(server_path):
        return jsonify({"error": "السيرفر غير موجود"}), 404

    if action == 'start':
        # إيجاد ملف التشغيل
        meta = get_server_meta(server_path)
        startup_file = meta.get('startup_file') or find_startup_file(server_path)

        if not startup_file:
            return jsonify({
                "error": "لم يتم العثور على ملف تشغيل. ارفع ملف .py أو .js أولاً، ثم اضغط 'تعيين تشغيل'."
            }), 400

        full_path = os.path.join(server_path, startup_file)
        if not os.path.exists(full_path):
            return jsonify({"error": f"ملف التشغيل '{startup_file}' غير موجود"}), 400

        # إيقاف أي عملية سابقة
        if username in running_procs and name in running_procs[username]:
            try:
                running_procs[username][name]['proc'].terminate()
                time.sleep(0.5)
            except:
                pass

        if username not in running_procs:
            running_procs[username] = {}

        if startup_file.endswith('.py'):
            cmd = [sys.executable, startup_file]
        elif startup_file.endswith('.js'):
            cmd = ['node', startup_file]
        else:
            return jsonify({"error": "نوع الملف غير مدعوم"}), 400

        log_path = os.path.join(server_path, "server.log")
        log_file = open(log_path, "a", encoding="utf-8")
        log_file.write(f"\n[{datetime.now().isoformat()}] 🚀 Server started: {startup_file}\n")
        log_file.flush()

        try:
            proc = subprocess.Popen(
                cmd, cwd=server_path,
                stdout=log_file, stderr=subprocess.STDOUT
            )

            running_procs[username][name] = {
                "proc": proc,
                "status": "running",
                "startup_file": startup_file,
                "start_time": datetime.now().isoformat(),
                "restart_count": 0
            }

            # حفظ ملف التشغيل في meta
            meta['startup_file'] = startup_file
            save_server_meta(server_path, meta)

            return jsonify({"status": "success", "startup_file": startup_file})
        except Exception as e:
            return jsonify({"error": f"فشل التشغيل: {str(e)}"}), 500

    elif action == 'stop':
        if username in running_procs and name in running_procs[username]:
            proc_info = running_procs[username][name]
            proc_info['status'] = 'offline'
            try:
                proc_info['proc'].terminate()
                proc_info['proc'].wait(timeout=5)
            except:
                try:
                    proc_info['proc'].kill()
                except:
                    pass
            del running_procs[username][name]
            return jsonify({"status": "success"})
        return jsonify({"status": "success"})  # لا بأس إذا لم يكن يعمل

    return jsonify({"error": "إجراء غير معروف"}), 400

@app.route("/api/servers/logs/<server_name>")
def get_server_logs(server_name):
    """جلب سجلات السيرفر"""
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    server_path = os.path.join(get_user_servers_dir(session['username']), server_name)
    log_path = os.path.join(server_path, "server.log")

    if not os.path.exists(log_path):
        return jsonify({"logs": "لا توجد سجلات بعد."})

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            # آخر 100 سطر فقط
            lines = f.readlines()
            last_lines = lines[-100:] if len(lines) > 100 else lines
            return jsonify({"logs": "".join(last_lines)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============== تشغيل التطبيق ==============

if __name__ == "__main__":
    init_users_db()
    init_tokens_db()
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 BRO HOST بدأ على المنفذ {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
