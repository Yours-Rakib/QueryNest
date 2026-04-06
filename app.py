from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import sqlite3, re, os, datetime

app = Flask(__name__)
app.secret_key = 'querynest_secret_key_2026'

DB_PATH = 'querynest.db'
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXT = {'pdf', 'docx', 'pptx', 'xlsx', 'png', 'jpg', 'jpeg', 'zip', 'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur  = conn.cursor()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def home():
    conn    = get_db()
    notices = conn.execute("SELECT * FROM notices ORDER BY publish_date DESC LIMIT 5").fetchall()
    conn.close()
    return render_template('home.html', notices=notices)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('home'))
    if request.method == 'POST':
        name     = request.form['name'].strip()
        password = request.form['password']
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id']   = user['user_id']
            session['user_name'] = user['name']
            session['role']      = user['role']
            flash(f"Welcome back, {user['name']}!", 'success')
            return redirect(url_for('admin_dashboard') if user['role'] == 'admin' else url_for('home'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('home'))
    if request.method == 'POST':
        name    = request.form['name'].strip()
        email   = request.form.get('email', '').strip()
        pw      = request.form['password']
        confirm = request.form['confirm_password']
        if len(name) < 3:
            flash('Username must be at least 3 characters.', 'danger')
            return render_template('register.html')
        if len(pw) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('register.html')
        if pw != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('register.html')
        conn     = get_db()
        existing = conn.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
        if existing:
            conn.close()
            flash('Username already taken.', 'danger')
            return render_template('register.html')
        conn.execute(
            "INSERT INTO users (name, email, display_name, password, role) VALUES (?,?,?,?,?)",
            (name, email, name, generate_password_hash(pw), 'student')
        )
        conn.commit(); conn.close()
        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/chatbot')
@login_required
def chatbot():
    conn = get_db()
    # Feature #3: Top 6 most-used FAQ chips
    top_faqs = conn.execute('''
        SELECT f.question, f.category, COUNT(ch.chat_id) as cnt
        FROM faqs f LEFT JOIN chat_history ch ON ch.matched_faq = f.question
        GROUP BY f.faq_id ORDER BY cnt DESC LIMIT 6
    ''').fetchall()
    # Feature #4: chat history with timestamps
    history = conn.execute('''
        SELECT * FROM chat_history WHERE user_id=? ORDER BY timestamp DESC LIMIT 50
    ''', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('chatbot.html', suggestions=top_faqs, history=history)

@app.route('/chatbot/ask', methods=['POST'])
@login_required
def chatbot_ask():
    data    = request.get_json()
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'answer': 'Please type a question first.', 'matched': False})

    result    = chatbot_response(message)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = get_db()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO chat_history (user_id, message, response, matched_faq, category, timestamp) VALUES (?,?,?,?,?,?)",
        (session['user_id'], message, result['answer'], result.get('question'), result.get('category'), timestamp)
    )
    chat_id = cur.lastrowid

    # Feature #2: auto-flag unmatched
    if not result['matched']:
        conn.execute(
            "INSERT INTO unmatched_queries (user_id, query_text, timestamp) VALUES (?,?,?)",
            (session['user_id'], message, timestamp)
        )

    conn.commit(); conn.close()
    result['chat_id']   = chat_id
    result['timestamp'] = timestamp
    return jsonify(result)

def chatbot_response(user_message):
    clean = re.sub(r'[^\w\s]', '', user_message.lower())
    words = set(clean.split())
    stop_words = {'what','is','the','how','when','where','who','are','a','an','do','does','can','i','my','for','to','of','in','it','be','get','was','will'}
    words -= stop_words

    conn = get_db()
    faqs = conn.execute("SELECT * FROM faqs").fetchall()
    conn.close()

    best_faq   = None
    best_score = 0

    for faq in faqs:
        kw_words  = set((faq['keywords'] or '').lower().split())
        q_words   = set(re.sub(r'[^\w\s]', '', faq['question'].lower()).split()) - stop_words
        faq_words = kw_words | q_words
        score = len(words & faq_words)
        if score > best_score:
            best_score = score
            best_faq   = faq

    confidence = 'High' if best_score >= 2 else 'Low'

    if best_faq and best_score >= 1:
        return {
            'answer':     best_faq['answer'],
            'question':   best_faq['question'],
            'category':   best_faq['category'],
            'faq_id':     best_faq['faq_id'],
            'confidence': confidence,
            'matched':    True
        }
    return {
        'answer':     "Sorry, I couldn't find an answer to that. Try rephrasing your question, or browse the Academic Info page.",
        'question':   None,
        'category':   None,
        'faq_id':     None,
        'confidence': None,
        'matched':    False
    }
@app.route('/chatbot')
@login_required
def chatbot():
    conn = get_db()
    # Feature #3: Top 6 FAQ chips
    top_faqs = conn.execute('''
        SELECT f.question, f.category, COUNT(ch.chat_id) as cnt
        FROM faqs f LEFT JOIN chat_history ch ON ch.matched_faq = f.question
        GROUP BY f.faq_id ORDER BY cnt DESC LIMIT 6
    ''').fetchall()
    history = conn.execute(
        'SELECT * FROM chat_history WHERE user_id=? ORDER BY timestamp DESC LIMIT 50',
        (session['user_id'],)
    ).fetchall()
    conn.close()
    return render_template('chatbot.html', suggestions=top_faqs, history=history)