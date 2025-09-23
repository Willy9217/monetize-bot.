# MANY - Super Bot de Monetización (revisado)
import os, sqlite3, threading, time, uuid, random, secrets
from datetime import datetime
from flask import Flask, request, redirect, url_for, render_template, flash, session, send_file, jsonify
try:
    from cryptography.fernet import Fernet
except Exception:
    Fernet = None
try:
    import openai
except Exception:
    openai = None

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'many.db')
FERNET_PATH = os.path.join(DATA_DIR, 'fernet.key')

ADMIN_USER = os.environ.get('BOT_ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('BOT_ADMIN_PASS', 'admin123')
AUTO_INTERVAL_HOURS = int(os.environ.get('AUTO_INTERVAL_HOURS', '48'))
DEMO_MODE = os.environ.get('DEMO_MODE', '1') == '1'

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_urlsafe(24))

os.makedirs(DATA_DIR, exist_ok=True)

def load_or_create_fernet():
    if Fernet is None:
        return None
    if os.path.exists(FERNET_PATH):
        with open(FERNET_PATH, 'rb') as f:
            key = f.read().strip()
    else:
        key = Fernet.generate_key()
        with open(FERNET_PATH, 'wb') as f:
            f.write(key)
    return Fernet(key)

fernet = load_or_create_fernet()

def get_db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    db = get_db()
    cur = db.cursor()
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, title TEXT, body TEXT, status TEXT, created_at INTEGER, published_at INTEGER, platform TEXT, est_revenue REAL);
    CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, ts INTEGER, type TEXT, meta TEXT);
    CREATE TABLE IF NOT EXISTS earnings (id TEXT PRIMARY KEY, ts INTEGER, platform TEXT, amount REAL, note TEXT);
    CREATE TABLE IF NOT EXISTS strategies (id TEXT PRIMARY KEY, name TEXT, score REAL, last_run INTEGER);
    ''')
    db.commit()
    cur.execute("SELECT COUNT(*) as c FROM strategies")
    if cur.fetchone()['c'] == 0:
        cur.execute("INSERT INTO strategies (id,name,score,last_run) VALUES (?,?,?,?)", (str(uuid.uuid4()), 'default', 1.0, int(time.time())))
        db.commit()
    db.close()

init_db()

def set_setting(k, v, encrypt=False):
    db = get_db()
    if encrypt and fernet is not None and v is not None:
        v_enc = fernet.encrypt(v.encode()).decode()
    else:
        v_enc = v
    db.execute("REPLACE INTO settings (k,v) VALUES (?,?)", (k, v_enc))
    db.commit()
    db.close()

def get_setting(k, decrypt=False):
    db = get_db()
    cur = db.execute("SELECT v FROM settings WHERE k=?", (k,))
    row = cur.fetchone()
    db.close()
    if not row:
        return None
    v = row['v']
    if decrypt and fernet is not None and v is not None:
        try:
            return fernet.decrypt(v.encode()).decode()
        except Exception:
            return None
    return v

def is_logged_in():
    return session.get('logged_in') == True

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username','')
        p = request.form.get('password','')
        if u == ADMIN_USER and p == ADMIN_PASS:
            session['logged_in'] = True
            return redirect(url_for('status'))
        else:
            flash('Usuario o contraseña inválidos','danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/config', methods=['GET','POST'])
def config():
    if not is_logged_in():
        return redirect(url_for('login'))
    message = None
    if request.method == 'POST':
        platforms = ['amazon_access','amazon_secret','amazon_tag','clickbank_key','clickbank_nick','ebay_key','aliexpress_key','openai_key']
        for p in platforms:
            val = request.form.get(p)
            if val is not None:
                encrypt = p.endswith('_key') or 'secret' in p or 'access' in p
                set_setting(p, val, encrypt=encrypt)
        message = "Configuración guardada."
        ok_openai = get_setting('openai_key', decrypt=True)
        if ok_openai and openai is not None:
            openai.api_key = ok_openai
    current = { 'amazon_tag': get_setting('amazon_tag') or '' , 'demo_mode': 'on' if DEMO_MODE else 'off' }
    return render_template('config.html', message=message, current=current)

@app.route('/status')
def status():
    if not is_logged_in():
        return redirect(url_for('login'))
    db = get_db()
    cur = db.execute("SELECT COUNT(*) as drafts FROM posts WHERE status='draft'")
    drafts = cur.fetchone()['drafts']
    cur = db.execute("SELECT COUNT(*) as pub FROM posts WHERE status='published'")
    pub = cur.fetchone()['pub']
    cur = db.execute("SELECT SUM(amount) as total FROM earnings")
    total = cur.fetchone()['total'] or 0.0
    cur = db.execute("SELECT name,score,last_run FROM strategies ORDER BY last_run DESC LIMIT 5")
    strategies = cur.fetchall()
    db.close()
    return render_template('status.html', drafts=drafts, published=pub, total=total, strategies=strategies, demo=DEMO_MODE)

def generate_text_for_topic(topic):
    ok_openai = get_setting('openai_key', decrypt=True) or None
    if ok_openai and openai is not None:
        try:
            openai.api_key = ok_openai
            resp = openai.ChatCompletion.create(model='gpt-3.5-turbo', messages=[{'role':'user','content':f'Escribe un artículo comercial sobre: {topic}'}], max_tokens=700)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print('OpenAI error', e)
    return f"<p>Contenido de ejemplo para: <strong>{topic}</strong></p><p>Compra aquí: https://www.amazon.com/dp/EXAMPLE?tag={get_setting('amazon_tag') or 'demo-tag'}</p>"

def publish_to_platforms(post_id, title, body):
    published_platforms = []
    if os.environ.get('DEMO_MODE','1') == '1':
        published_platforms = ['demo-web','demo-telegram']
    else:
        if get_setting('ebay_key', decrypt=True):
            published_platforms.append('ebay')
        if get_setting('clickbank_key', decrypt=True):
            published_platforms.append('clickbank-listing')
    db = get_db()
    est = random.uniform(0.5, 5.0)
    ts = int(time.time())
    db.execute("INSERT INTO posts (id,title,body,status,created_at,published_at,platform,est_revenue) VALUES (?,?,?,?,?,?,?,?)",
               (post_id, title, body, 'published', ts, ts, ','.join(published_platforms), est))
    db.execute("INSERT INTO earnings (id,ts,platform,amount,note) VALUES (?,?,?,?,?)", (str(uuid.uuid4()), ts, 'mixed', est, 'demo sale'))
    db.execute("INSERT INTO events (id,ts,type,meta) VALUES (?,?,?,?)", (str(uuid.uuid4()), ts, 'published', post_id))
    db.commit()
    db.close()
    return published_platforms, est

@app.route('/generate_and_publish', methods=['POST','GET'])
def generate_and_publish():
    if not is_logged_in():
        return redirect(url_for('login'))
    data = request.get_json(force=False) or {}
    topic = data.get('topic') or request.args.get('topic') or 'Productos con mejor conversión hoy'
    title = f"{topic} - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
    body = generate_text_for_topic(topic)
    pid = str(uuid.uuid4())
    db = get_db()
    db.execute("INSERT INTO posts (id,title,body,status,created_at) VALUES (?,?,?,?,?)", (pid, title, body, 'draft', int(time.time())))
    db.commit()
    db.close()
    pubs, est = publish_to_platforms(pid, title, body)
    return jsonify({'id':pid,'published_on':pubs,'est_revenue':est})

worker_thread = None
worker_stop = threading.Event()

def optimize_strategies():
    db = get_db()
    cur = db.execute("SELECT id,name,score,last_run FROM strategies")
    rows = cur.fetchall()
    for r in rows:
        new_score = max(0.1, float(r['score']) * (1 + random.uniform(-0.05, 0.1)))
        db.execute("UPDATE strategies SET score=?, last_run=? WHERE id=?", (new_score, int(time.time()), r['id']))
    db.commit()
    db.close()

def auto_loop():
    print('Auto worker started (interval hours =', AUTO_INTERVAL_HOURS, ')')
    while not worker_stop.wait(AUTO_INTERVAL_HOURS * 3600):
        try:
            print('Auto worker cycle at', datetime.utcnow().isoformat())
            topics = ['Mejores auriculares 2025', 'Software de productividad para PYMES', 'Accesorios para telefonos baratas']
            for t in topics:
                generate_and_publish_internal(t)
            optimize_strategies()
        except Exception as e:
            print('Auto worker error', e)

def generate_and_publish_internal(topic):
    title = f"{topic} - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
    body = generate_text_for_topic(topic)
    pid = str(uuid.uuid4())
    db = get_db()
    db.execute("INSERT INTO posts (id,title,body,status,created_at) VALUES (?,?,?,?,?)", (pid, title, body, 'draft', int(time.time())))
    db.commit()
    db.close()
    publish_to_platforms(pid, title, body)

@app.route('/admin/start', methods=['POST'])
def admin_start():
    global worker_thread
    if not is_logged_in():
        return redirect(url_for('login'))
    if worker_thread and worker_thread.is_alive():
        return jsonify({'ok':False, 'msg':'already running'})
    worker_stop.clear()
    worker_thread = threading.Thread(target=auto_loop, daemon=True)
    worker_thread.start()
    return jsonify({'ok':True})

@app.route('/admin/stop', methods=['POST'])
def admin_stop():
    if not is_logged_in():
        return redirect(url_for('login'))
    worker_stop.set()
    return jsonify({'ok':True})

@app.route('/posts')
def list_posts():
    if not is_logged_in():
        return redirect(url_for('login'))
    db = get_db()
    cur = db.execute("SELECT id,title,status,published_at,est_revenue FROM posts ORDER BY created_at DESC LIMIT 200")
    rows = cur.fetchall()
    db.close()
    return render_template('posts.html', posts=rows)

@app.route('/earnings.csv')
def export_earnings():
    if not is_logged_in():
        return redirect(url_for('login'))
    db = get_db()
    cur = db.execute("SELECT ts,platform,amount,note FROM earnings ORDER BY ts DESC")
    rows = cur.fetchall()
    db.close()
    import csv, io
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['timestamp','platform','amount','note'])
    for r in rows:
        cw.writerow([r['ts'], r['platform'], r['amount'], r['note']])
    si.seek(0)
    return send_file(io.BytesIO(si.getvalue().encode()), mimetype='text/csv', as_attachment=True, download_name='earnings.csv')

@app.route('/')
def home():
    if not is_logged_in():
        return redirect(url_for('login'))
    return redirect(url_for('status'))

if os.environ.get('AUTO_START','1') == '1':
    try:
        if 'worker_thread' not in globals() or worker_thread is None or not (worker_thread and worker_thread.is_alive()):
            worker_thread = threading.Thread(target=auto_loop, daemon=True)
            worker_thread.start()
    except Exception as e:
        print('Could not auto-start worker', e)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=False)
