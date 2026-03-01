from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import random
import os
import base64
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = 'library_secret_key_2024'
DB_PATH = 'library.db'

# ── Gmail SMTP Config (settings DB থেকে নেওয়া হবে) ──
def send_reset_email(to_email, student_name, reset_token):
    s = get_settings()
    smtp_email    = s.get('smtp_email', '')
    smtp_password = s.get('smtp_password', '')
    if not smtp_email or not smtp_password:
        return False, 'SMTP config করা নেই।'

    # Actual server URL ব্যবহার করি
    from flask import request as freq
    try:
        base_url = freq.host_url.rstrip('/')
    except RuntimeError:
        base_url = 'http://127.0.0.1:5000'
    reset_url = f"{base_url}/student/reset-password/{reset_token}"
    s2   = get_settings()
    lib  = s2.get('library_name', 'Library')
    body = f"""
    <!DOCTYPE html>
    <html><body style='margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif'>
    <table width='100%' cellpadding='0' cellspacing='0'>
      <tr><td align='center' style='padding:40px 20px'>
        <table width='500' cellpadding='0' cellspacing='0' style='max-width:500px;width:100%'>

          <!-- Header -->
          <tr><td style='background:#0f172a;border-radius:16px 16px 0 0;padding:30px;text-align:center'>
            <div style='font-size:2rem;margin-bottom:8px'>📚</div>
            <div style='font-family:Georgia,serif;font-size:1.4rem;font-weight:bold;color:#fff'>{lib}</div>
            <div style='color:#f59e0b;font-size:.75rem;letter-spacing:2px;text-transform:uppercase;margin-top:4px'>Library System</div>
          </td></tr>

          <!-- Body -->
          <tr><td style='background:#fff;padding:36px 40px'>
            <p style='color:#0f172a;font-size:1rem;margin-top:0'>প্রিয় <strong>{student_name}</strong>,</p>
            <p style='color:#475569;line-height:1.7'>আমরা আপনার Library account এর <strong>Password Reset</strong> এর একটি request পেয়েছি।
            নিচের বাটনে ক্লিক করে নতুন password সেট করুন:</p>

            <div style='text-align:center;margin:32px 0'>
              <a href='{reset_url}'
                 style='display:inline-block;background:#f59e0b;color:#0f172a;padding:14px 36px;
                        border-radius:10px;text-decoration:none;font-weight:bold;font-size:1rem'>
                🔑 Password Reset করুন
              </a>
            </div>

            <div style='background:#fef9ec;border-left:4px solid #f59e0b;padding:14px 16px;border-radius:0 8px 8px 0;margin:20px 0'>
              <p style='margin:0;color:#78350f;font-size:.85rem'>
                ⏰ এই link টি <strong>১ ঘণ্টা</strong> পর্যন্ত valid।<br>
                মেয়াদ শেষ হলে আবার Forgot Password করুন।
              </p>
            </div>

            <p style='color:#94a3b8;font-size:.8rem;margin-bottom:0'>
              আপনি যদি এই request না করে থাকেন, এই email টি ignore করুন।
              আপনার account সুরক্ষিত আছে।
            </p>
          </td></tr>

          <!-- Footer -->
          <tr><td style='background:#f8fafc;border-radius:0 0 16px 16px;padding:20px 40px;text-align:center'>
            <p style='margin:0;color:#94a3b8;font-size:.75rem'>
              এই email টি {lib} Library System থেকে পাঠানো হয়েছে।<br>
              Reply করবেন না — এটি একটি automated email।
            </p>
          </td></tr>

        </table>
      </td></tr>
    </table>
    </body></html>
    """
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'Password Reset — Library System'
        msg['From']    = smtp_email
        msg['To']      = to_email
        msg.attach(MIMEText(body, 'html'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to_email, msg.as_string())
        return True, 'Email পাঠানো হয়েছে।'
    except Exception as e:
        return False, str(e)

# ════════════════════════════════════════════
#  Decorators
# ════════════════════════════════════════════

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            flash('এই পেজটি দেখতে লগইন করুন।', 'info')
            return redirect(url_for('login', next=request.path))
        if not session.get('is_admin'):
            flash('এই কাজটি করার অনুমতি আপনার নেই।', 'error')
            return redirect(url_for('books'))
        return f(*args, **kwargs)
    return decorated

def super_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            flash('এই পেজটি দেখতে লগইন করুন।', 'info')
            return redirect(url_for('login', next=request.path))
        if not session.get('is_super'):
            flash('এই পেজটি শুধুমাত্র Super Admin এর জন্য।', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('student_logged_in'):
            flash('বই request করতে আগে Student Login করুন।', 'info')
            return redirect(url_for('student_login', next=request.path))
        return f(*args, **kwargs)
    return decorated

# ════════════════════════════════════════════
#  DB
# ════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, author TEXT NOT NULL, isbn TEXT UNIQUE,
        genre TEXT, total_copies INTEGER DEFAULT 1, available_copies INTEGER DEFAULT 1,
        added_date TEXT DEFAULT CURRENT_TIMESTAMP, cover_color TEXT DEFAULT '#4A90D9'
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, phone TEXT,
        join_date TEXT DEFAULT CURRENT_TIMESTAMP, active INTEGER DEFAULT 1
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS borrowings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER, member_id INTEGER,
        borrow_date TEXT DEFAULT CURRENT_TIMESTAMP, due_date TEXT,
        return_date TEXT, status TEXT DEFAULT 'borrowed',
        FOREIGN KEY(book_id) REFERENCES books(id),
        FOREIGN KEY(member_id) REFERENCES members(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS book_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
        student_note TEXT,
        request_date TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'pending', admin_note TEXT, resolved_date TEXT,
        pdf_filename TEXT,
        FOREIGN KEY(book_id) REFERENCES books(id),
        FOREIGN KEY(student_id) REFERENCES students(id)
    )''')

    # ── Student accounts table ──
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        password TEXT NOT NULL,
        reg_date TEXT DEFAULT CURRENT_TIMESTAMP,
        active INTEGER DEFAULT 1
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        token TEXT UNIQUE NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        used INTEGER DEFAULT 0,
        FOREIGN KEY(student_id) REFERENCES students(id)
    )''')

    defaults = [
        ('library_name',    'BiblioTech'),
        ('library_tagline', 'Library System'),
        ('library_logo',    '📚'),
        ('library_footer',  'সিটি পাবলিক লাইব্রেরি'),
        ('logo_type',       'emoji'),
        ('admin_username',  'admin'),
        ('admin_password',  'admin123'),
        ('super_username',  'superadmin'),
        ('super_password',  'super123'),
        ('smtp_email',      ''),
        ('smtp_password',   ''),
    ]
    for key, val in defaults:
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)', (key, val))

    sample_books = [
        ('The Great Gatsby', 'F. Scott Fitzgerald', '9780743273565', 'Fiction', 3, 3, '#E74C3C'),
        ('To Kill a Mockingbird', 'Harper Lee', '9780061935466', 'Fiction', 2, 2, '#2ECC71'),
        ('1984', 'George Orwell', '9780451524935', 'Dystopian', 4, 4, '#9B59B6'),
        ('Pride and Prejudice', 'Jane Austen', '9780141439518', 'Romance', 2, 2, '#E67E22'),
        ('The Hobbit', 'J.R.R. Tolkien', '9780547928227', 'Fantasy', 3, 3, '#1ABC9C'),
        ("Harry Potter and the Sorcerer's Stone", 'J.K. Rowling', '9780590353427', 'Fantasy', 5, 5, '#F39C12'),
        ('The Alchemist', 'Paulo Coelho', '9780062315007', 'Philosophy', 2, 2, '#3498DB'),
        ('Brave New World', 'Aldous Huxley', '9780060850524', 'Dystopian', 1, 1, '#E91E63'),
    ]
    for book in sample_books:
        try:
            c.execute('INSERT INTO books (title, author, isbn, genre, total_copies, available_copies, cover_color) VALUES (?,?,?,?,?,?,?)', book)
        except: pass

    os.makedirs('static/pdfs', exist_ok=True)
    conn.commit()
    conn.close()


def get_settings():
    conn = get_db()
    rows = conn.execute('SELECT key, value FROM settings').fetchall()
    conn.close()
    return {row['key']: row['value'] for row in rows}


@app.context_processor
def inject_settings():
    return dict(site=get_settings())


# ════════════════════════════════════════════
#  Admin Auth
# ════════════════════════════════════════════

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('dashboard') if session.get('is_admin') else url_for('books'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        s = get_settings()
        if username == s.get('super_username') and password == s.get('super_password'):
            session['logged_in'] = True
            session['is_admin']  = True
            session['is_super']  = True
            session['username']  = username
            flash('স্বাগতম, Super Admin!', 'success')
            return redirect(url_for('settings'))
        elif username == s.get('admin_username') and password == s.get('admin_password'):
            session['logged_in'] = True
            session['is_admin']  = True
            session['is_super']  = False
            session['username']  = username
            flash('স্বাগতম, Admin!', 'success')
            return redirect(request.args.get('next', url_for('dashboard')))
        else:
            flash('ভুল Username বা Password!', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('সফলভাবে লগআউট হয়েছে।', 'info')
    return redirect(url_for('login'))


# ════════════════════════════════════════════
#  Student Auth
# ════════════════════════════════════════════

@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if session.get('student_logged_in'):
        return redirect(url_for('my_books'))

    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip()
        phone    = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()
        confirm  = request.form.get('confirm_password', '').strip()

        if not name or not email or not password:
            flash('নাম, ইমেইল ও পাসওয়ার্ড আবশ্যক।', 'error')
            return redirect(url_for('student_register'))
        if len(password) < 6:
            flash('পাসওয়ার্ড কমপক্ষে ৬ অক্ষরের হতে হবে।', 'error')
            return redirect(url_for('student_register'))
        if password != confirm:
            flash('পাসওয়ার্ড দুটো মিলছে না।', 'error')
            return redirect(url_for('student_register'))

        conn = get_db()
        try:
            conn.execute('INSERT INTO students (name, email, phone, password) VALUES (?,?,?,?)',
                         (name, email, phone, password))
            conn.commit()
            flash('Registration সফল! এখন লগইন করুন।', 'success')
            conn.close()
            return redirect(url_for('student_login'))
        except Exception:
            flash('এই ইমেইল দিয়ে আগেই registration আছে।', 'error')
            conn.close()
            return redirect(url_for('student_register'))

    return render_template('student_register.html')


@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if session.get('student_logged_in'):
        return redirect(url_for('my_books'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        conn     = get_db()
        student  = conn.execute('SELECT * FROM students WHERE email=? AND active=1', (email,)).fetchone()
        conn.close()

        if student and student['password'] == password:
            session['student_logged_in'] = True
            session['student_id']        = student['id']
            session['student_name']      = student['name']
            session['student_email']     = student['email']
            flash(f'স্বাগতম, {student["name"]}!', 'success')
            return redirect(request.args.get('next', url_for('my_books')))
        else:
            flash('ভুল Email বা Password!', 'error')

    return render_template('student_login.html')


@app.route('/student/logout')
def student_logout():
    session.pop('student_logged_in', None)
    session.pop('student_id', None)
    session.pop('student_name', None)
    session.pop('student_email', None)
    flash('লগআউট হয়েছে।', 'info')
    return redirect(url_for('books'))


# ════════════════════════════════════════════
#  Super Admin — Settings
# ════════════════════════════════════════════

@app.route('/settings', methods=['GET', 'POST'])
@super_required
def settings():
    if request.method == 'POST':
        conn            = get_db()
        library_name    = request.form.get('library_name', '').strip()
        library_tagline = request.form.get('library_tagline', '').strip()
        library_footer  = request.form.get('library_footer', '').strip()
        logo_type       = request.form.get('logo_type', 'emoji')
        library_logo    = request.form.get('library_logo', '📚').strip()
        logo_file       = request.files.get('logo_file')
        if logo_file and logo_file.filename:
            allowed = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}
            ext = logo_file.filename.rsplit('.', 1)[-1].lower()
            if ext in allowed:
                b64          = base64.b64encode(logo_file.read()).decode('utf-8')
                mime         = 'image/svg+xml' if ext == 'svg' else f'image/{ext}'
                library_logo = f'data:{mime};base64,{b64}'
                logo_type    = 'image'
            else:
                flash('শুধু PNG, JPG, GIF, SVG, WEBP ফাইল আপলোড করা যাবে।', 'error')
                conn.close()
                return redirect(url_for('settings'))
        smtp_email    = request.form.get('smtp_email', '').strip()
        smtp_password = request.form.get('smtp_password', '').strip()

        updates = {
            'library_name':    library_name    or 'BiblioTech',
            'library_tagline': library_tagline or 'Library System',
            'library_footer':  library_footer  or '',
            'library_logo':    library_logo,
            'logo_type':       logo_type,
            'smtp_email':      smtp_email,
        }
        # Password field খালি রাখলে পুরানো password রাখব
        if smtp_password:
            updates['smtp_password'] = smtp_password

        for key, val in updates.items():
            conn.execute('UPDATE settings SET value=? WHERE key=?', (val, key))
        conn.commit()
        conn.close()
        flash('Settings সফলভাবে আপডেট হয়েছে!', 'success')
        return redirect(url_for('settings'))
    return render_template('settings.html')


# ════════════════════════════════════════════
#  Change Password
# ════════════════════════════════════════════

@app.route('/change-password', methods=['GET', 'POST'])
@admin_required
def change_password():
    if request.method == 'POST':
        current  = request.form.get('current_password', '').strip()
        new_pw   = request.form.get('new_password', '').strip()
        confirm  = request.form.get('confirm_password', '').strip()
        s        = get_settings()
        is_super = session.get('is_super')
        correct  = s.get('super_password') if is_super else s.get('admin_password')
        pw_key   = 'super_password'        if is_super else 'admin_password'
        if current != correct:
            flash('বর্তমান পাসওয়ার্ড সঠিক নয়!', 'error')
            return redirect(url_for('change_password'))
        if len(new_pw) < 6:
            flash('নতুন পাসওয়ার্ড কমপক্ষে ৬ অক্ষরের হতে হবে।', 'error')
            return redirect(url_for('change_password'))
        if new_pw != confirm:
            flash('নতুন পাসওয়ার্ড দুটো মিলছে না!', 'error')
            return redirect(url_for('change_password'))
        conn = get_db()
        conn.execute('UPDATE settings SET value=? WHERE key=?', (new_pw, pw_key))
        conn.commit()
        conn.close()
        flash('পাসওয়ার্ড সফলভাবে পরিবর্তন হয়েছে! আবার লগইন করুন।', 'success')
        session.clear()
        return redirect(url_for('login'))
    return render_template('change_password.html')


# ════════════════════════════════════════════
#  Public — বইয়ের তালিকা
# ════════════════════════════════════════════

@app.route('/')
def index():
    return redirect(url_for('books'))


@app.route('/books')
def books():
    search = request.args.get('search', '')
    genre  = request.args.get('genre', '')
    conn   = get_db()
    query  = 'SELECT * FROM books WHERE 1=1'
    params = []
    if search:
        query += ' AND (title LIKE ? OR author LIKE ? OR isbn LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    if genre:
        query += ' AND genre = ?'
        params.append(genre)
    query += ' ORDER BY title'
    books_list = conn.execute(query, params).fetchall()
    genres     = conn.execute('SELECT DISTINCT genre FROM books WHERE genre IS NOT NULL ORDER BY genre').fetchall()

    pending_requests = {}
    if session.get('is_admin'):
        rows = conn.execute("""
            SELECT br.book_id, br.id, s.name as student_name, s.phone as student_phone, br.request_date
            FROM book_requests br
            JOIN students s ON br.student_id = s.id
            WHERE br.status='pending' ORDER BY br.request_date ASC
        """).fetchall()
        for row in rows:
            bid = row['book_id']
            if bid not in pending_requests:
                pending_requests[bid] = []
            pending_requests[bid].append(row)

    conn.close()
    return render_template('books.html', books=books_list, genres=genres,
                           search=search, selected_genre=genre,
                           pending_requests=pending_requests)


# ════════════════════════════════════════════
#  Student — Request, My Books, PDF
# ════════════════════════════════════════════

@app.route('/request-book/<int:book_id>', methods=['POST'])
@student_required
def request_book(book_id):
    student_id   = session['student_id']
    student_note = request.form.get('student_note', '').strip()
    conn = get_db()
    book = conn.execute('SELECT * FROM books WHERE id=?', (book_id,)).fetchone()

    if not book:
        flash('বইটি পাওয়া যায়নি!', 'error')
        conn.close()
        return redirect(url_for('books'))
    if book['available_copies'] <= 0:
        flash('দুঃখিত! বইটি এই মুহূর্তে পাওয়া যাচ্ছে না।', 'error')
        conn.close()
        return redirect(url_for('books'))

    # একই student একই বই double request করতে পারবে না
    existing = conn.execute(
        "SELECT id FROM book_requests WHERE book_id=? AND student_id=? AND status='pending'",
        (book_id, student_id)
    ).fetchone()
    if existing:
        flash('আপনি ইতিমধ্যে এই বইটির জন্য request করেছেন।', 'info')
        conn.close()
        return redirect(url_for('books'))

    conn.execute('INSERT INTO book_requests (book_id, student_id, student_note) VALUES (?,?,?)',
                 (book_id, student_id, student_note))
    conn.commit()
    conn.close()
    flash(f'"{book["title"]}" বইটির জন্য request পাঠানো হয়েছে!', 'success')
    return redirect(url_for('books'))


@app.route('/my-books')
@student_required
def my_books():
    conn = get_db()
    books_list = conn.execute("""
        SELECT br.*, b.title as book_title, b.author, b.cover_color, b.genre
        FROM book_requests br
        JOIN books b ON br.book_id = b.id
        WHERE br.student_id = ?
        ORDER BY br.request_date DESC
    """, (session['student_id'],)).fetchall()
    conn.close()
    return render_template('my_books.html', books=books_list)


@app.route('/read-pdf/<int:req_id>')
@student_required
def read_pdf(req_id):
    conn = get_db()
    req  = conn.execute("""
        SELECT br.*, b.title as book_title, b.author, b.cover_color
        FROM book_requests br JOIN books b ON br.book_id = b.id
        WHERE br.id = ? AND br.student_id = ? AND br.status = 'approved' AND br.pdf_filename IS NOT NULL
    """, (req_id, session['student_id'])).fetchone()
    conn.close()
    if not req:
        flash('বইটি পাওয়া যায়নি অথবা PDF নেই।', 'error')
        return redirect(url_for('my_books'))
    return render_template('read_pdf.html', req=req)


# ════════════════════════════════════════════
#  Admin Routes
# ════════════════════════════════════════════

@app.route('/dashboard')
@admin_required
def dashboard():
    conn = get_db()
    total_books    = conn.execute('SELECT SUM(total_copies) FROM books').fetchone()[0] or 0
    total_titles   = conn.execute('SELECT COUNT(*) FROM books').fetchone()[0]
    total_members  = conn.execute('SELECT COUNT(*) FROM members WHERE active=1').fetchone()[0]
    total_students = conn.execute('SELECT COUNT(*) FROM students WHERE active=1').fetchone()[0]
    active_borrows = conn.execute("SELECT COUNT(*) FROM borrowings WHERE status='borrowed'").fetchone()[0]
    overdue        = conn.execute("SELECT COUNT(*) FROM borrowings WHERE status='borrowed' AND due_date < date('now')").fetchone()[0]
    pending_reqs   = conn.execute("SELECT COUNT(*) FROM book_requests WHERE status='pending'").fetchone()[0]

    recent_activity = conn.execute("""
        SELECT b.title, m.name, br.borrow_date, br.status, br.due_date
        FROM borrowings br JOIN books b ON br.book_id=b.id JOIN members m ON br.member_id=m.id
        ORDER BY br.borrow_date DESC LIMIT 5
    """).fetchall()
    popular_books = conn.execute("""
        SELECT b.title, b.author, b.cover_color, COUNT(br.id) as borrow_count
        FROM books b LEFT JOIN borrowings br ON b.id=br.book_id
        GROUP BY b.id ORDER BY borrow_count DESC LIMIT 4
    """).fetchall()
    recent_requests = conn.execute("""
        SELECT br.*, b.title as book_title, b.cover_color, s.name as student_name
        FROM book_requests br JOIN books b ON br.book_id=b.id JOIN students s ON br.student_id=s.id
        WHERE br.status='pending' ORDER BY br.request_date DESC LIMIT 5
    """).fetchall()
    conn.close()
    return render_template('dashboard.html',
        total_books=total_books, total_titles=total_titles,
        total_members=total_members, total_students=total_students,
        active_borrows=active_borrows, overdue=overdue, pending_reqs=pending_reqs,
        recent_activity=recent_activity, popular_books=popular_books,
        recent_requests=recent_requests)


@app.route('/books/add', methods=['GET', 'POST'])
@admin_required
def add_book():
    if request.method == 'POST':
        title  = request.form['title']
        author = request.form['author']
        isbn   = request.form.get('isbn', '')
        genre  = request.form.get('genre', '')
        copies = int(request.form.get('copies', 1))
        color  = random.choice(['#E74C3C','#2ECC71','#9B59B6','#E67E22','#1ABC9C','#F39C12','#3498DB','#E91E63','#34495E','#16A085'])
        conn = get_db()
        try:
            conn.execute('INSERT INTO books (title, author, isbn, genre, total_copies, available_copies, cover_color) VALUES (?,?,?,?,?,?,?)',
                         (title, author, isbn, genre, copies, copies, color))
            conn.commit()
            flash('বইটি সফলভাবে যোগ করা হয়েছে!', 'success')
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
        finally:
            conn.close()
        return redirect(url_for('books'))
    return render_template('add_book.html')


@app.route('/books/delete/<int:book_id>', methods=['POST'])
@admin_required
def delete_book(book_id):
    conn = get_db()
    conn.execute('DELETE FROM books WHERE id=?', (book_id,))
    conn.commit()
    conn.close()
    flash('বইটি মুছে ফেলা হয়েছে।', 'info')
    return redirect(url_for('books'))


@app.route('/members')
@admin_required
def members():
    search = request.args.get('search', '')
    conn = get_db()
    if search:
        ml = conn.execute('SELECT * FROM members WHERE name LIKE ? OR email LIKE ? ORDER BY name',
                          (f'%{search}%', f'%{search}%')).fetchall()
    else:
        ml = conn.execute('SELECT * FROM members ORDER BY name').fetchall()
    conn.close()
    return render_template('members.html', members=ml, search=search)


@app.route('/members/add', methods=['GET', 'POST'])
@admin_required
def add_member():
    if request.method == 'POST':
        name  = request.form['name']
        email = request.form['email']
        phone = request.form.get('phone', '')
        conn  = get_db()
        try:
            conn.execute('INSERT INTO members (name, email, phone) VALUES (?,?,?)', (name, email, phone))
            conn.commit()
            flash('সদস্য সফলভাবে যোগ করা হয়েছে!', 'success')
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
        finally:
            conn.close()
        return redirect(url_for('members'))
    return render_template('add_member.html')


@app.route('/members/delete/<int:member_id>', methods=['POST'])
@admin_required
def delete_member(member_id):
    conn = get_db()
    conn.execute('DELETE FROM members WHERE id=?', (member_id,))
    conn.commit()
    conn.close()
    flash('সদস্যটি মুছে ফেলা হয়েছে।', 'info')
    return redirect(url_for('members'))


@app.route('/students')
@admin_required
def students():
    search = request.args.get('search', '')
    conn = get_db()
    if search:
        sl = conn.execute('SELECT * FROM students WHERE name LIKE ? OR email LIKE ? ORDER BY reg_date DESC',
                          (f'%{search}%', f'%{search}%')).fetchall()
    else:
        sl = conn.execute('SELECT * FROM students ORDER BY reg_date DESC').fetchall()
    conn.close()
    return render_template('students.html', students=sl, search=search)


@app.route('/students/toggle/<int:student_id>', methods=['POST'])
@admin_required
def toggle_student(student_id):
    conn = get_db()
    s = conn.execute('SELECT active FROM students WHERE id=?', (student_id,)).fetchone()
    if s:
        new_status = 0 if s['active'] else 1
        conn.execute('UPDATE students SET active=? WHERE id=?', (new_status, student_id))
        conn.commit()
        flash('Student এর অবস্থা পরিবর্তন হয়েছে।', 'info')
    conn.close()
    return redirect(url_for('students'))


@app.route('/requests')
@admin_required
def requests_list():
    status_filter = request.args.get('status', 'pending')
    conn = get_db()
    query  = '''SELECT br.*, b.title as book_title, b.cover_color, b.author,
                       s.name as student_name, s.email as student_email, s.phone as student_phone
                FROM book_requests br
                JOIN books b ON br.book_id=b.id
                JOIN students s ON br.student_id=s.id'''
    params = []
    if status_filter != 'all':
        query += ' WHERE br.status=?'
        params.append(status_filter)
    query += ' ORDER BY br.request_date DESC'
    reqs = conn.execute(query, params).fetchall()
    counts = {
        'pending':  conn.execute("SELECT COUNT(*) FROM book_requests WHERE status='pending'").fetchone()[0],
        'approved': conn.execute("SELECT COUNT(*) FROM book_requests WHERE status='approved'").fetchone()[0],
        'rejected': conn.execute("SELECT COUNT(*) FROM book_requests WHERE status='rejected'").fetchone()[0],
    }
    conn.close()
    return render_template('requests.html', requests=reqs, status_filter=status_filter, counts=counts)


@app.route('/requests/<int:req_id>/approve', methods=['POST'])
@admin_required
def approve_request(req_id):
    admin_note   = request.form.get('admin_note', '').strip()
    pdf_file     = request.files.get('pdf_file')
    pdf_filename = None
    conn = get_db()
    req  = conn.execute('SELECT * FROM book_requests WHERE id=?', (req_id,)).fetchone()
    if req and req['status'] == 'pending':
        book = conn.execute('SELECT * FROM books WHERE id=?', (req['book_id'],)).fetchone()
        if book:
            if pdf_file and pdf_file.filename.lower().endswith('.pdf'):
                safe_name    = f'req_{req_id}_{req["book_id"]}.pdf'
                pdf_filename = safe_name
                pdf_file.save(os.path.join('static', 'pdfs', safe_name))
            conn.execute(
                "UPDATE book_requests SET status='approved', admin_note=?, resolved_date=date('now'), pdf_filename=? WHERE id=?",
                (admin_note, pdf_filename, req_id)
            )
            conn.commit()
            has_pdf = '📄 PDF সহ ' if pdf_filename else ''
            flash(f'{has_pdf}"{book["title"]}" — request অনুমোদন হয়েছে।', 'success')
        else:
            flash('বইটি পাওয়া যাচ্ছে না।', 'error')
    conn.close()
    return redirect(request.referrer or url_for('requests_list'))


@app.route('/requests/<int:req_id>/reject', methods=['POST'])
@admin_required
def reject_request(req_id):
    admin_note = request.form.get('admin_note', '').strip()
    conn = get_db()
    req  = conn.execute('SELECT * FROM book_requests WHERE id=?', (req_id,)).fetchone()
    if req and req['status'] == 'pending':
        conn.execute("UPDATE book_requests SET status='rejected', admin_note=?, resolved_date=date('now') WHERE id=?",
                     (admin_note, req_id))
        conn.commit()
        flash('Request বাতিল করা হয়েছে।', 'info')
    conn.close()
    return redirect(request.referrer or url_for('requests_list'))


@app.route('/borrow', methods=['GET', 'POST'])
@admin_required
def borrow():
    conn = get_db()
    if request.method == 'POST':
        book_id   = request.form['book_id']
        member_id = request.form['member_id']
        days      = int(request.form.get('days', 14))
        due_date  = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
        book = conn.execute('SELECT * FROM books WHERE id=?', (book_id,)).fetchone()
        if book and book['available_copies'] > 0:
            conn.execute('INSERT INTO borrowings (book_id, member_id, due_date) VALUES (?,?,?)',
                         (book_id, member_id, due_date))
            conn.execute('UPDATE books SET available_copies = available_copies - 1 WHERE id=?', (book_id,))
            conn.commit()
            flash('বই সফলভাবে ইস্যু করা হয়েছে!', 'success')
        else:
            flash('বইটি এই মুহূর্তে পাওয়া যাচ্ছে না!', 'error')
        conn.close()
        return redirect(url_for('borrow'))
    books_list   = conn.execute('SELECT * FROM books WHERE available_copies > 0 ORDER BY title').fetchall()
    members_list = conn.execute('SELECT * FROM members WHERE active=1 ORDER BY name').fetchall()
    borrowings   = conn.execute("""
        SELECT br.*, b.title, b.cover_color, m.name as member_name
        FROM borrowings br JOIN books b ON br.book_id=b.id JOIN members m ON br.member_id=m.id
        WHERE br.status='borrowed' ORDER BY br.borrow_date DESC
    """).fetchall()
    conn.close()
    return render_template('borrow.html', books=books_list, members=members_list, borrowings=borrowings)


@app.route('/return/<int:borrow_id>', methods=['POST'])
@admin_required
def return_book(borrow_id):
    conn   = get_db()
    borrow = conn.execute('SELECT * FROM borrowings WHERE id=?', (borrow_id,)).fetchone()
    if borrow:
        conn.execute("UPDATE borrowings SET status='returned', return_date=date('now') WHERE id=?", (borrow_id,))
        conn.execute('UPDATE books SET available_copies = available_copies + 1 WHERE id=?', (borrow['book_id'],))
        conn.commit()
        flash('বই সফলভাবে ফেরত দেওয়া হয়েছে!', 'success')
    conn.close()
    return redirect(url_for('borrow'))


@app.route('/issued-books')
@admin_required
def issued_books():
    conn = get_db()
    approved_reqs = conn.execute("""
        SELECT br.*, b.title as book_title, b.author, b.cover_color,
               s.name as student_name, s.phone as student_phone
        FROM book_requests br JOIN books b ON br.book_id=b.id JOIN students s ON br.student_id=s.id
        WHERE br.status='approved' ORDER BY br.resolved_date DESC
    """).fetchall()
    borrowings = conn.execute("""
        SELECT bw.*, b.title as book_title, b.author, b.cover_color,
               m.name as member_name, m.phone as member_phone, m.email as member_email
        FROM borrowings bw JOIN books b ON bw.book_id=b.id JOIN members m ON bw.member_id=m.id
        ORDER BY bw.borrow_date DESC
    """).fetchall()
    conn.close()
    return render_template('issued_books.html', approved_reqs=approved_reqs, borrowings=borrowings)


# ════════════════════════════════════════════
#  Student — Forgot / Reset Password
# ════════════════════════════════════════════

@app.route('/student/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        conn  = get_db()
        student = conn.execute('SELECT * FROM students WHERE email=? AND active=1', (email,)).fetchone()

        if not student:
            # Security: একই message দেখাই — email exist না করলেও
            flash('যদি এই email টি registered হয়, তাহলে reset link পাঠানো হবে।', 'info')
            conn.close()
            return redirect(url_for('forgot_password'))

        # পুরনো unused token delete করি
        conn.execute('DELETE FROM password_resets WHERE student_id=? AND used=0', (student['id'],))

        # নতুন token তৈরি
        token = secrets.token_urlsafe(32)
        conn.execute('INSERT INTO password_resets (student_id, token) VALUES (?,?)',
                     (student['id'], token))
        conn.commit()
        conn.close()

        # Email পাঠাও
        ok, msg = send_reset_email(email, student['name'], token)
        if ok:
            flash('Password reset link আপনার email এ পাঠানো হয়েছে! Inbox চেক করুন।', 'success')
        else:
            # SMTP fail হলে admin-reset এর কথা বলি
            flash(f'Email পাঠানো যায়নি ({msg})। Admin এর সাথে যোগাযোগ করুন।', 'error')

        return redirect(url_for('student_login'))

    return render_template('forgot_password.html')


@app.route('/student/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    conn  = get_db()
    # Token valid কিনা চেক — ১ ঘণ্টার মধ্যে, ব্যবহার না হওয়া
    reset = conn.execute("""
        SELECT pr.*, s.name, s.email
        FROM password_resets pr JOIN students s ON pr.student_id = s.id
        WHERE pr.token=? AND pr.used=0
          AND datetime(pr.created_at, '+1 hour') > datetime('now')
    """, (token,)).fetchone()

    if not reset:
        conn.close()
        flash('এই link টি invalid অথবা মেয়াদোত্তীর্ণ।', 'error')
        return redirect(url_for('student_login'))

    if request.method == 'POST':
        new_pw  = request.form.get('new_password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()

        if len(new_pw) < 6:
            flash('পাসওয়ার্ড কমপক্ষে ৬ অক্ষরের হতে হবে।', 'error')
            conn.close()
            return redirect(url_for('reset_password', token=token))
        if new_pw != confirm:
            flash('পাসওয়ার্ড দুটো মিলছে না।', 'error')
            conn.close()
            return redirect(url_for('reset_password', token=token))

        conn.execute('UPDATE students SET password=? WHERE id=?', (new_pw, reset['student_id']))
        conn.execute('UPDATE password_resets SET used=1 WHERE token=?', (token,))
        conn.commit()
        conn.close()
        flash('পাসওয়ার্ড সফলভাবে পরিবর্তন হয়েছে! এখন লগইন করুন।', 'success')
        return redirect(url_for('student_login'))

    conn.close()
    return render_template('reset_password.html', token=token, reset=reset)


# ════════════════════════════════════════════
#  Admin — Student Password Reset
# ════════════════════════════════════════════

@app.route('/students/reset-password/<int:student_id>', methods=['POST'])
@admin_required
def admin_reset_student_password(student_id):
    new_pw = request.form.get('new_password', '').strip()
    if len(new_pw) < 6:
        flash('পাসওয়ার্ড কমপক্ষে ৬ অক্ষরের হতে হবে।', 'error')
        return redirect(url_for('students'))
    conn = get_db()
    s = conn.execute('SELECT name FROM students WHERE id=?', (student_id,)).fetchone()
    if s:
        conn.execute('UPDATE students SET password=? WHERE id=?', (new_pw, student_id))
        conn.commit()
        flash(f'{s["name"]} এর পাসওয়ার্ড reset হয়েছে।', 'success')
    conn.close()
    return redirect(url_for('students'))


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
