from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'library_secret_key_2024'

DB_PATH = 'library.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        author TEXT NOT NULL,
        isbn TEXT UNIQUE,
        genre TEXT,
        total_copies INTEGER DEFAULT 1,
        available_copies INTEGER DEFAULT 1,
        added_date TEXT DEFAULT CURRENT_TIMESTAMP,
        cover_color TEXT DEFAULT '#4A90D9'
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        join_date TEXT DEFAULT CURRENT_TIMESTAMP,
        active INTEGER DEFAULT 1
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS borrowings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER,
        member_id INTEGER,
        borrow_date TEXT DEFAULT CURRENT_TIMESTAMP,
        due_date TEXT,
        return_date TEXT,
        status TEXT DEFAULT 'borrowed',
        FOREIGN KEY(book_id) REFERENCES books(id),
        FOREIGN KEY(member_id) REFERENCES members(id)
    )''')
    
    # Sample data
    sample_books = [
        ('The Great Gatsby', 'F. Scott Fitzgerald', '9780743273565', 'Fiction', 3, 3, '#E74C3C'),
        ('To Kill a Mockingbird', 'Harper Lee', '9780061935466', 'Fiction', 2, 2, '#2ECC71'),
        ('1984', 'George Orwell', '9780451524935', 'Dystopian', 4, 4, '#9B59B6'),
        ('Pride and Prejudice', 'Jane Austen', '9780141439518', 'Romance', 2, 2, '#E67E22'),
        ('The Hobbit', 'J.R.R. Tolkien', '9780547928227', 'Fantasy', 3, 3, '#1ABC9C'),
        ('Harry Potter and the Sorcerer\'s Stone', 'J.K. Rowling', '9780590353427', 'Fantasy', 5, 5, '#F39C12'),
        ('The Alchemist', 'Paulo Coelho', '9780062315007', 'Philosophy', 2, 2, '#3498DB'),
        ('Brave New World', 'Aldous Huxley', '9780060850524', 'Dystopian', 1, 1, '#E91E63'),
    ]
    
    for book in sample_books:
        try:
            c.execute('INSERT INTO books (title, author, isbn, genre, total_copies, available_copies, cover_color) VALUES (?,?,?,?,?,?,?)', book)
        except:
            pass
    
    sample_members = [
        ('Rahim Hossain', 'rahim@example.com', '01711-234567'),
        ('Karim Ahmed', 'karim@example.com', '01812-345678'),
        ('Nadia Islam', 'nadia@example.com', '01913-456789'),
        ('Sadia Rahman', 'sadia@example.com', '01611-567890'),
    ]
    
    for member in sample_members:
        try:
            c.execute('INSERT INTO members (name, email, phone) VALUES (?,?,?)', member)
        except:
            pass
    
    conn.commit()
    conn.close()

@app.route('/')
def dashboard():
    conn = get_db()
    total_books = conn.execute('SELECT SUM(total_copies) FROM books').fetchone()[0] or 0
    total_titles = conn.execute('SELECT COUNT(*) FROM books').fetchone()[0]
    total_members = conn.execute('SELECT COUNT(*) FROM members WHERE active=1').fetchone()[0]
    active_borrows = conn.execute("SELECT COUNT(*) FROM borrowings WHERE status='borrowed'").fetchone()[0]
    
    overdue = conn.execute("""
        SELECT COUNT(*) FROM borrowings 
        WHERE status='borrowed' AND due_date < date('now')
    """).fetchone()[0]
    
    recent_activity = conn.execute("""
        SELECT b.title, m.name, br.borrow_date, br.status, br.due_date
        FROM borrowings br
        JOIN books b ON br.book_id = b.id
        JOIN members m ON br.member_id = m.id
        ORDER BY br.borrow_date DESC LIMIT 5
    """).fetchall()
    
    popular_books = conn.execute("""
        SELECT b.title, b.author, b.cover_color, COUNT(br.id) as borrow_count
        FROM books b LEFT JOIN borrowings br ON b.id = br.book_id
        GROUP BY b.id ORDER BY borrow_count DESC LIMIT 4
    """).fetchall()
    
    conn.close()
    return render_template('dashboard.html', 
        total_books=total_books, total_titles=total_titles,
        total_members=total_members, active_borrows=active_borrows,
        overdue=overdue, recent_activity=recent_activity,
        popular_books=popular_books)

@app.route('/books')
def books():
    search = request.args.get('search', '')
    genre = request.args.get('genre', '')
    conn = get_db()
    
    query = 'SELECT * FROM books WHERE 1=1'
    params = []
    if search:
        query += ' AND (title LIKE ? OR author LIKE ? OR isbn LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    if genre:
        query += ' AND genre = ?'
        params.append(genre)
    query += ' ORDER BY title'
    
    books_list = conn.execute(query, params).fetchall()
    genres = conn.execute('SELECT DISTINCT genre FROM books WHERE genre IS NOT NULL ORDER BY genre').fetchall()
    conn.close()
    return render_template('books.html', books=books_list, genres=genres, search=search, selected_genre=genre)

@app.route('/books/add', methods=['GET', 'POST'])
def add_book():
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        isbn = request.form.get('isbn', '')
        genre = request.form.get('genre', '')
        copies = int(request.form.get('copies', 1))
        colors = ['#E74C3C','#2ECC71','#9B59B6','#E67E22','#1ABC9C','#F39C12','#3498DB','#E91E63','#34495E','#16A085']
        import random
        color = random.choice(colors)
        
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
def delete_book(book_id):
    conn = get_db()
    conn.execute('DELETE FROM books WHERE id=?', (book_id,))
    conn.commit()
    conn.close()
    flash('বইটি মুছে ফেলা হয়েছে।', 'info')
    return redirect(url_for('books'))

@app.route('/members')
def members():
    search = request.args.get('search', '')
    conn = get_db()
    if search:
        members_list = conn.execute(
            'SELECT * FROM members WHERE name LIKE ? OR email LIKE ? ORDER BY name',
            (f'%{search}%', f'%{search}%')
        ).fetchall()
    else:
        members_list = conn.execute('SELECT * FROM members ORDER BY name').fetchall()
    conn.close()
    return render_template('members.html', members=members_list, search=search)

@app.route('/members/add', methods=['GET', 'POST'])
def add_member():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form.get('phone', '')
        conn = get_db()
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
def delete_member(member_id):
    conn = get_db()
    conn.execute('DELETE FROM members WHERE id=?', (member_id,))
    conn.commit()
    conn.close()
    flash('সদস্যটি মুছে ফেলা হয়েছে।', 'info')
    return redirect(url_for('members'))

@app.route('/borrow', methods=['GET', 'POST'])
def borrow():
    conn = get_db()
    if request.method == 'POST':
        book_id = request.form['book_id']
        member_id = request.form['member_id']
        days = int(request.form.get('days', 14))
        due_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
        
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
    
    books_list = conn.execute('SELECT * FROM books WHERE available_copies > 0 ORDER BY title').fetchall()
    members_list = conn.execute('SELECT * FROM members WHERE active=1 ORDER BY name').fetchall()
    borrowings = conn.execute("""
        SELECT br.*, b.title, b.cover_color, m.name as member_name
        FROM borrowings br
        JOIN books b ON br.book_id = b.id
        JOIN members m ON br.member_id = m.id
        WHERE br.status = 'borrowed'
        ORDER BY br.borrow_date DESC
    """).fetchall()
    conn.close()
    return render_template('borrow.html', books=books_list, members=members_list, borrowings=borrowings)

@app.route('/return/<int:borrow_id>', methods=['POST'])
def return_book(borrow_id):
    conn = get_db()
    borrow = conn.execute('SELECT * FROM borrowings WHERE id=?', (borrow_id,)).fetchone()
    if borrow:
        conn.execute("UPDATE borrowings SET status='returned', return_date=date('now') WHERE id=?", (borrow_id,))
        conn.execute('UPDATE books SET available_copies = available_copies + 1 WHERE id=?', (borrow['book_id'],))
        conn.commit()
        flash('বই সফলভাবে ফেরত দেওয়া হয়েছে!', 'success')
    conn.close()
    return redirect(url_for('borrow'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
