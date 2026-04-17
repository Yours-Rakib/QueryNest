from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import sqlite3, re, os, datetime

app = Flask(__name__)
app.secret_key = 'querynest_secret_key_2026'

DB_PATH     = 'querynest.db'
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXT   = {'pdf', 'docx', 'pptx', 'xlsx', 'png', 'jpg', 'jpeg', 'zip', 'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ─── Database ─────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur  = conn.cursor()

    # Core tables
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL UNIQUE,
            email        TEXT DEFAULT '',
            display_name TEXT DEFAULT '',
            avatar       TEXT DEFAULT '',
            password     TEXT NOT NULL,
            role         TEXT NOT NULL CHECK(role IN ('student','admin'))
        )
    ''')
    # Add avatar column if upgrading existing DB
    try:
        cur.execute("ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT ''")
    except Exception:
        pass
    cur.execute('''
        CREATE TABLE IF NOT EXISTS faqs (
            faq_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            question  TEXT NOT NULL,
            answer    TEXT NOT NULL,
            keywords  TEXT,
            category  TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS notices (
            notice_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            description  TEXT NOT NULL,
            publish_date TEXT NOT NULL,
            attachment   TEXT
        )
    ''')

    # Module 1 tables
    cur.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            chat_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            message      TEXT NOT NULL,
            response     TEXT NOT NULL,
            matched_faq  TEXT,
            category     TEXT,
            rating       TEXT DEFAULT NULL,
            timestamp    TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS unmatched_queries (
            query_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER,
            query_text   TEXT NOT NULL,
            timestamp    TEXT NOT NULL,
            converted    INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS faq_ratings (
            rating_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            faq_id       INTEGER,
            chat_id      INTEGER,
            user_id      INTEGER,
            rating       TEXT NOT NULL CHECK(rating IN ('helpful','not_helpful')),
            timestamp    TEXT NOT NULL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            feedback_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER,
            user_name    TEXT,
            content      TEXT NOT NULL,
            status       TEXT DEFAULT 'Pending',
            timestamp    TEXT NOT NULL
        )
    ''')

    # Module 2 tables
    cur.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            course_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT NOT NULL,
            title       TEXT NOT NULL,
            credits     REAL NOT NULL,
            semester    TEXT NOT NULL,
            type        TEXT NOT NULL CHECK(type IN ('Theory','Lab'))
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS exam_routine (
            exam_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT NOT NULL,
            course_name TEXT NOT NULL,
            exam_date   TEXT NOT NULL,
            exam_time   TEXT NOT NULL,
            room        TEXT NOT NULL,
            exam_type   TEXT NOT NULL CHECK(exam_type IN ('Midterm','Final'))
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS mark_distribution (
            mark_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            component   TEXT NOT NULL,
            marks       INTEGER NOT NULL,
            description TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS lab_schedule (
            lab_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT NOT NULL,
            course_name TEXT NOT NULL,
            day         TEXT NOT NULL,
            time        TEXT NOT NULL,
            room        TEXT NOT NULL,
            instructor  TEXT NOT NULL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS resources (
            resource_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            description  TEXT,
            url          TEXT,
            resource_type TEXT NOT NULL,
            topic        TEXT NOT NULL,
            emoji        TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS events (
            event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            description  TEXT,
            event_date   TEXT NOT NULL,
            event_type   TEXT NOT NULL,
            link         TEXT,
            location     TEXT,
            platform     TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS study_materials (
            material_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            description  TEXT,
            filename     TEXT NOT NULL,
            category     TEXT NOT NULL,
            uploaded_at  TEXT NOT NULL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS career_paths (
            path_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            description  TEXT,
            skills       TEXT,
            tools        TEXT,
            icon         TEXT,
            logo         TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clubs (
            club_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            description  TEXT,
            contact      TEXT,
            category     TEXT,
            logo         TEXT,
            motto        TEXT,
            link         TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS scholarships (
            scholarship_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title          TEXT NOT NULL,
            description    TEXT,
            deadline       TEXT,
            link           TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS internships (
            internship_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            title          TEXT NOT NULL,
            company        TEXT,
            description    TEXT,
            deadline       TEXT,
            link           TEXT
        )
    ''')

    # ── Seed Admin ─────────────────────────────────────────────────────────────
    cur.execute("SELECT * FROM users WHERE role='admin'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (name, email, display_name, password, role) VALUES (?,?,?,?,?)",
            ('admin', 'admin@querynest.edu', 'Administrator', generate_password_hash('admin123'), 'admin')
        )
    else:
        # Ensure admin password is always valid (fixes stale hash issues)
        cur.execute("UPDATE users SET password=? WHERE role='admin'",
                    (generate_password_hash('admin123'),))

    # ── Seed FAQs ──────────────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM faqs")
    if cur.fetchone()[0] == 0:
        sample_faqs = [
            ('What is the credit hour for SWE courses?',
             'Most SWE theory courses carry 3 credit hours. Lab courses carry 1.5 credit hours.',
             'credit hour credits course', 'Academic'),
            ('How is the grading policy structured?',
             'DIU Grading Scale:\n- A+ = 90-100 (GPA 4.00)\n- A  = 85-89  (GPA 3.75)\n- A- = 80-84  (GPA 3.50)\n- B+ = 75-79  (GPA 3.25)\n- B  = 70-74  (GPA 3.00)\n- B- = 65-69  (GPA 2.75)\n- C+ = 60-64  (GPA 2.50)\n- C  = 55-59  (GPA 2.25)\n- D  = 50-54  (GPA 2.00)\n- F  = below 50 (Fail)',
             'grade grading marks result gpa cgpa', 'Academic'),
            ('When is the exam routine published?',
             'The exam routine is published 2 weeks before semester finals. Check the Academic Info page for the current schedule.',
             'exam routine schedule date published', 'Exam'),
            ('What is the passing mark?',
             'The minimum passing mark is 50 out of 100. Below 50 means F grade and you must retake the course.',
             'pass fail minimum mark score', 'Academic'),
            ('How many absences are allowed?',
             'Students must maintain at least 75% attendance to sit for final exams. More than 25% absences = dropped from course.',
             'absent attendance class allowed percentage', 'Academic'),
            ('What is the mark distribution for theory courses?',
             'Theory Course Marks:\n- Attendance: 7\n- Assignment: 5\n- Presentation: 8\n- Quiz: 15\n- Midterm Exam: 25\n- Final Exam: 40\nTotal: 100 marks',
             'mark distribution theory assignment quiz midterm final', 'Exam'),
            ('What is the mark distribution for lab courses?',
             'Lab Course Marks:\n- Lab Performance: 30\n- Lab Report: 20\n- Lab Test/Viva: 50\nTotal: 100 marks',
             'mark distribution lab report viva performance', 'Exam'),
            ('What courses are available this semester?',
             'Current SWE courses: Data Structures, Algorithm Design, Database Management, Software Engineering, Computer Networks, and their labs.',
             'course available semester swe subject syllabus', 'Academic'),
            ('What is the project guideline for SWE courses?',
             'SWE Project Rules:\n- Teams of 3-4 students\n- Topic approved by supervisor\n- Proposal: Week 4\n- Progress report: Week 8\n- Final presentation: Week 16',
             'project guideline team supervisor proposal presentation', 'Lab'),
            ('How do I contact my teacher?',
             'Contact your course teacher through the department office or via the official DIU student email. Faculty details are on the DIU website.',
             'teacher contact faculty instructor professor', 'Academic'),
            ('What is the retake policy?',
             'Students who fail (F grade) must retake the course in the next available semester. Retakes are subject to normal registration fees.',
             'retake repeat fail course policy', 'Academic'),
            ('How do I register for courses?',
             'Course registration is done through the DIU student portal during the registration period. Contact your advisor if you face issues.',
             'register registration enroll course portal', 'Academic'),
        ]
        cur.executemany(
            "INSERT INTO faqs (question, answer, keywords, category) VALUES (?,?,?,?)",
            sample_faqs
        )

    # ── Seed Notices ───────────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM notices")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO notices (title, description, publish_date) VALUES (?,?,?)",
            [
                ('Mid-term Exam Schedule Released',
                 'Mid-term exams will begin from April 10, 2026. Check the department notice board for room assignments and timing details.',
                 '2026-03-28'),
                ('Lab Report Submission Deadline',
                 'All pending lab reports must be submitted by April 5, 2026. Late submissions will not be accepted without prior permission.',
                 '2026-03-25'),
                ('Scholarship Application Open',
                 'Applications for the merit-based scholarship are now open. Eligible students with CGPA above 3.5 can apply. Deadline: April 20, 2026.',
                 '2026-03-20'),
                ('Department Seminar on AI & ML',
                 'A seminar on Artificial Intelligence and Machine Learning will be held on April 15, 2026 in Auditorium Hall B.',
                 '2026-03-15'),
                ('Internship Drive by TechCorp BD',
                 'TechCorp Bangladesh is visiting campus for internship recruitment on April 12, 2026. Interested students must register by April 8.',
                 '2026-03-12'),
            ]
        )

    # ── Seed Courses ───────────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM courses")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO courses (code, title, credits, semester, type) VALUES (?,?,?,?,?)",
            [
                ('SWE101',  'Introduction to Programming',     3.0, 'Spring 2026', 'Theory'),
                ('SWE101L', 'Introduction to Programming Lab', 1.5, 'Spring 2026', 'Lab'),
                ('SWE201',  'Data Structures',                 3.0, 'Spring 2026', 'Theory'),
                ('SWE201L', 'Data Structures Lab',             1.5, 'Spring 2026', 'Lab'),
                ('SWE301',  'Algorithm Design & Analysis',     3.0, 'Spring 2026', 'Theory'),
                ('SWE302',  'Database Management System',      3.0, 'Spring 2026', 'Theory'),
                ('SWE302L', 'Database Management Lab',         1.5, 'Spring 2026', 'Lab'),
                ('SWE401',  'Software Engineering',            3.0, 'Spring 2026', 'Theory'),
                ('SWE402',  'Computer Networks',               3.0, 'Spring 2026', 'Theory'),
                ('SWE402L', 'Computer Networks Lab',           1.5, 'Spring 2026', 'Lab'),
            ]
        )

    # ── Seed Exam Routine ──────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM exam_routine")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO exam_routine (course_code, course_name, exam_date, exam_time, room, exam_type) VALUES (?,?,?,?,?,?)",
            [
                ('SWE201', 'Data Structures',     '2026-04-10', '09:00 AM - 11:00 AM', 'Room 301', 'Midterm'),
                ('SWE301', 'Algorithm Design',    '2026-04-11', '11:00 AM - 01:00 PM', 'Room 302', 'Midterm'),
                ('SWE302', 'Database Management', '2026-04-12', '09:00 AM - 11:00 AM', 'Room 303', 'Midterm'),
                ('SWE401', 'Software Engineering','2026-04-13', '02:00 PM - 04:00 PM', 'Room 301', 'Midterm'),
                ('SWE402', 'Computer Networks',   '2026-04-14', '09:00 AM - 11:00 AM', 'Room 304', 'Midterm'),
                ('SWE201', 'Data Structures',     '2026-06-10', '09:00 AM - 12:00 PM', 'Room 301', 'Final'),
                ('SWE301', 'Algorithm Design',    '2026-06-11', '09:00 AM - 12:00 PM', 'Room 302', 'Final'),
                ('SWE302', 'Database Management', '2026-06-12', '09:00 AM - 12:00 PM', 'Room 303', 'Final'),
                ('SWE401', 'Software Engineering','2026-06-13', '02:00 PM - 05:00 PM', 'Room 301', 'Final'),
                ('SWE402', 'Computer Networks',   '2026-06-14', '09:00 AM - 12:00 PM', 'Room 304', 'Final'),
            ]
        )

    # ── Seed Mark Distribution ─────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM mark_distribution")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO mark_distribution (component, marks, description) VALUES (?,?,?)",
            [
                ('Attendance',    7,  'Based on class attendance percentage'),
                ('Assignment',    5,  'Home assignments submitted each week'),
                ('Presentation',  8,  'In-class presentations and demos'),
                ('Quiz',         15,  'In-class quizzes throughout semester'),
                ('Midterm Exam', 25,  'Written exam at mid-semester'),
                ('Final Exam',   40,  'Comprehensive exam at end of semester'),
            ]
        )

    # ── Seed Lab Schedule ─────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM lab_schedule")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO lab_schedule (course_code, course_name, day, time, room, instructor) VALUES (?,?,?,?,?,?)",
            [
                ('SWE101L', 'Intro to Programming Lab', 'Sunday',    '08:00 AM - 10:30 AM', 'Lab 101', 'Dr. Iqbal'),
                ('SWE201L', 'Data Structures Lab',      'Monday',    '11:00 AM - 01:30 PM', 'Lab 102', 'Mr. Karim'),
                ('SWE302L', 'Database Management Lab',  'Tuesday',   '02:00 PM - 04:30 PM', 'Lab 103', 'Ms. Nusrat'),
                ('SWE402L', 'Computer Networks Lab',    'Wednesday', '08:00 AM - 10:30 AM', 'Lab 104', 'Dr. Hasan'),
            ]
        )

    # ── Seed Resources ────────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM resources")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO resources (title, description, url, resource_type, topic) VALUES (?,?,?,?,?)",
            [
                ('Introduction to Algorithms (CLRS)', 'The definitive algorithms textbook', 'https://mitpress.mit.edu/9780262046305/', 'Book', 'DSA'),
                ('CS50 on YouTube', 'Harvard free intro CS course', 'https://www.youtube.com/@cs50', 'YouTube', 'DSA'),
                ('GeeksforGeeks DSA', 'Practice and theory for DSA', 'https://www.geeksforgeeks.org/data-structures/', 'Website', 'DSA'),
                ('SQLZoo', 'Interactive SQL learning', 'https://sqlzoo.net/', 'Website', 'DBMS'),
                ('MySQL Tutorial', 'Complete MySQL learning guide', 'https://www.mysqltutorial.org/', 'Tutorial', 'DBMS'),
                ('Traversy Media', 'Full-stack web dev tutorials', 'https://www.youtube.com/@TraversyMedia', 'YouTube', 'Networking'),
                ('Computer Networking: A Top-Down Approach', 'Kurose & Ross - Standard networking textbook', 'https://www.pearson.com/', 'Book', 'Networking'),
                ('freeCodeCamp', 'Free coding bootcamp with certificates', 'https://www.freecodecamp.org/', 'Tutorial', 'DSA'),
                ('The Odin Project', 'Full stack curriculum', 'https://www.theodinproject.com/', 'Tutorial', 'DBMS'),
                ('TechWorld with Nana', 'DevOps and cloud tutorials', 'https://www.youtube.com/@TechWorldwithNana', 'YouTube', 'Networking'),
            ]
        )

    # ── Seed Events ───────────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM events")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO events (title, description, event_date, event_type, link, location) VALUES (?,?,?,?,?,?)",
            [
                ('ICPC Asia Regional 2026', 'International Collegiate Programming Contest Asia Regional', '2026-05-15', 'Contest', 'https://icpc.global', 'Online'),
                ('HackDIU Spring 2026', 'DIU Intra-university Hackathon – 24-hour coding sprint', '2026-04-25', 'Hackathon', 'https://diu.edu.bd', 'DIU Campus'),
                ('Google I/O Extended Dhaka', 'Google developer conference extended event in Dhaka', '2026-05-20', 'Tech Event', 'https://io.google', 'Dhaka'),
                ('Codeforces Round 1000', 'Codeforces Div. 2 rated round', '2026-04-18', 'Contest', 'https://codeforces.com', 'Online'),
                ('Meta Hacker Cup 2026', 'Facebook/Meta annual programming competition', '2026-06-01', 'Contest', 'https://www.facebook.com/hackercup/', 'Online'),
                ('BdOSN DevFest 2026', 'Bangladesh Open Source Network developer festival', '2026-05-10', 'Tech Event', 'https://bdosn.org', 'Dhaka'),
            ]
        )

    # ── Seed Career Paths ─────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM career_paths")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO career_paths (title, description, skills, tools, icon) VALUES (?,?,?,?,?)",
            [
                ('Backend Developer', 'Build server-side logic, APIs, and databases',
                 'Python, Java, Node.js, SQL, REST APIs, System Design',
                 'Django, Spring Boot, Express, PostgreSQL, Redis, Docker', 'bi-server'),
                ('Frontend Developer', 'Design and build interactive user interfaces',
                 'HTML, CSS, JavaScript, TypeScript, React, UI/UX Design',
                 'React, Vue, Tailwind CSS, Figma, Webpack, Git', 'bi-display'),
                ('DevOps Engineer', 'Manage infrastructure, CI/CD and cloud deployments',
                 'Linux, Bash, Cloud (AWS/GCP), Docker, Kubernetes, Networking',
                 'Jenkins, GitHub Actions, Terraform, Ansible, Prometheus', 'bi-cloud-upload'),
                ('Data Engineer / AI Engineer / ML Engineer', 'Build data pipelines and machine learning systems',
                 'Python, Statistics, Linear Algebra, Machine Learning, Deep Learning',
                 'TensorFlow, PyTorch, Pandas, Scikit-learn, Jupyter, Spark', 'bi-cpu'),
                ('Mobile Developer', 'Develop Android, iOS or cross-platform apps',
                 'Dart, Kotlin/Java (Android), Swift (iOS), REST APIs',
                 'Flutter, React Native, Android Studio, Xcode, Firebase', 'bi-phone'),
                ('Cybersecurity Engineer', 'Protect systems and networks from threats',
                 'Networking, Linux, Cryptography, Ethical Hacking, Security Audits',
                 'Kali Linux, Wireshark, Metasploit, Burp Suite, Nmap', 'bi-shield-lock'),
            ]
        )

    # ── Seed Clubs ────────────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM clubs")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO clubs (name, description, contact, category) VALUES (?,?,?,?)",
            [
                ('DIU Computer & Programming Club', 'Competitive programming, problem solving, ICPC prep', 'cpc@diu.edu.bd', 'Technical'),
                ('DIU Robotics Club', 'Robotics, IoT, and hardware projects', 'robotics@diu.edu.bd', 'Technical'),
                ('DIU Debate Club', 'Public speaking, debate competitions nationwide', 'debate@diu.edu.bd', 'Cultural'),
                ('DIU Photography Club', 'Campus photography, workshops, exhibitions', 'photo@diu.edu.bd', 'Cultural'),
                ('DIU Entrepreneurs Club', 'Startup ideas, business pitches, networking events', 'entrepreneur@diu.edu.bd', 'Business'),
            ]
        )

    # ── Seed Scholarships ─────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM scholarships")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO scholarships (title, description, deadline, link) VALUES (?,?,?,?)",
            [
                ('DIU Merit Scholarship', '50% waiver for students with CGPA 3.5+', '2026-04-20', 'https://diu.edu.bd/scholarship'),
                ('ICT Ministry Fellowship', 'Govt. scholarship for top SWE students in BD', '2026-05-01', 'https://ictd.gov.bd'),
                ('BASIS Scholarship', 'Software industry scholarship by BASIS', '2026-06-15', 'https://basis.org.bd'),
            ]
        )

    # ── Seed Internships ──────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM internships")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO internships (title, company, description, deadline, link) VALUES (?,?,?,?,?)",
            [
                ('Junior Software Engineer Intern', 'Brain Station 23', '3-month paid internship for CSE/SWE students', '2026-04-10', 'https://brainstation-23.com'),
                ('Backend Dev Intern', 'Shajgoj Ltd.', 'Node.js internship role', '2026-04-15', 'https://shajgoj.com'),
                ('Data Science Intern', 'BJIT Ltd.', 'Python & ML internship for final year students', '2026-05-01', 'https://bjitgroup.com'),
            ]
        )

    conn.commit()
    # ── Migrations ────────────────────────────────────────────────────────────
    try:
        cur.execute("ALTER TABLE notices ADD COLUMN attachment TEXT")
        conn.commit()
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE resources ADD COLUMN emoji TEXT")
        conn.commit()
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE career_paths ADD COLUMN logo TEXT")
        conn.commit()
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE events ADD COLUMN platform TEXT")
        conn.commit()
    except Exception:
        pass
    for col in ['logo TEXT', 'motto TEXT', 'link TEXT']:
        try:
            cur.execute(f"ALTER TABLE clubs ADD COLUMN {col}")
            conn.commit()
        except Exception:
            pass
    conn.close()


# ─── Chatbot Logic ────────────────────────────────────────────────────────────

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


# ─── Decorators ───────────────────────────────────────────────────────────────

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


# ─── Public Routes ────────────────────────────────────────────────────────────

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


# ─── Feature #21: Student Profile ─────────────────────────────────────────────

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (session['user_id'],)).fetchone()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_profile':
            display_name = request.form.get('display_name', '').strip()
            email        = request.form.get('email', '').strip()
            # Handle avatar upload
            avatar_filename = user['avatar'] or ''
            file = request.files.get('avatar')
            if file and file.filename:
                ext = file.filename.rsplit('.', 1)[-1].lower()
                if ext in {'png', 'jpg', 'jpeg', 'gif', 'webp'}:
                    avatar_filename = f"avatar_{session['user_id']}.{ext}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], avatar_filename))
            conn.execute("UPDATE users SET display_name=?, email=?, avatar=? WHERE user_id=?",
                         (display_name, email, avatar_filename, session['user_id']))
            conn.commit()
            session['user_name'] = user['name']
            flash('Profile updated successfully!', 'success')
        elif action == 'change_password':
            current  = request.form.get('current_password')
            new_pw   = request.form.get('new_password')
            confirm  = request.form.get('confirm_password')
            if not check_password_hash(user['password'], current):
                flash('Current password is incorrect.', 'danger')
            elif len(new_pw) < 6:
                flash('New password must be at least 6 characters.', 'danger')
            elif new_pw != confirm:
                flash('New passwords do not match.', 'danger')
            else:
                conn.execute("UPDATE users SET password=? WHERE user_id=?",
                             (generate_password_hash(new_pw), session['user_id']))
                conn.commit()
                flash('Password changed successfully!', 'success')
        conn.close()
        return redirect(url_for('profile'))
    conn.close()
    return render_template('profile.html', user=user)


# ─── Feature #4 & #1: Chatbot with history + confidence ──────────────────────

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

@app.route('/chatbot/rate', methods=['POST'])
@login_required
def chatbot_rate():
    """Feature #5: Per-response rating"""
    data    = request.get_json()
    chat_id = data.get('chat_id')
    rating  = data.get('rating')  # 'helpful' or 'not_helpful'
    if not chat_id or rating not in ('helpful', 'not_helpful'):
        return jsonify({'ok': False})
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    # Update chat_history rating
    conn.execute("UPDATE chat_history SET rating=? WHERE chat_id=? AND user_id=?",
                 (rating, chat_id, session['user_id']))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


# ─── Feature #6: Student Feedback ────────────────────────────────────────────

@app.route('/feedback', methods=['GET', 'POST'])
@login_required
def feedback():
    if request.method == 'POST':
        content   = request.form.get('content', '').strip()
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if content:
            conn = get_db()
            conn.execute(
                "INSERT INTO feedback (user_id, user_name, content, status, timestamp) VALUES (?,?,?,?,?)",
                (session['user_id'], session['user_name'], content, 'Pending', timestamp)
            )
            conn.commit(); conn.close()
            flash('Feedback submitted! Thank you.', 'success')
        else:
            flash('Please write something before submitting.', 'warning')
        return redirect(url_for('feedback'))
    return render_template('feedback.html')


# ─── Feature #7: FAQ Browse ───────────────────────────────────────────────────

@app.route('/faqs')
@login_required
def faq_browse():
    category = request.args.get('category', '')
    search   = request.args.get('search', '')
    conn     = get_db()
    query    = "SELECT * FROM faqs WHERE 1=1"
    params   = []
    if category:
        query += " AND category=?"
        params.append(category)
    if search:
        query += " AND (question LIKE ? OR answer LIKE ?)"
        params += [f'%{search}%', f'%{search}%']
    faqs       = conn.execute(query + " ORDER BY category", params).fetchall()
    categories = conn.execute("SELECT DISTINCT category FROM faqs ORDER BY category").fetchall()
    conn.close()
    return render_template('faq_browse.html', faqs=faqs, categories=categories,
                           current_category=category, search=search)


# ─── Feature #8: Resource Library ────────────────────────────────────────────

@app.route('/resources')
@login_required
def resources():
    topic = request.args.get('topic', '')
    conn  = get_db()
    if topic:
        items = conn.execute("SELECT * FROM resources WHERE topic=? ORDER BY resource_type", (topic,)).fetchall()
    else:
        items = conn.execute("SELECT * FROM resources ORDER BY topic, resource_type").fetchall()
    topics = conn.execute("SELECT DISTINCT topic FROM resources ORDER BY topic").fetchall()
    conn.close()
    return render_template('resources.html', resources=items, topics=topics, current_topic=topic)

# ── Admin Resource Library ─────────────────────────────────────────────────────
RESOURCE_TYPES = [
    'Tutorial', 'Book', 'Website', 'YouTube', 'PDF / Document',
    'Online Course', 'Blog / Article', 'GitHub Repository',
    'Practice Platform', 'Podcast', 'Newsletter', 'Tool / Software'
]

RESOURCE_TOPICS = [
    'DSA', 'Networking', 'DBMS', 'Software Engineering', 'Web Development',
    'Mobile Development', 'Machine Learning / AI', 'Cloud & DevOps',
    'Cybersecurity', 'System Design', 'Operating Systems',
    'Computer Architecture', 'Mathematics', 'Career & Interview', 'Other'
]

@app.route('/admin/resources')
@admin_required
def admin_resources():
    conn  = get_db()
    items = conn.execute("SELECT * FROM resources ORDER BY topic, resource_type").fetchall()
    conn.close()
    return render_template('admin_resources.html', resources=items)

@app.route('/admin/resource/add', methods=['GET', 'POST'])
@admin_required
def resource_add():
    if request.method == 'POST':
        conn = get_db()
        conn.execute(
            "INSERT INTO resources (title, description, url, resource_type, topic, emoji) VALUES (?,?,?,?,?,?)",
            (request.form['title'], request.form['description'],
             request.form['url'], request.form['resource_type'],
             request.form['topic'], request.form.get('emoji', ''))
        )
        conn.commit(); conn.close()
        flash('Resource added!', 'success')
        return redirect(url_for('admin_resources'))
    return render_template('resource_form.html', resource=None, action='Add',
                           resource_types=RESOURCE_TYPES, resource_topics=RESOURCE_TOPICS)

@app.route('/admin/resource/edit/<int:resource_id>', methods=['GET', 'POST'])
@admin_required
def resource_edit(resource_id):
    conn     = get_db()
    resource = conn.execute("SELECT * FROM resources WHERE resource_id=?", (resource_id,)).fetchone()
    if request.method == 'POST':
        conn.execute(
            "UPDATE resources SET title=?, description=?, url=?, resource_type=?, topic=?, emoji=? WHERE resource_id=?",
            (request.form['title'], request.form['description'],
             request.form['url'], request.form['resource_type'],
             request.form['topic'], request.form.get('emoji', ''), resource_id)
        )
        conn.commit(); conn.close()
        flash('Resource updated!', 'success')
        return redirect(url_for('admin_resources'))
    conn.close()
    return render_template('resource_form.html', resource=resource, action='Edit',
                           resource_types=RESOURCE_TYPES, resource_topics=RESOURCE_TOPICS)

@app.route('/admin/resource/delete/<int:resource_id>')
@admin_required
def resource_delete(resource_id):
    conn = get_db()
    conn.execute("DELETE FROM resources WHERE resource_id=?", (resource_id,))
    conn.commit(); conn.close()
    flash('Resource deleted.', 'warning')
    return redirect(url_for('admin_resources'))


# ─── Feature #9: Trending Leaderboard ────────────────────────────────────────

@app.route('/trending')
@login_required
def trending():
    conn = get_db()
    trending = conn.execute('''
        SELECT matched_faq as question, category, COUNT(*) as count
        FROM chat_history WHERE matched_faq IS NOT NULL
        GROUP BY matched_faq ORDER BY count DESC LIMIT 20
    ''').fetchall()
    conn.close()
    return render_template('trending.html', trending=trending)


# ─── Feature #10: Career Roadmap ──────────────────────────────────────────────

@app.route('/career')
@login_required
def career():
    conn  = get_db()
    paths = conn.execute("SELECT * FROM career_paths").fetchall()
    conn.close()
    return render_template('career.html', paths=paths)

# ── Admin Career Roadmap ───────────────────────────────────────────────────────
CAREER_SKILLS = [
    'Python', 'Java', 'JavaScript', 'TypeScript', 'C++', 'C#', 'Go', 'Rust', 'Kotlin', 'Swift',
    'PHP', 'Ruby', 'Dart', 'Scala', 'R', 'MATLAB', 'Bash / Shell Scripting',
    'HTML', 'CSS', 'SQL', 'NoSQL', 'REST APIs', 'GraphQL', 'gRPC',
    'Data Structures & Algorithms', 'System Design', 'Object-Oriented Programming',
    'Functional Programming', 'Design Patterns', 'Microservices Architecture',
    'Networking Fundamentals', 'Operating Systems', 'Linux / Unix',
    'Cloud Computing (AWS/GCP/Azure)', 'Docker', 'Kubernetes',
    'Machine Learning', 'Deep Learning', 'Natural Language Processing',
    'Computer Vision', 'Statistics & Probability', 'Linear Algebra',
    'Cryptography', 'Ethical Hacking', 'Penetration Testing', 'Security Audits',
    'Agile / Scrum', 'CI/CD', 'DevOps Practices', 'Test-Driven Development',
    'UI/UX Design', 'Figma / Prototyping', 'Mobile Development', 'Cross-Platform Dev',
    'Database Design', 'Data Modeling', 'Big Data', 'Data Pipelines',
    'Blockchain', 'IoT', 'Embedded Systems', 'Computer Architecture',
    'Version Control (Git)', 'Code Review', 'Technical Writing', 'Problem Solving',
]

CAREER_TOOLS = [
    'Django', 'Flask', 'FastAPI', 'Spring Boot', 'Express.js', 'NestJS', 'Laravel',
    'React', 'Vue.js', 'Angular', 'Next.js', 'Nuxt.js', 'Svelte', 'Tailwind CSS',
    'Flutter', 'React Native', 'Android Studio', 'Xcode', 'Firebase',
    'PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'SQLite', 'Cassandra', 'Elasticsearch',
    'TensorFlow', 'PyTorch', 'Scikit-learn', 'Pandas', 'NumPy', 'Jupyter Notebook',
    'Apache Spark', 'Kafka', 'Airflow', 'dbt',
    'Docker', 'Kubernetes', 'Terraform', 'Ansible', 'Helm',
    'Jenkins', 'GitHub Actions', 'GitLab CI', 'CircleCI', 'ArgoCD',
    'AWS (EC2, S3, Lambda)', 'Google Cloud Platform', 'Microsoft Azure',
    'Nginx', 'Apache', 'Caddy', 'HAProxy', 'RabbitMQ',
    'Kali Linux', 'Wireshark', 'Metasploit', 'Burp Suite', 'Nmap',
    'Figma', 'Adobe XD', 'Sketch', 'InVision',
    'Git', 'GitHub', 'GitLab', 'Bitbucket',
    'VS Code', 'IntelliJ IDEA', 'PyCharm', 'Eclipse', 'Vim / Neovim',
    'Postman', 'Insomnia', 'Swagger', 'GraphQL Playground',
    'Prometheus', 'Grafana', 'Datadog', 'Sentry', 'ELK Stack',
    'WordPress', 'Shopify', 'Magento', 'Strapi', 'Contentful',
]

@app.route('/admin/careers')
@admin_required
def admin_careers():
    conn  = get_db()
    paths = conn.execute("SELECT * FROM career_paths").fetchall()
    conn.close()
    return render_template('admin_careers.html', paths=paths)

@app.route('/admin/career/add', methods=['GET', 'POST'])
@admin_required
def career_add():
    if request.method == 'POST':
        conn = get_db()
        logo_filename = None
        file = request.files.get('logo')
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext in {'png', 'jpg', 'jpeg'}:
                logo_filename = secure_filename(
                    f"career_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
                )
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], logo_filename))
        skills_list = request.form.getlist('skills')
        tools_list  = request.form.getlist('tools')
        conn.execute(
            "INSERT INTO career_paths (title, description, skills, tools, icon, logo) VALUES (?,?,?,?,?,?)",
            (request.form['title'], request.form['description'],
             ', '.join(skills_list), ', '.join(tools_list),
             request.form.get('icon', 'bi-briefcase'), logo_filename)
        )
        conn.commit(); conn.close()
        flash('Career path added!', 'success')
        return redirect(url_for('admin_careers'))
    return render_template('career_form.html', path=None, action='Add',
                           career_skills=CAREER_SKILLS, career_tools=CAREER_TOOLS)

@app.route('/admin/career/edit/<int:path_id>', methods=['GET', 'POST'])
@admin_required
def career_edit(path_id):
    conn = get_db()
    path = conn.execute("SELECT * FROM career_paths WHERE path_id=?", (path_id,)).fetchone()
    if request.method == 'POST':
        logo_filename = path['logo']
        file = request.files.get('logo')
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext in {'png', 'jpg', 'jpeg'}:
                logo_filename = secure_filename(
                    f"career_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
                )
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], logo_filename))
        skills_list = request.form.getlist('skills')
        tools_list  = request.form.getlist('tools')
        conn.execute(
            "UPDATE career_paths SET title=?, description=?, skills=?, tools=?, icon=?, logo=? WHERE path_id=?",
            (request.form['title'], request.form['description'],
             ', '.join(skills_list), ', '.join(tools_list),
             request.form.get('icon', 'bi-briefcase'), logo_filename, path_id)
        )
        conn.commit(); conn.close()
        flash('Career path updated!', 'success')
        return redirect(url_for('admin_careers'))
    conn.close()
    return render_template('career_form.html', path=path, action='Edit',
                           career_skills=CAREER_SKILLS, career_tools=CAREER_TOOLS)

@app.route('/admin/career/delete/<int:path_id>')
@admin_required
def career_delete(path_id):
    conn = get_db()
    conn.execute("DELETE FROM career_paths WHERE path_id=?", (path_id,))
    conn.commit(); conn.close()
    flash('Career path deleted.', 'warning')
    return redirect(url_for('admin_careers'))


# ─── Feature #11: Events Board ────────────────────────────────────────────────

@app.route('/events')
@login_required
def events():
    etype = request.args.get('type', '')
    conn  = get_db()
    if etype:
        evts = conn.execute("SELECT * FROM events WHERE event_type=? ORDER BY event_date", (etype,)).fetchall()
    else:
        evts = conn.execute("SELECT * FROM events ORDER BY event_date").fetchall()
    types = conn.execute("SELECT DISTINCT event_type FROM events ORDER BY event_type").fetchall()
    conn.close()
    return render_template('events.html', events=evts, types=types, current_type=etype)

# ── Admin Events & Hackathons ──────────────────────────────────────────────────
EVENT_TYPES = ['Contest', 'Hackathon', 'Tech Event']

@app.route('/admin/events')
@admin_required
def admin_events():
    conn  = get_db()
    evts  = conn.execute("SELECT * FROM events ORDER BY event_date DESC").fetchall()
    conn.close()
    return render_template('admin_events.html', events=evts)

@app.route('/admin/event/add', methods=['GET', 'POST'])
@admin_required
def event_add():
    if request.method == 'POST':
        conn = get_db()
        platform = request.form.get('platform', 'Online')
        location = request.form.get('location', '').strip()
        # If Online, override location
        if platform == 'Online':
            location = 'Online'
        conn.execute(
            "INSERT INTO events (title, description, event_date, event_type, link, location, platform) VALUES (?,?,?,?,?,?,?)",
            (request.form['title'], request.form.get('description',''),
             request.form['event_date'], request.form['event_type'],
             request.form.get('link',''), location, platform)
        )
        conn.commit(); conn.close()
        flash('Event added!', 'success')
        return redirect(url_for('admin_events'))
    return render_template('event_form.html', event=None, action='Add', event_types=EVENT_TYPES)

@app.route('/admin/event/edit/<int:event_id>', methods=['GET', 'POST'])
@admin_required
def event_edit(event_id):
    conn  = get_db()
    event = conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
    if request.method == 'POST':
        platform = request.form.get('platform', 'Online')
        location = request.form.get('location', '').strip()
        if platform == 'Online':
            location = 'Online'
        conn.execute(
            "UPDATE events SET title=?, description=?, event_date=?, event_type=?, link=?, location=?, platform=? WHERE event_id=?",
            (request.form['title'], request.form.get('description',''),
             request.form['event_date'], request.form['event_type'],
             request.form.get('link',''), location, platform, event_id)
        )
        conn.commit(); conn.close()
        flash('Event updated!', 'success')
        return redirect(url_for('admin_events'))
    conn.close()
    return render_template('event_form.html', event=event, action='Edit', event_types=EVENT_TYPES)

@app.route('/admin/event/delete/<int:event_id>')
@admin_required
def event_delete(event_id):
    conn = get_db()
    conn.execute("DELETE FROM events WHERE event_id=?", (event_id,))
    conn.commit(); conn.close()
    flash('Event deleted.', 'warning')
    return redirect(url_for('admin_events'))


# ─── Feature #12: Study Material Download ─────────────────────────────────────

@app.route('/materials')
@login_required
def materials():
    category = request.args.get('category', '')
    conn     = get_db()
    if category:
        items = conn.execute("SELECT * FROM study_materials WHERE category=? ORDER BY uploaded_at DESC", (category,)).fetchall()
    else:
        items = conn.execute("SELECT * FROM study_materials ORDER BY uploaded_at DESC").fetchall()
    categories = conn.execute("SELECT DISTINCT category FROM study_materials ORDER BY category").fetchall()
    conn.close()
    return render_template('materials.html', materials=items, categories=categories, current_category=category)

@app.route('/materials/download/<int:material_id>')
@login_required
def material_download(material_id):
    conn     = get_db()
    material = conn.execute("SELECT * FROM study_materials WHERE material_id=?", (material_id,)).fetchone()
    conn.close()
    if not material:
        flash('File not found.', 'danger')
        return redirect(url_for('materials'))
    upload_dir = os.path.join(app.root_path, 'static', 'uploads')
    return send_from_directory(upload_dir, material['filename'], as_attachment=True)


# ─── Feature #13: Campus Info Hub ────────────────────────────────────────────

@app.route('/campus')
@login_required
def campus():
    conn         = get_db()
    clubs        = conn.execute("SELECT * FROM clubs ORDER BY category, name").fetchall()
    scholarships = conn.execute("SELECT * FROM scholarships ORDER BY deadline").fetchall()
    internships  = conn.execute("SELECT * FROM internships ORDER BY deadline").fetchall()
    conn.close()
    return render_template('campus.html', clubs=clubs, scholarships=scholarships, internships=internships)

# ── Admin Campus Info Hub ──────────────────────────────────────────────────────
CLUB_CATEGORIES = [
    'Technical', 'Cultural', 'Business', 'Sports', 'Social & Volunteer',
    'Science & Research', 'Arts & Media', 'Gaming & E-Sports',
    'Language & Literature', 'Environment', 'Health & Wellness', 'Other'
]

@app.route('/admin/campus')
@admin_required
def admin_campus():
    conn         = get_db()
    clubs        = conn.execute("SELECT * FROM clubs ORDER BY category, name").fetchall()
    scholarships = conn.execute("SELECT * FROM scholarships ORDER BY deadline").fetchall()
    internships  = conn.execute("SELECT * FROM internships ORDER BY deadline").fetchall()
    conn.close()
    return render_template('admin_campus.html',
                           clubs=clubs, scholarships=scholarships, internships=internships)

# ── Clubs ──────────────────────────────────────────────────────────────────────
@app.route('/admin/club/add', methods=['GET', 'POST'])
@admin_required
def club_add():
    if request.method == 'POST':
        conn = get_db()
        logo_filename = None
        file = request.files.get('logo')
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext in {'png', 'jpg', 'jpeg'}:
                logo_filename = secure_filename(
                    f"club_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
                )
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], logo_filename))
        conn.execute(
            "INSERT INTO clubs (name, description, contact, category, logo, motto, link) VALUES (?,?,?,?,?,?,?)",
            (request.form['name'], request.form.get('description',''),
             request.form.get('contact',''), request.form.get('category',''),
             logo_filename, request.form.get('motto',''), request.form.get('link',''))
        )
        conn.commit(); conn.close()
        flash('Club added!', 'success')
        return redirect(url_for('admin_campus'))
    return render_template('club_form.html', club=None, action='Add', club_categories=CLUB_CATEGORIES)

@app.route('/admin/club/edit/<int:club_id>', methods=['GET', 'POST'])
@admin_required
def club_edit(club_id):
    conn = get_db()
    club = conn.execute("SELECT * FROM clubs WHERE club_id=?", (club_id,)).fetchone()
    if request.method == 'POST':
        logo_filename = club['logo']
        file = request.files.get('logo')
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext in {'png', 'jpg', 'jpeg'}:
                logo_filename = secure_filename(
                    f"club_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
                )
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], logo_filename))
        conn.execute(
            "UPDATE clubs SET name=?, description=?, contact=?, category=?, logo=?, motto=?, link=? WHERE club_id=?",
            (request.form['name'], request.form.get('description',''),
             request.form.get('contact',''), request.form.get('category',''),
             logo_filename, request.form.get('motto',''), request.form.get('link',''), club_id)
        )
        conn.commit(); conn.close()
        flash('Club updated!', 'success')
        return redirect(url_for('admin_campus'))
    conn.close()
    return render_template('club_form.html', club=club, action='Edit', club_categories=CLUB_CATEGORIES)

@app.route('/admin/club/delete/<int:club_id>')
@admin_required
def club_delete(club_id):
    conn = get_db()
    conn.execute("DELETE FROM clubs WHERE club_id=?", (club_id,))
    conn.commit(); conn.close()
    flash('Club deleted.', 'warning')
    return redirect(url_for('admin_campus'))

# ── Scholarships ───────────────────────────────────────────────────────────────
@app.route('/admin/scholarship/add', methods=['GET', 'POST'])
@admin_required
def scholarship_add():
    if request.method == 'POST':
        conn = get_db()
        conn.execute(
            "INSERT INTO scholarships (title, description, deadline, link) VALUES (?,?,?,?)",
            (request.form['title'], request.form.get('description',''),
             request.form.get('deadline',''), request.form.get('link',''))
        )
        conn.commit(); conn.close()
        flash('Scholarship added!', 'success')
        return redirect(url_for('admin_campus'))
    return render_template('scholarship_form.html', scholarship=None, action='Add')

@app.route('/admin/scholarship/edit/<int:scholarship_id>', methods=['GET', 'POST'])
@admin_required
def scholarship_edit(scholarship_id):
    conn = get_db()
    scholarship = conn.execute("SELECT * FROM scholarships WHERE scholarship_id=?", (scholarship_id,)).fetchone()
    if request.method == 'POST':
        conn.execute(
            "UPDATE scholarships SET title=?, description=?, deadline=?, link=? WHERE scholarship_id=?",
            (request.form['title'], request.form.get('description',''),
             request.form.get('deadline',''), request.form.get('link',''), scholarship_id)
        )
        conn.commit(); conn.close()
        flash('Scholarship updated!', 'success')
        return redirect(url_for('admin_campus'))
    conn.close()
    return render_template('scholarship_form.html', scholarship=scholarship, action='Edit')

@app.route('/admin/scholarship/delete/<int:scholarship_id>')
@admin_required
def scholarship_delete(scholarship_id):
    conn = get_db()
    conn.execute("DELETE FROM scholarships WHERE scholarship_id=?", (scholarship_id,))
    conn.commit(); conn.close()
    flash('Scholarship deleted.', 'warning')
    return redirect(url_for('admin_campus'))

# ── Internships ────────────────────────────────────────────────────────────────
@app.route('/admin/internship/add', methods=['GET', 'POST'])
@admin_required
def internship_add():
    if request.method == 'POST':
        conn = get_db()
        conn.execute(
            "INSERT INTO internships (title, company, description, deadline, link) VALUES (?,?,?,?,?)",
            (request.form['title'], request.form.get('company',''),
             request.form.get('description',''), request.form.get('deadline',''),
             request.form.get('link',''))
        )
        conn.commit(); conn.close()
        flash('Internship added!', 'success')
        return redirect(url_for('admin_campus'))
    return render_template('internship_form.html', internship=None, action='Add')

@app.route('/admin/internship/edit/<int:internship_id>', methods=['GET', 'POST'])
@admin_required
def internship_edit(internship_id):
    conn = get_db()
    internship = conn.execute("SELECT * FROM internships WHERE internship_id=?", (internship_id,)).fetchone()
    if request.method == 'POST':
        conn.execute(
            "UPDATE internships SET title=?, company=?, description=?, deadline=?, link=? WHERE internship_id=?",
            (request.form['title'], request.form.get('company',''),
             request.form.get('description',''), request.form.get('deadline',''),
             request.form.get('link',''), internship_id)
        )
        conn.commit(); conn.close()
        flash('Internship updated!', 'success')
        return redirect(url_for('admin_campus'))
    conn.close()
    return render_template('internship_form.html', internship=internship, action='Edit')

@app.route('/admin/internship/delete/<int:internship_id>')
@admin_required
def internship_delete(internship_id):
    conn = get_db()
    conn.execute("DELETE FROM internships WHERE internship_id=?", (internship_id,))
    conn.commit(); conn.close()
    flash('Internship deleted.', 'warning')
    return redirect(url_for('admin_campus'))


# ─── Feature #14 & #20: Notices (with search/date filter) ────────────────────

@app.route('/notices')
@login_required
def notices():
    search     = request.args.get('search', '')
    date_from  = request.args.get('date_from', '')
    date_to    = request.args.get('date_to', '')
    conn       = get_db()
    query      = "SELECT * FROM notices WHERE 1=1"
    params     = []
    if search:
        query  += " AND (title LIKE ? OR description LIKE ?)"
        params += [f'%{search}%', f'%{search}%']
    if date_from:
        query  += " AND publish_date >= ?"
        params.append(date_from)
    if date_to:
        query  += " AND publish_date <= ?"
        params.append(date_to)
    all_notices = conn.execute(query + " ORDER BY publish_date DESC", params).fetchall()
    conn.close()
    return render_template('notices.html', notices=all_notices,
                           search=search, date_from=date_from, date_to=date_to)


# ─── Academic Info ────────────────────────────────────────────────────────────

@app.route('/academic')
@login_required
def academic():
    conn     = get_db()
    courses  = conn.execute("SELECT * FROM courses ORDER BY code").fetchall()
    midterms = conn.execute("SELECT * FROM exam_routine WHERE exam_type='Midterm' ORDER BY exam_date").fetchall()
    finals   = conn.execute("SELECT * FROM exam_routine WHERE exam_type='Final' ORDER BY exam_date").fetchall()
    marks    = conn.execute("SELECT * FROM mark_distribution").fetchall()
    labs     = conn.execute("SELECT * FROM lab_schedule ORDER BY day").fetchall()
    conn.close()
    return render_template('academic.html', courses=courses, midterms=midterms,
                           finals=finals, marks=marks, labs=labs)


# ─── Admin Routes ─────────────────────────────────────────────────────────────

# Feature #15: Analytics Dashboard
@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    total_faqs       = conn.execute("SELECT COUNT(*) FROM faqs").fetchone()[0]
    total_queries    = conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0]
    unmatched_count  = conn.execute("SELECT COUNT(*) FROM unmatched_queries WHERE converted=0").fetchone()[0]
    pending_feedback = conn.execute("SELECT COUNT(*) FROM feedback WHERE status='Pending'").fetchone()[0]
    total_users      = conn.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0]

    top_questions = conn.execute('''
        SELECT matched_faq, COUNT(*) as cnt FROM chat_history
        WHERE matched_faq IS NOT NULL
        GROUP BY matched_faq ORDER BY cnt DESC LIMIT 5
    ''').fetchall()

    avg_ratings = conn.execute('''
        SELECT f.question,
               SUM(CASE WHEN ch.rating='helpful' THEN 1 ELSE 0 END) as helpful,
               SUM(CASE WHEN ch.rating='not_helpful' THEN 1 ELSE 0 END) as not_helpful
        FROM faqs f LEFT JOIN chat_history ch ON ch.matched_faq = f.question
        WHERE ch.rating IS NOT NULL
        GROUP BY f.faq_id ORDER BY helpful DESC LIMIT 5
    ''').fetchall()

    conn.close()
    return render_template('admin_dashboard.html',
                           total_faqs=total_faqs, total_queries=total_queries,
                           unmatched_count=unmatched_count, pending_feedback=pending_feedback,
                           total_users=total_users, top_questions=top_questions,
                           avg_ratings=avg_ratings)


# Feature #16: Unanswered Query Review & Conversion
@app.route('/admin/unmatched')
@admin_required
def admin_unmatched():
    conn = get_db()
    queries = conn.execute('''
        SELECT uq.*, u.name as student_name
        FROM unmatched_queries uq LEFT JOIN users u ON uq.user_id = u.user_id
        WHERE uq.converted=0 ORDER BY uq.timestamp DESC
    ''').fetchall()
    conn.close()
    return render_template('admin_unmatched.html', queries=queries)

@app.route('/admin/unmatched/convert/<int:query_id>', methods=['GET', 'POST'])
@admin_required
def admin_convert_query(query_id):
    conn  = get_db()
    query = conn.execute("SELECT * FROM unmatched_queries WHERE query_id=?", (query_id,)).fetchone()
    if request.method == 'POST':
        conn.execute(
            "INSERT INTO faqs (question, answer, keywords, category) VALUES (?,?,?,?)",
            (request.form['question'], request.form['answer'],
             request.form['keywords'], request.form['category'])
        )
        conn.execute("UPDATE unmatched_queries SET converted=1 WHERE query_id=?", (query_id,))
        conn.commit(); conn.close()
        flash('Query converted to FAQ!', 'success')
        return redirect(url_for('admin_unmatched'))
    conn.close()
    return render_template('admin_convert.html', query=query)


# Feature #17: Admin FAQ Manager (CRUD)
@app.route('/admin/faqs')
@admin_required
def admin_faqs():
    conn = get_db()
    faqs = conn.execute("SELECT * FROM faqs ORDER BY category, faq_id").fetchall()
    conn.close()
    return render_template('admin_faqs.html', faqs=faqs)

@app.route('/admin/faq/add', methods=['GET', 'POST'])
@admin_required
def faq_add():
    if request.method == 'POST':
        conn = get_db()
        conn.execute(
            "INSERT INTO faqs (question, answer, keywords, category) VALUES (?,?,?,?)",
            (request.form['question'], request.form['answer'],
             request.form['keywords'], request.form['category'])
        )
        conn.commit(); conn.close()
        flash('FAQ added successfully!', 'success')
        return redirect(url_for('admin_faqs'))
    return render_template('faq_form.html', faq=None, action='Add')

@app.route('/admin/faq/edit/<int:faq_id>', methods=['GET', 'POST'])
@admin_required
def faq_edit(faq_id):
    conn = get_db()
    faq  = conn.execute("SELECT * FROM faqs WHERE faq_id=?", (faq_id,)).fetchone()
    if request.method == 'POST':
        conn.execute(
            "UPDATE faqs SET question=?, answer=?, keywords=?, category=? WHERE faq_id=?",
            (request.form['question'], request.form['answer'],
             request.form['keywords'], request.form['category'], faq_id)
        )
        conn.commit(); conn.close()
        flash('FAQ updated!', 'success')
        return redirect(url_for('admin_faqs'))
    conn.close()
    return render_template('faq_form.html', faq=faq, action='Edit')

@app.route('/admin/faq/delete/<int:faq_id>')
@admin_required
def faq_delete(faq_id):
    conn = get_db()
    conn.execute("DELETE FROM faqs WHERE faq_id=?", (faq_id,))
    conn.commit(); conn.close()
    flash('FAQ deleted.', 'warning')
    return redirect(url_for('admin_faqs'))


# Feature #18: Admin Chat Log Viewer
@app.route('/admin/chatlogs')
@admin_required
def admin_chatlogs():
    student    = request.args.get('student', '')
    date_filter = request.args.get('date', '')
    conn        = get_db()
    query       = "SELECT ch.*, u.name as student_name FROM chat_history ch LEFT JOIN users u ON ch.user_id=u.user_id WHERE 1=1"
    params      = []
    if student:
        query  += " AND u.name LIKE ?"
        params.append(f'%{student}%')
    if date_filter:
        query  += " AND ch.timestamp LIKE ?"
        params.append(f'{date_filter}%')
    logs     = conn.execute(query + " ORDER BY ch.timestamp DESC LIMIT 200", params).fetchall()
    students = conn.execute("SELECT DISTINCT name FROM users WHERE role='student' ORDER BY name").fetchall()
    conn.close()
    return render_template('admin_chatlogs.html', logs=logs, students=students,
                           student_filter=student, date_filter=date_filter)


# Feature #19: Admin Feedback Manager
@app.route('/admin/feedback')
@admin_required
def admin_feedback():
    conn     = get_db()
    feedbacks = conn.execute("SELECT * FROM feedback ORDER BY timestamp DESC").fetchall()
    conn.close()
    return render_template('admin_feedback.html', feedbacks=feedbacks)

@app.route('/admin/feedback/status/<int:feedback_id>/<status>')
@admin_required
def admin_feedback_status(feedback_id, status):
    if status not in ('Resolved', 'Pending'):
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin_feedback'))
    conn = get_db()
    conn.execute("UPDATE feedback SET status=? WHERE feedback_id=?", (status, feedback_id))
    conn.commit(); conn.close()
    flash(f'Feedback marked as {status}.', 'success')
    return redirect(url_for('admin_feedback'))


# Admin Notice CRUD
@app.route('/admin/notices')
@admin_required
def admin_notices():
    conn    = get_db()
    notices = conn.execute("SELECT * FROM notices ORDER BY publish_date DESC").fetchall()
    conn.close()
    return render_template('admin_notices.html', notices=notices)

@app.route('/admin/notice/add', methods=['GET', 'POST'])
@admin_required
def notice_add():
    if request.method == 'POST':
        conn = get_db()
        attachment_filename = None
        file = request.files.get('attachment')
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext in {'pdf', 'jpg', 'jpeg', 'png'}:
                attachment_filename = secure_filename(
                    f"notice_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
                )
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], attachment_filename))
        conn.execute(
            "INSERT INTO notices (title, description, publish_date, attachment) VALUES (?,?,?,?)",
            (request.form['title'], request.form['description'],
             request.form['publish_date'], attachment_filename)
        )
        conn.commit(); conn.close()
        flash('Notice posted!', 'success')
        return redirect(url_for('admin_notices'))
    return render_template('notice_form.html', notice=None, action='Add')

@app.route('/admin/notice/edit/<int:notice_id>', methods=['GET', 'POST'])
@admin_required
def notice_edit(notice_id):
    conn   = get_db()
    notice = conn.execute("SELECT * FROM notices WHERE notice_id=?", (notice_id,)).fetchone()
    if request.method == 'POST':
        attachment_filename = notice['attachment']  # keep existing by default
        file = request.files.get('attachment')
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext in {'pdf', 'jpg', 'jpeg', 'png'}:
                attachment_filename = secure_filename(
                    f"notice_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
                )
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], attachment_filename))
        conn.execute(
            "UPDATE notices SET title=?, description=?, publish_date=?, attachment=? WHERE notice_id=?",
            (request.form['title'], request.form['description'],
             request.form['publish_date'], attachment_filename, notice_id)
        )
        conn.commit(); conn.close()
        flash('Notice updated!', 'success')
        return redirect(url_for('admin_notices'))
    conn.close()
    return render_template('notice_form.html', notice=notice, action='Edit')

@app.route('/admin/notice/delete/<int:notice_id>')
@admin_required
def notice_delete(notice_id):
    conn = get_db()
    conn.execute("DELETE FROM notices WHERE notice_id=?", (notice_id,))
    conn.commit(); conn.close()
    flash('Notice deleted.', 'warning')
    return redirect(url_for('admin_notices'))

@app.route('/notices/download/<int:notice_id>')
def notice_download(notice_id):
    conn   = get_db()
    notice = conn.execute("SELECT * FROM notices WHERE notice_id=?", (notice_id,)).fetchone()
    conn.close()
    if not notice or not notice['attachment']:
        flash('No attachment found for this notice.', 'danger')
        return redirect(url_for('notices'))
    upload_dir = os.path.join(app.root_path, 'static', 'uploads')
    return send_from_directory(upload_dir, notice['attachment'], as_attachment=True)


# Admin Study Material Upload
@app.route('/admin/materials')
@admin_required
def admin_materials():
    conn  = get_db()
    items = conn.execute("SELECT * FROM study_materials ORDER BY uploaded_at DESC").fetchall()
    conn.close()
    return render_template('admin_materials.html', materials=items)

@app.route('/admin/material/upload', methods=['GET', 'POST'])
@admin_required
def material_upload():
    if request.method == 'POST':
        title    = request.form.get('title', '').strip()
        desc     = request.form.get('description', '').strip()
        category = request.form.get('category', '').strip()
        file     = request.files.get('file')
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext in ALLOWED_EXT:
                filename  = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                conn      = get_db()
                conn.execute(
                    "INSERT INTO study_materials (title, description, filename, category, uploaded_at) VALUES (?,?,?,?,?)",
                    (title, desc, filename, category, timestamp)
                )
                conn.commit(); conn.close()
                flash('Material uploaded!', 'success')
                return redirect(url_for('admin_materials'))
        flash('Invalid file.', 'danger')
    return render_template('admin_material_upload.html')

@app.route('/admin/material/delete/<int:material_id>')
@admin_required
def material_delete(material_id):
    conn = get_db()
    mat  = conn.execute("SELECT * FROM study_materials WHERE material_id=?", (material_id,)).fetchone()
    if mat:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], mat['filename'])
        if os.path.exists(filepath):
            os.remove(filepath)
        conn.execute("DELETE FROM study_materials WHERE material_id=?", (material_id,))
        conn.commit()
    conn.close()
    flash('Material deleted.', 'warning')
    return redirect(url_for('admin_materials'))


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
