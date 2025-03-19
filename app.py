from flask import Flask, render_template,request, redirect, url_for, flash,session, send_from_directory, jsonify, send_file
from flask_mysqldb import MySQL 
from flask_bcrypt import Bcrypt
from flask_ckeditor import CKEditor
from functools import wraps
from datetime import datetime
from gtts import gTTS
import os
import pyttsx3
import uuid
import secrets
from MySQLdb.cursors import DictCursor
import MySQLdb


app = Flask(__name__)
bcrypt = Bcrypt(app)

# App secret key for sessions
app.secret_key = 'secret123'

# MySQL database configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'FYP'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

# File upload configuration
UPLOAD_FOLDER = 'uploads'  
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # Create the folder if it doesn't exist

# Initialize MySQL connection
mysql = MySQL(app)
ckeditor = CKEditor(app) # Initialize CKEditor

# Landing page route
@app.route('/landing-page')
def index():
    print("Landing page route accessed!")
    return render_template('landing-page.html')
 
# Signup route   
@app.route('/sign-up', methods=['GET', 'POST'])
def signup():
     # Fetch form data
    if request.method == 'POST':
        first_name = request.form['firstname']
        last_name = request.form['lastname']
        phone = request.form['phonenumber']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form.get('confirmpassword', '')  # Use .get()

        # Check if passwords match
        if password != confirm_password:
            flash("Passwords do not match!", "danger")
            return redirect(url_for('signup'))
    

        # Hash the password
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # Insert user into the database
        cursor = mysql.connection.cursor()
        cursor.execute(
            "INSERT INTO users (first_name, last_name, phone_number, email, password_hash) VALUES (%s, %s, %s, %s, %s)", 
            (first_name, last_name, phone, email, hashed_password)
        )
        mysql.connection.commit()
        cursor.close()

        flash("Signup successful! You can now log in.", "success")
        return redirect(url_for('signin'))

    return render_template('sign-up.html')

#signin route
@app.route('/sign-in', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        email = request.form.get('email')
        pass_cand = request.form.get('password')
        cur = mysql.connection.cursor()
        result = cur.execute("SELECT * FROM users WHERE email=%s", [email])
        if result > 0:
            # Get stored data
            data = cur.fetchone()
            stored_password = data['password_hash']
            # Compare passwords directly
            
            if bcrypt.check_password_hash(stored_password, pass_cand):
                session['logged_in'] = True
                session['email'] = email

                flash('You are now logged in', 'success')
                return redirect(url_for('homepage'))
            else:
                flash('Invalid Login', 'danger')
                return render_template('sign-in.html')
        else:
            flash('User Not Found', 'danger')
            return render_template('sign-in.html')
    return render_template('sign-in.html')

# Decorator to check if user is logged in
def is_logged_in(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "email" not in session:  # Check if the user is logged in
            flash("You need to log in first", "danger")
            return redirect(url_for("signin"))  # ✅ Fixed redirect
        return f(*args, **kwargs)  # Proceed with the original function
    return decorated_function


#Logout route
@app.route('/logout')
def logout():
  session.clear()
  flash('You are now logged out', 'success')
  return redirect(url_for('signin'))  

#create folder route
@app.route("/create_folder", methods=["POST"])
def create_folder():
    if "email" not in session:  # Check if user is logged in
        flash("You must be logged in to create a folder!", "danger")
        return redirect(url_for("homepage"))

    folder_name = request.form.get("folder_name", "").strip()
    
    # Get the user's ID from the database using session email
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (session["email"],))
    user = cur.fetchone()

    if not user:
        flash("User not found!", "danger")
        return redirect(url_for("homepage"))

    user_id = user["id"]  # Extract user ID

    # Insert folder into database
    cur.execute(
        "INSERT INTO folders (user_id, folder_name) VALUES (%s, %s)", 
        (user_id, folder_name)
    )
    mysql.connection.commit()
    cur.close()

    flash("Folder created successfully!", "success")
    return redirect(url_for("homepage"))

@app.route('/move_folder_to_trash/<int:folder_id>', methods=['POST'])
@is_logged_in
def move_folder_to_trash(folder_id):
    try:
        cur = mysql.connection.cursor()

        # Move folder to trash
        cur.execute("UPDATE folders SET deleted = 1 WHERE id = %s", (folder_id,))

        # Move all notes inside the folder to trash
        cur.execute("UPDATE notes SET deleted = 1 WHERE folder_id = %s", (folder_id,))

        mysql.connection.commit()
        cur.close()

        flash("Folder and its files moved to trash!", "success")  # ✅ Flash message

        return redirect(url_for('trash'))  # ✅ Redirect to trash page

    except Exception as e:
        mysql.connection.rollback()
        flash(f"Error moving folder to trash: {e}", "danger")  # ✅ Show error as flash message
        return redirect(url_for('trash'))  # ✅ Redirect even on error
#search route
@app.route('/search')
@is_logged_in
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)  # Fix here

    print("Session email:", session.get("email"))

    cursor.execute("SELECT id FROM users WHERE email = %s", (session.get("email"),))
    user = cursor.fetchone()

    if not user:
        return jsonify([])

    user_id = user["id"]

    print("User ID:", user_id, "Search Query:", query)

    cursor.execute("""
        SELECT id, title, created_by, uploaded_at, time_created
        FROM notes
        WHERE created_by = %s AND title LIKE %s
    """, (session['email'], f"%{query}%"))

    results = cursor.fetchall()
    cursor.close()

    print("Search results:", results)

    return jsonify(results)
#seacrh folder route
@app.route('/search_folders')
@is_logged_in
def search_folders():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    user_email = session.get("email")
    if not user_email:
        return jsonify([])

    print("User Email:", user_email, "Search Query:", query)

    # Searching for folders based on title and created_by (email)
    cursor.execute("""
        SELECT id, folder_name, user_id, created_at 
        FROM folders
        WHERE folder_name LIKE %s AND DELETED = 0
    """, ('%' + query + '%',))

    results = cursor.fetchall()
    cursor.close()

    print("Folder Search Results:", results)

    return jsonify(results)

#search shared notes route
@app.route('/search_shared_notes')
@is_logged_in
def search_shared_notes():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    user_email = session.get("email")
    if not user_email:
        return jsonify([])

    print("User Email:", user_email, "Search Query:", query)

    # Fetch shared notes where the user is the recipient (shared_with = email)
    cursor.execute("""
        SELECT sn.id AS share_id, n.id AS note_id, n.title, sn.shared_with
        FROM shared_notes sn
        JOIN notes n ON sn.note_id = n.id
        WHERE sn.shared_with = %s AND (n.title LIKE %s)
    """, (user_email, '%' + query + '%'))

    results = cursor.fetchall()
    cursor.close()

    print("Shared Notes Search Results:", results)

    return jsonify(results)

#search deleted notes route
@app.route('/search_trash')
@is_logged_in
def search_trash():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    user_email = session.get("email")
    if not user_email:
        return jsonify([])

    print("User Email:", user_email, "Search Query:", query)

    # 🔎 Search deleted notes
    cursor.execute("""
        SELECT id, title, deleted_at, 'note' AS type 
        FROM trash 
        WHERE deleted_by = %s AND title LIKE %s
    """, (user_email, '%' + query + '%'))
    notes = cursor.fetchall()
    print("🔎 Notes Found:", notes)  # Debugging

    # 📂 Search deleted folders (FIXED QUERY)
    cursor.execute("""
        SELECT id, folder_name AS title, created_at AS deleted_at, 'folder' AS type 
        FROM folders  
        WHERE user_id = (SELECT id FROM users WHERE email = %s) 
        AND deleted = 1 
        AND folder_name LIKE %s
    """, (user_email, '%' + query + '%'))
    folders = cursor.fetchall()
    print("📂 Folders Found:", folders)  # Debugging

    cursor.close()

    results = notes + folders  # Combine results
    print("🚀 Final Search Results:", results)  # Debugging

    return jsonify(results)


#navabr route
@app.route('/nav')
def nav():
    return render_template('navbar.html')
#shared route
@app.route('/shared')
def shared():
    return render_template('shared.html')

#edit note route
@app.route('/edit_file/<int:note_id>/<int:folder_id>', methods=['GET', 'POST'])
@is_logged_in
def edit_file(note_id, folder_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM notes WHERE id = %s", (note_id,))
    note = cur.fetchone()
    cur.close()

    if not note:
        flash("Note not found!", "danger")
        return redirect(url_for('my_files', folder_id=folder_id))

    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        file = request.files.get('file')

        file_path = note['file_path']  # Initialize with existing file path
        if file:
            filename = file.filename
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path) # File save, no error handling

        if not title:
            flash("Title is required", "danger")
            return render_template('editnote.html', note=note, folder_id=folder_id)

        cur = mysql.connection.cursor()
        cur.execute("""
            UPDATE notes SET title = %s, content = %s, file_path = %s
            WHERE id = %s
        """, (title, content, file_path, note_id))
        mysql.connection.commit() # Database commit, no error handling
        cur.close()

        flash('Note updated successfully!', 'success')
        return redirect(url_for('my_files', folder_id=folder_id))

    return render_template('editnote.html', note=note, folder_id=folder_id)

#home route
@app.route('/home')
def homepage():
    if "email" not in session:
        flash("You must be logged in to access this page!", "danger")
        return redirect(url_for("sign-in"))

    cur = mysql.connection.cursor()

    # Get the logged-in user's ID
    cur.execute("SELECT id FROM users WHERE email = %s", (session["email"],))
    user = cur.fetchone()

    if not user:
        flash("User not found!", "danger")
        return redirect(url_for("sign-in"))

    user_id = user["id"]

    # Pagination setup
    page = request.args.get('page', 1, type=int)  # Get the current page number
    per_page = 5  # Number of folders per page
    offset = (page - 1) * per_page  # Calculate offset

    # Fetch paginated folders with creator details
    cur.execute("""
        SELECT folders.id, folders.folder_name, folders.created_at, users.email AS created_by
        FROM folders
        JOIN users ON folders.user_id = users.id
        WHERE folders.user_id = %s And folders.deleted = 0
        ORDER BY folders.created_at DESC
        LIMIT %s OFFSET %s
    """, (user_id, per_page, offset))

    folders = cur.fetchall()

    # Count total folders for pagination controls
    cur.execute("SELECT COUNT(*) FROM folders WHERE user_id = %s AND deleted = 0", (user_id,))
    total_folders = cur.fetchone()["COUNT(*)"]

    cur.close()

    # Calculate total pages
    total_pages = (total_folders + per_page - 1) // per_page  # Round up division

    return render_template(
        'home-page.html',
        folders=folders,
        total_pages=total_pages,
        current_page=page
    )

#myfiles route
@app.route('/myfiles/<int:folder_id>')
@is_logged_in
def my_files(folder_id):
    cursor = mysql.connection.cursor()
    
    cursor.execute("""
        SELECT id, title, created_by, uploaded_at, time_created 
        FROM notes 
        WHERE folder_id = %s AND deleted = 0
    """, (folder_id,))
    files = cursor.fetchall()
    cursor.close()

    return render_template('myfiles.html', files=files, folder_id=folder_id)  # Pass folder_id here!

@app.route('/view_file/<int:note_id>')
@is_logged_in
def view_file(note_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM notes WHERE id = %s", (note_id,))
    note = cur.fetchone()
    cur.close()

    if not note:
        flash("Note not found!", "danger")
        # Handle the case where the note is not found.  Redirecting 
        # to myfiles with a potentially missing folder_id will cause an error
        return redirect(url_for('my_files'))  # Or redirect to a more appropriate page

    # Initialize the TTS engine (pyttsx3 - for offline)
    engine = pyttsx3.init()

    def speak_text(text):
        engine.say(text)
        engine.runAndWait()

    return render_template('viewnote.html', note=note, speak_text=speak_text) # Pass speak_text to the template

@app.route('/mynote/<int:folder_id>', methods=['GET', 'POST'])
@is_logged_in
def mynote(folder_id):
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        file = request.files.get('file')

        file_path = None
        if file:
            filename = file.filename
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(file_path)
            except Exception as e:
                flash(f"Error saving file: {e}", "danger")
                return render_template('mynote.html', folder_id=folder_id)

        if not title:
            flash('Title is required', 'danger')
            return render_template('mynote.html', folder_id=folder_id)

        cur = mysql.connection.cursor()
        try:
            cur.execute("""
                INSERT INTO notes (folder_id, title, content, file_path, created_by) 
                VALUES (%s, %s, %s, %s, %s)
            """, (folder_id, title, content, file_path, session['email']))
            mysql.connection.commit()
            flash('Note added successfully', 'success')
            return redirect(url_for('my_files', folder_id=folder_id))  # Correct redirect here!
        except Exception as e:
            mysql.connection.rollback()
            flash(f"Error saving note: {e}", "danger")
            return render_template('mynote.html', folder_id=folder_id)
        finally:
            cur.close()

    return render_template('note-page.html', folder_id=folder_id)  # Correct template for GET

@app.route('/download/<filename>')
def download_file(filename):
    folder_id = request.args.get('folder_id') #get the folder id.
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
    except FileNotFoundError:
        flash("File not found.", "danger")
        return redirect(url_for('my_files', folder_id=folder_id))

@app.route('/trash')
@is_logged_in
def trash():
    try:
        cursor = mysql.connection.cursor()
        user_email = session.get('email')

        if not user_email:
            flash("User session expired. Please log in again.", "danger")
            return redirect(url_for('login'))

        # ✅ Fetch deleted notes
        cursor.execute("SELECT id, title, deleted_at FROM trash WHERE deleted_by = %s", (user_email,))
        deleted_notes = cursor.fetchall()

        # ✅ Fetch deleted folders using email instead of user_id
        cursor.execute("""
            SELECT id, folder_name AS title, created_at AS deleted_at 
            FROM folders 
            WHERE deleted = 1 AND user_id = (SELECT id FROM users WHERE email = %s)
        """, (user_email,))
        deleted_folders = cursor.fetchall()

        # ✅ Combine results
        deleted_items = deleted_notes + deleted_folders

        print("📌 Deleted Notes:", deleted_notes)
        print("📌 Deleted Folders:", deleted_folders)

    except Exception as e:
        flash(f"Error fetching trash items: {e}", "danger")
        print("❌ Error fetching trash:", e)
        deleted_items = []

    finally:
        cursor.close()

    return render_template('trash.html', deleted_items=deleted_items)

@app.route('/restore_item/<int:item_id>', methods=['POST'])
@is_logged_in
def restore_item(item_id):
    try:
        cursor = mysql.connection.cursor()
        user_email = session.get('email')

        # ✅ Check if the item is a note in trash
        cursor.execute("SELECT note_id FROM trash WHERE id = %s AND deleted_by = %s", 
                       (item_id, user_email))
        note_result = cursor.fetchone()

        if note_result:
            note_id = note_result['note_id']
            cursor.execute("UPDATE notes SET deleted = 0 WHERE id = %s", (note_id,))
            cursor.execute("DELETE FROM trash WHERE id = %s", (item_id,))
            mysql.connection.commit()
            flash("Note restored successfully!", "success")

        else:
            # ✅ Check if the item is a folder
            cursor.execute("""
                SELECT id FROM folders WHERE id = %s 
                AND user_id = (SELECT id FROM users WHERE email = %s) AND deleted = 1
            """, (item_id, user_email))
            folder_result = cursor.fetchone()

            if folder_result:
                folder_id = folder_result['id']

                # ✅ Restore all notes inside the folder
                cursor.execute("UPDATE notes SET deleted = 0 WHERE folder_id = %s", (folder_id,))
                # ✅ Restore the folder
                cursor.execute("UPDATE folders SET deleted = 0 WHERE id = %s", (folder_id,))
                mysql.connection.commit()
                flash("Folder and all its notes restored successfully!", "success")
            else:
                flash("Item not found or unauthorized.", "danger")

    except Exception as e:
        mysql.connection.rollback()
        flash(f"Error restoring item: {e}", "danger")
    finally:
        cursor.close()

    return redirect(url_for('trash'))

@app.route('/delete_item_permanently/<int:item_id>', methods=['POST'])
@is_logged_in
def delete_item_permanently(item_id):
    try:
        cursor = mysql.connection.cursor()
        user_email = session.get('email')

        # ✅ Check if the item is a note in trash
        cursor.execute("SELECT note_id FROM trash WHERE id = %s AND deleted_by = %s", 
                       (item_id, user_email))
        note_result = cursor.fetchone()

        if note_result:
            note_id = note_result['note_id']
            cursor.execute("DELETE FROM notes WHERE id = %s", (note_id,))
            cursor.execute("DELETE FROM trash WHERE id = %s", (item_id,))
            mysql.connection.commit()
            flash("Note permanently deleted!", "success")

        else:
            # ✅ Check if the item is a folder
            cursor.execute("""
                SELECT id FROM folders WHERE id = %s 
                AND user_id = (SELECT id FROM users WHERE email = %s) AND deleted = 1
            """, (item_id, user_email))
            folder_result = cursor.fetchone()

            if folder_result:
                # ✅ Delete all notes inside the folder
                cursor.execute("DELETE FROM notes WHERE folder_id = %s", (item_id,))
                # ✅ Delete the folder itself
                cursor.execute("DELETE FROM folders WHERE id = %s", (item_id,))
                mysql.connection.commit()
                flash("Folder and its contents permanently deleted!", "success")
            else:
                flash("Item not found or unauthorized.", "danger")

    except Exception as e:
        mysql.connection.rollback()
        flash(f"Error permanently deleting item: {e}", "danger")
    finally:
        cursor.close()

    return redirect(url_for('trash'))


@app.route('/move_to_trash/<int:item_id>/<int:folder_id>', methods=['POST'])
@is_logged_in
def move_to_trash(item_id, folder_id):
    try:
        cursor = mysql.connection.cursor()

        # 🔹 Fetch the note from "notes" table BEFORE deleting it
        cursor.execute("SELECT * FROM notes WHERE id = %s", (item_id,))
        note = cursor.fetchone()

        if not note:
            flash("Note not found!", "danger")
            return redirect(url_for('my_files'))
        
        cursor.execute("""
            UPDATE notes 
            SET deleted = 1 
            WHERE id = %s
        """, (item_id,))

        # ✅ Insert into "trash" FIRST
        cursor.execute("""
            INSERT INTO trash (note_id, folder_id, title, content, deleted_by, deleted_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (note['id'], folder_id, note['title'], note['content'], session['email']))

        # ✅ Now delete it from "notes"
        #cursor.execute("DELETE FROM notes WHERE id = %s", (item_id,))

        mysql.connection.commit()
        flash("Note moved to trash successfully!", "success")

    except Exception as e:
        mysql.connection.rollback()
        flash(f"Error moving note to trash: {e}", "danger")
        print("❌ Error:", e)
    finally:
        cursor.close()

    return redirect(url_for('my_files', folder_id=folder_id))



@app.route('/speak', methods=['POST'])
def speak():
    text = request.form.get('text')
    filename = "static/speech.mp3"  # Save in a static folder

    try:
        engine = pyttsx3.init()
        engine.save_to_file(text, filename)
        engine.runAndWait()  # Wait until saving is done

        return send_file(filename, as_attachment=False)  # Send the file as a response
    except Exception as e:
        print(f"Error in /speak: {e}")
        return "Error generating speech", 500
    

@app.route('/generate_share_link/<int:note_id>')
@is_logged_in
def generate_share_link(note_id):
    print(f"Generating share link for note ID: {note_id}")
    
    share_id = str(uuid.uuid4())  # Generate a unique share ID
    share_link = url_for('view_shared_note', share_id=share_id, _external=True)

    print(f"Generated share link: {share_link}")
    
    return jsonify({'share_link': share_link, 'share_id': share_id})

@app.route('/confirm_share', methods=['POST'])
@is_logged_in
def confirm_share():
    note_id = request.form.get('note_id')
    share_id = request.form.get('share_id')

    if not note_id or not share_id:
        flash('Invalid sharing request', 'danger')
        return redirect(url_for('homepage'))  # Redirect to home instead

    cursor = mysql.connection.cursor()
    cursor.execute("""
        INSERT INTO shared_notes (note_id, share_id, shared_with)
        VALUES (%s, %s, %s)
    """, (note_id, share_id, session['email']))
    mysql.connection.commit()
    cursor.close()

    flash('Note successfully shared!', 'success')
    return redirect(url_for('shared_notes', share_id=share_id))  # ✅ Corrected

@app.route('/shared_notes')
def shared_notes():
    cursor = mysql.connection.cursor(DictCursor)
    
    # Assuming 'session["email"]' contains the logged-in user's email
    email = session.get("email")  

    cursor.execute("""
        SELECT notes.title, notes.id AS note_id, shared_notes.share_id, shared_notes.shared_with
        FROM notes 
        JOIN shared_notes ON notes.id = shared_notes.note_id
        WHERE shared_notes.shared_with = %s
    """, (email,))  # Pass parameter as a tuple

    notes = cursor.fetchall()  # Fetch multiple rows
    cursor.close()

    return render_template('shared.html', notes=notes)  # Pass the list


@app.route('/delete_shared_note/<share_id>', methods=['POST'])
def delete_shared_note(share_id):
    cursor = mysql.connection.cursor()
    
    # Check if the shared note exists before deleting
    cursor.execute("SELECT * FROM shared_notes WHERE share_id = %s", (share_id,))
    shared_note = cursor.fetchone()

    if shared_note:
        cursor.execute("DELETE FROM shared_notes WHERE share_id = %s", (share_id,))
        mysql.connection.commit()
        cursor.close()
        flash("Shared note deleted successfully.", "success")
    else:
        flash("Shared note not found.", "danger")

    return redirect(url_for('shared_notes', share_id=share_id))

@app.route('/view_shared_note/<share_id>')
def view_shared_note(share_id):
    cursor = mysql.connection.cursor(DictCursor)
    cursor.execute("""
        SELECT notes.title, notes.content, shared_notes.shared_with
        FROM notes
        JOIN shared_notes ON notes.id = shared_notes.note_id
        WHERE shared_notes.share_id = %s
    """, (share_id,))
    
    note = cursor.fetchone()
    cursor.close()

    if not note:
        flash("Shared note not found or access denied.", "danger")
        return redirect(url_for('homepage'))  # Redirect to home if invalid

    return render_template('sharednotes.html', note=note)

if __name__== '__main__':
    app.run(debug=True)