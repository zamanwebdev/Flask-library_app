from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import random
import os
import base64
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = 'library_secret_key_2024'

DB_PATH = 'library.db'
# Credentials are stored in DB (init_db sets defaults)

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
        book_id INTEGER NOT NULL, student_name TEXT NOT NULL,
        student_phone TEXT, student_note TEXT,
        request_date TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'pending', admin_note TEXT, resolved_date TEXT,
        pdf_filename TEXT,
        FOREIGN KEY(book_id) REFERENCES books(id)
    )''')
    # Migration: add pdf_filename if upgrading from old DB
    try:
        c.execute("ALTER TABLE book_requests ADD COLUMN pdf_filename TEXT")
    except:
        pass

    # ── Library settings table ──
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')

    # Default settings
    defaults = [
        ('library_name',    'BiblioTech'),
        ('library_tagline', 'Library System'),
        ('library_logo',    '📚'),
        ('library_footer',  'সিটি পাবলিক লাইব্রেরি'),
        ('logo_type',       'emoji'),
        # Credentials (stored as plain text — swap for hashed in production)
        ('admin_username',  'admin'),
        ('admin_password',  'admin123'),
        ('super_username',  'superadmin'),
        ('super_password',  'super123'),
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

    sample_members = [
        ('Rahim Hossain', 'rahim@example.com', '01711-234567'),
        ('Karim Ahmed',   'karim@example.com', '01812-345678'),
        ('Nadia Islam',   'nadia@example.com', '01913-456789'),
        ('Sadia Rahman',  'sadia@example.com', '01611-567890'),
    ]
    for member in sample_members:
        try:
            c.execute('INSERT INTO members (name, email, phone) VALUES (?,?,?)', member)
        except: pass

    conn.commit()
    conn.close()

    # PDF storage folder
    os.makedirs('static/pdfs', exist_ok=True)


def get_settings():
    """Settings dict সব template এ পাঠানো হবে।"""
    conn = get_db()
    rows = conn.execute('SELECT key, value FROM settings').fetchall()
    conn.close()
    return {row['key']: row['value'] for row in rows}


@app.context_processor
def inject_settings():
    """প্রতিটি template এ automatically settings inject করে।"""
    return dict(site=get_settings())


# ════════════════════════════════════════════
#  Auth
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
            flash('স্বাগতম, Admin! সফলভাবে লগইন হয়েছে।', 'success')
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
#  Super Admin — Settings
# ════════════════════════════════════════════

@app.route('/settings', methods=['GET', 'POST'])
@super_required
def settings():
    if request.method == 'POST':
        conn = get_db()

        library_name    = request.form.get('library_name', '').strip()
        library_tagline = request.form.get('library_tagline', '').strip()
        library_footer  = request.form.get('library_footer', '').strip()
        logo_type       = request.form.get('logo_type', 'emoji')
        library_logo    = request.form.get('library_logo', '📚').strip()

        # Image upload হলে base64 এ store করব
        logo_file = request.files.get('logo_file')
        if logo_file and logo_file.filename:
            allowed = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}
            ext = logo_file.filename.rsplit('.', 1)[-1].lower()
            if ext in allowed:
                img_data   = logo_file.read()
                b64        = base64.b64encode(img_data).decode('utf-8')
                mime       = 'image/svg+xml' if ext == 'svg' else f'image/{ext}'
                library_logo = f'data:{mime};base64,{b64}'
                logo_type    = 'image'
            else:
                flash('শুধু PNG, JPG, GIF, SVG, WEBP ফাইল আপলোড করা যাবে।', 'error')
                conn.close()
                return redirect(url_for('settings'))

        updates = {
            'library_name':    library_name    or 'BiblioTech',
            'library_tagline': library_tagline or 'Library System',
            'library_footer':  library_footer  or '',
            'library_logo':    library_logo,
            'logo_type':       logo_type,
        }
        for key, val in updates.items():
            conn.execute('UPDATE settings SET value=? WHERE key=?', (val, key))

        conn.commit()
        conn.close()
        flash('Settings সফলভাবে আপডেট হয়েছে!', 'success')
        return redirect(url_for('settings'))

    return render_template('settings.html')


# ════════════════════════════════════════════
#  Public
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
            SELECT book_id, id, student_name, student_phone, request_date
            FROM book_requests WHERE status='pending' ORDER BY request_date ASC
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


@app.route('/request-book/<int:book_id>', methods=['POST'])
def request_book(book_id):
    student_name  = request.form.get('student_name', '').strip()
    student_phone = request.form.get('student_phone', '').strip()
    student_note  = request.form.get('student_note', '').strip()

    if not student_name:
        flash('নাম দেওয়া আবশ্যক!', 'error')
        return redirect(url_for('books'))

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

    conn.execute('INSERT INTO book_requests (book_id, student_name, student_phone, student_note) VALUES (?,?,?,?)',
                 (book_id, student_name, student_phone, student_note))
    conn.commit()
    conn.close()
    flash(f'"{book["title"]}" বইটির জন্য আপনার request সফলভাবে পাঠানো হয়েছে!', 'success')
    return redirect(url_for('books'))


# ════════════════════════════════════════════
#  Admin
# ════════════════════════════════════════════

@app.route('/dashboard')
@admin_required
def dashboard():
    conn = get_db()
    total_books    = conn.execute('SELECT SUM(total_copies) FROM books').fetchone()[0] or 0
    total_titles   = conn.execute('SELECT COUNT(*) FROM books').fetchone()[0]
    total_members  = conn.execute('SELECT COUNT(*) FROM members WHERE active=1').fetchone()[0]
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
        SELECT br.*, b.title as book_title, b.cover_color
        FROM book_requests br JOIN books b ON br.book_id=b.id
        WHERE br.status='pending' ORDER BY br.request_date DESC LIMIT 5
    """).fetchall()

    conn.close()
    return render_template('dashboard.html',
        total_books=total_books, total_titles=total_titles,
        total_members=total_members, active_borrows=active_borrows,
        overdue=overdue, pending_reqs=pending_reqs,
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


@app.route('/requests')
@admin_required
def requests_list():
    status_filter = request.args.get('status', 'pending')
    conn = get_db()
    query  = 'SELECT br.*, b.title as book_title, b.cover_color, b.author FROM book_requests br JOIN books b ON br.book_id=b.id'
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
            # PDF upload handle
            if pdf_file and pdf_file.filename.lower().endswith('.pdf'):
                safe_name    = f"req_{req_id}_{req['book_id']}.pdf"
                pdf_filename = safe_name
                pdf_file.save(os.path.join('static', 'pdfs', safe_name))

            conn.execute(
                "UPDATE book_requests SET status='approved', admin_note=?, resolved_date=date('now'), pdf_filename=? WHERE id=?",
                (admin_note, pdf_filename, req_id)
            )
            conn.commit()
            has_pdf = '📄 PDF সহ ' if pdf_filename else ''
            flash(f'{has_pdf}"{book["title"]}" — {req["student_name"]} এর request অনুমোদন হয়েছে।', 'success')
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
        conn.execute("UPDATE book_requests SET status='rejected', admin_note=?, resolved_date=date('now') WHERE id=?", (admin_note, req_id))
        conn.commit()
        flash(f'{req["student_name"]} এর request বাতিল করা হয়েছে।', 'info')
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
            conn.execute('INSERT INTO borrowings (book_id, member_id, due_date) VALUES (?,?,?)', (book_id, member_id, due_date))
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
        SELECT br.*, b.title as book_title, b.author, b.cover_color
        FROM book_requests br JOIN books b ON br.book_id=b.id
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


@app.route('/change-password', methods=['GET', 'POST'])
@admin_required
def change_password():
    if request.method == 'POST':
        current  = request.form.get('current_password', '').strip()
        new_pw   = request.form.get('new_password', '').strip()
        confirm  = request.form.get('confirm_password', '').strip()

        s = get_settings()
        is_super = session.get('is_super')

        # যার পাসওয়ার্ড change হবে তার current password check
        if is_super:
            correct = s.get('super_password')
            pw_key  = 'super_password'
        else:
            correct = s.get('admin_password')
            pw_key  = 'admin_password'

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
#  Student — আমার অনুমোদিত বই (PDF পড়া)
# ════════════════════════════════════════════

@app.route('/my-books', methods=['GET', 'POST'])
def my_books():
    books_found = None
    student_name = ''

    if request.method == 'POST':
        student_name = request.form.get('student_name', '').strip()
        if student_name:
            conn = get_db()
            books_found = conn.execute("""
                SELECT br.*, b.title as book_title, b.author, b.cover_color, b.genre
                FROM book_requests br
                JOIN books b ON br.book_id = b.id
                WHERE br.student_name = ? AND br.status = 'approved'
                ORDER BY br.resolved_date DESC
            """, (student_name,)).fetchall()
            conn.close()

    return render_template('my_books.html', books=books_found, student_name=student_name)


@app.route('/read-pdf/<int:req_id>')
def read_pdf(req_id):
    conn = get_db()
    req  = conn.execute("""
        SELECT br.*, b.title as book_title, b.author, b.cover_color
        FROM book_requests br JOIN books b ON br.book_id = b.id
        WHERE br.id = ? AND br.status = 'approved' AND br.pdf_filename IS NOT NULL
    """, (req_id,)).fetchone()
    conn.close()

    if not req:
        flash('বইটি পাওয়া যায়নি অথবা PDF নেই।', 'error')
        return redirect(url_for('my_books'))

    return render_template('read_pdf.html', req=req)


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
