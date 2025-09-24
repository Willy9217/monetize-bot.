# monetize_bot_ready.py
# Versión mejorada y revisada: auto-generación y publicación solo si hay enlaces afiliados.
# Use ONLY on domains you own. Edit .env before deploying.

from flask import Flask, request, jsonify, render_template_string, g, abort
import os, re, sqlite3, time, uuid, threading, logging
from datetime import datetime

try:
    import openai
except Exception:
    openai = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('monetize_bot_ready')

DB_PATH = os.environ.get('AMB_DB', '/data/amb_data.sqlite')
OPENAI_KEY = os.environ.get('OPENAI_API_KEY', '').strip()
SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me')
AFFIL_DOMAINS = [d.strip() for d in os.environ.get('AFFIL_DOMAINS', 'amazon.com,clickbank.net,shareasale.com').split(',') if d.strip()]
AUTO_INTERVAL_MIN = int(os.environ.get('AUTO_INTERVAL_MIN', '120'))
AUTO_START = os.environ.get('AMB_AUTO_START', '1') == '1'
CONTENT_DIR = os.environ.get('CONTENT_DIR', '/data/content')
os.makedirs(CONTENT_DIR, exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db_dir = os.path.dirname(DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
            except Exception:
                pass
        db = g._database = sqlite3.connect(DB_PATH, check_same_thread=False)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    cur = db.cursor()
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS posts (
        id TEXT PRIMARY KEY,
        title TEXT,
        body TEXT,
        status TEXT,
        created_at INTEGER,
        published_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        ts INTEGER,
        type TEXT,
        meta TEXT
    );
    ''')
    db.commit()

def openai_generate(prompt, max_tokens=700):
    # Robust generation: try ChatCompletion, fallback to Completion if available, else return template
    if OPENAI_KEY and openai:
        try:
            openai.api_key = OPENAI_KEY
            # prefer ChatCompletion if available
            if hasattr(openai, 'ChatCompletion'):
                resp = openai.ChatCompletion.create(model='gpt-3.5-turbo', messages=[{'role':'user','content':prompt}], max_tokens=max_tokens, temperature=0.7)
                return resp.choices[0].message.content.strip()
            else:
                # fallback to Completion API
                resp = openai.Completion.create(model='text-davinci-003', prompt=prompt, max_tokens=max_tokens, temperature=0.7)
                return resp.choices[0].text.strip()
        except Exception as e:
            logger.warning('OpenAI generation failed: %s', e)
            return None
    # fallback template (useful for testing without API key)
    return f"{prompt}\n\n[Contenido de ejemplo generado. Reemplaza con OPENAI_API_KEY para mejor calidad]\nVisita: https://amazon.com/dp/EXAMPLE?tag=affiliate"

def contains_affiliate_links(text):
    if not text:
        return False
    for d in AFFIL_DOMAINS:
        if d.lower() in text.lower():
            return True
    # detect common affiliate token patterns
    if re.search(r'(\btag=|\baffiliate=|\baff_id=|\bref=|\butm_source=)', text, re.IGNORECASE):
        return True
    return False

def save_post(title, body, status='draft'):
    db = get_db()
    pid = str(uuid.uuid4())
    db.execute('INSERT INTO posts (id,title,body,status,created_at) VALUES (?,?,?,?,?)'[:1],) if False else None
    db.execute('INSERT INTO posts (id,title,body,status,created_at) VALUES (?,?,?,?,?)', (pid, title[:200], body, status, int(time.time())))
    db.commit()
    # save a human-readable copy for review if needed
    try:
        fname = os.path.join(CONTENT_DIR, f"{pid}.html")
        with open(fname, 'w', encoding='utf-8') as f:
            f.write(f"<h1>{title}</h1>\n" + body)
    except Exception:
        pass
    return pid

def publish_if_monetized(pid):
    db = get_db()
    cur = db.execute('SELECT * FROM posts WHERE id=?', (pid,))
    row = cur.fetchone()
    if not row:
        return False, 'not_found'
    body = row['body'] or ''
    if contains_affiliate_links(body):
        db.execute('UPDATE posts SET status=?, published_at=? WHERE id=?', ('published', int(time.time()), pid))
        db.commit()
        db.execute('INSERT INTO events (id,ts,type,meta) VALUES (?,?,?,?)', (str(uuid.uuid4()), int(time.time()), 'published', pid))
        db.commit()
        return True, 'published'
    else:
        db.execute('INSERT INTO events (id,ts,type,meta) VALUES (?,?,?,?)', (str(uuid.uuid4()), int(time.time()), 'rejected_no_aff', pid))
        db.commit()
        return False, 'no_affil_links'

@app.route('/generate_and_publish', methods=['POST'])
def generate_and_publish():
    data = request.get_json(force=True)
    topic = data.get('topic') if data else None
    if not topic:
        topic = 'Top converting products and deals this week'
    prompt = f"Escribe un artículo comercial optimizado para conversiones sobre: {topic}. Incluye al menos 2 enlaces a dominios afiliados y llamadas a la acción claras. Estructura con subtítulos y bullets."
    body = openai_generate(prompt)
    if body is None:
        return jsonify({'error':'generation_failed'}), 500
    pid = save_post(topic, body)
    ok, reason = publish_if_monetized(pid)
    return jsonify({'id':pid, 'published':ok, 'reason':reason})

# Background auto worker
stop_bg = threading.Event()
def auto_worker():
    logger.info('Auto worker started, interval %s minutes', AUTO_INTERVAL_MIN)
    while not stop_bg.wait(AUTO_INTERVAL_MIN * 60):
        try:
            prompt_topic = 'Top converting products and deals this week'
            prompt = f"Escribe un artículo comercial optimizado para conversiones sobre: {prompt_topic}. Incluye al menos 2 enlaces a dominios afiliados y llamadas a la acción claras."
            logger.info('Auto-generating content...')
            body = openai_generate(prompt)
            if not body:
                logger.warning('Auto generation returned empty; skipping this cycle')
                continue
            pid = save_post(prompt_topic, body)
            ok, reason = publish_if_monetized(pid)
            logger.info('Auto cycle: pid=%s published=%s reason=%s', pid, ok, reason)
        except Exception as e:
            logger.exception('Auto worker error: %s', e)

bg_thread = threading.Thread(target=auto_worker, daemon=True)

@app.route('/admin/start-auto', methods=['POST'])
def start_auto():
    global bg_thread
    if bg_thread.is_alive():
        return jsonify({'ok':False, 'msg':'already running'})
    bg_thread = threading.Thread(target=auto_worker, daemon=True)
    bg_thread.start()
    return jsonify({'ok':True})

@app.route('/admin/stop-auto', methods=['POST'])
def stop_auto():
    stop_bg.set()
    return jsonify({'ok':True})

@app.route('/admin/status', methods=['GET'])
def admin_status():
    db = get_db()
    cur = db.execute('SELECT COUNT(*) as drafts FROM posts WHERE status="draft"')
    drafts = cur.fetchone()['drafts']
    cur = db.execute('SELECT COUNT(*) as pub FROM posts WHERE status="published"')
    pub = cur.fetchone()['pub']
    return jsonify({'drafts':drafts, 'published':pub, 'auto_running': bg_thread.is_alive()})

@app.route('/')
def index():
    return render_template_string('<h2>Monetize Bot Ready - Panel</h2><p>Visita /admin/status y /generate_and_publish</p>')

@app.route('/posts')
def list_posts():
    db = get_db()
    cur = db.execute("SELECT id,title,published_at FROM posts WHERE status='published' ORDER BY published_at DESC")
    rows = cur.fetchall()
    html = '<h1>Publicaciones</h1><ul>'
    for r in rows:
        ts = r['published_at'] or r['published_at']
        html += f"<li><a href='/post/{r['id']}'>{r['title']}</a> - {ts}</li>"
    html += '</ul>'
    return html

@app.route('/post/<pid>')
def view_post(pid):
    db = get_db()
    cur = db.execute('SELECT * FROM posts WHERE id=?', (pid,))
    row = cur.fetchone()
    if not row:
        return 'No encontrado', 404
    return f"<h1>{row['title']}</h1><div>{row['body']}</div>"

@app.after_request
def set_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer-when-downgrade'
    return response

if __name__ == '__main__':
    with app.app_context():
        init_db()
        if AUTO_START:
            try:
                bg_thread.start()
            except RuntimeError:
                pass
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT','5000')), debug=False)
