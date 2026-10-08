import os, sqlite3, secrets, hashlib, hmac, uuid
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory, abort

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, 'repository.db')
UPLOADS = os.path.join(BASE, 'uploads')
os.makedirs(UPLOADS, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
ALLOWED_EXT = {'pdf','doc','docx','txt'}
FACULTIES = ['Arts','Education','Law','Pharmacy','Science','Social Sciences','Technology','The Social Sciences']
OUTPUT_TYPES = ['Thesis','Dissertation','Journal Article','Conference Paper','Project Report','Book','Dataset']


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 120_000)
    return salt.hex() + '$' + digest.hex()


def check_password(password, stored):
    try:
        salt_hex, digest_hex = stored.split('$', 1)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt_hex), 120_000)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def init_db():
    conn = db()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'depositor',
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS outputs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      authors TEXT NOT NULL,
      abstract TEXT NOT NULL,
      keywords TEXT NOT NULL,
      faculty TEXT NOT NULL,
      department TEXT NOT NULL,
      output_type TEXT NOT NULL,
      year INTEGER NOT NULL,
      file_name TEXT,
      access_level TEXT NOT NULL DEFAULT 'open',
      status TEXT NOT NULL DEFAULT 'pending',
      submitted_by INTEGER,
      moderation_note TEXT,
      views INTEGER NOT NULL DEFAULT 0,
      downloads INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      FOREIGN KEY(submitted_by) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS audit (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      action TEXT NOT NULL,
      output_id INTEGER,
      created_at TEXT NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id),
      FOREIGN KEY(output_id) REFERENCES outputs(id)
    );
    ''')
    admin = conn.execute('SELECT id FROM users WHERE email=?', ('admin@ui.edu.ng',)).fetchone()
    if not admin:
        conn.execute('INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                     ('Repository Librarian','admin@ui.edu.ng',hash_password('Admin@12345'),'librarian',datetime.utcnow().isoformat()))
    count = conn.execute('SELECT COUNT(*) c FROM outputs').fetchone()['c']
    if count == 0:
        samples = [
          ('Machine Learning Approaches for Student Performance Prediction','Adebayo T.; Okafor N.','A study of supervised learning methods for predicting student performance.','machine learning, education, prediction','Science','Computer Science','Project Report',2025,None,'open','approved'),
          ('Digital Library Services and User Experience in Nigerian Universities','Ibrahim K.; Bello A.','An assessment of digital library service use and user experience.','digital library, usability, Nigeria','Social Sciences','Library and Information Science','Journal Article',2024,None,'open','approved'),
          ('Mobile Learning Adoption Among University Students','Ojo M.; Yusuf R.','Factors influencing adoption of mobile learning services among students.','mobile learning, adoption, students','Education','Educational Technology','Thesis',2025,None,'open','approved'),
          ('Data Privacy Practices in Higher Education Systems','Okoro P.; Adekunle S.','A review of privacy practices for student information systems.','privacy, data protection, higher education','Technology','Computer Science','Conference Paper',2023,None,'open','approved'),
          ('Open Access Repositories and Scholarly Visibility','Lawal F.; Eze C.','The role of institutional repositories in scholarly communication.','open access, repository, visibility','Arts','Communication and Language Arts','Journal Article',2024,None,'open','approved'),
        ]
        for s in samples:
            conn.execute('''INSERT INTO outputs(title,authors,abstract,keywords,faculty,department,output_type,year,file_name,access_level,status,created_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', s + (datetime.utcnow().isoformat(),))
    conn.commit(); conn.close()


def current_user():
    uid = session.get('user_id')
    if not uid: return None
    conn = db(); u = conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone(); conn.close(); return u


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash('Please log in first.')
            return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            u = current_user()
            if not u or u['role'] not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return deco


def audit(user_id, action, output_id=None):
    conn=db(); conn.execute('INSERT INTO audit(user_id,action,output_id,created_at) VALUES(?,?,?,?)',(user_id,action,output_id,datetime.utcnow().isoformat())); conn.commit(); conn.close()


@app.context_processor
def inject_user():
    return {'current_user': current_user(), 'faculties': FACULTIES, 'output_types': OUTPUT_TYPES}

@app.route('/')
def index():
    q = request.args.get('q','').strip(); faculty=request.args.get('faculty',''); department=request.args.get('department',''); author=request.args.get('author',''); output_type=request.args.get('output_type',''); year=request.args.get('year','')
    conn=db(); where=['status="approved"']; params=[]
    if q:
        where.append('(title LIKE ? OR authors LIKE ? OR keywords LIKE ? OR abstract LIKE ?)'); params += [f'%{q}%']*4
    if faculty: where.append('faculty=?'); params.append(faculty)
    if department: where.append('department LIKE ?'); params.append(f'%{department}%')
    if author: where.append('authors LIKE ?'); params.append(f'%{author}%')
    if output_type: where.append('output_type=?'); params.append(output_type)
    if year.isdigit(): where.append('year=?'); params.append(int(year))
    sql='SELECT * FROM outputs WHERE '+' AND '.join(where)+' ORDER BY year DESC, id DESC'
    rows=conn.execute(sql,params).fetchall()
    departments=[r['department'] for r in conn.execute('SELECT DISTINCT department FROM outputs WHERE status="approved" ORDER BY department').fetchall()]
    years=[r['year'] for r in conn.execute('SELECT DISTINCT year FROM outputs WHERE status="approved" ORDER BY year DESC').fetchall()]
    conn.close(); return render_template('index.html', outputs=rows, q=q, faculty=faculty, department=department, author=author, output_type=output_type, year=year, departments=departments, years=years)

@app.route('/output/<int:oid>')
def output_detail(oid):
    conn=db(); row=conn.execute('SELECT o.*, u.name submitter FROM outputs o LEFT JOIN users u ON o.submitted_by=u.id WHERE o.id=?',(oid,)).fetchone()
    if not row or row['status']!='approved': abort(404)
    conn.execute('UPDATE outputs SET views=views+1 WHERE id=?',(oid,)); conn.commit(); conn.close()
    return render_template('detail.html', output=row)

@app.route('/download/<int:oid>')
def download(oid):
    conn=db(); row=conn.execute('SELECT * FROM outputs WHERE id=?',(oid,)).fetchone()
    if not row or row['status']!='approved': abort(404)
    if row['access_level']=='restricted' and not current_user():
        flash('This item is restricted. Please log in.'); return redirect(url_for('login'))
    if not row['file_name']: flash('This sample record has no attached file.'); return redirect(url_for('output_detail',oid=oid))
    conn.execute('UPDATE outputs SET downloads=downloads+1 WHERE id=?',(oid,)); conn.commit(); conn.close()
    return send_from_directory(UPLOADS,row['file_name'],as_attachment=True)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        name=request.form['name'].strip(); email=request.form['email'].strip().lower(); password=request.form['password']
        if not (email.endswith('@ui.edu.ng') or email.endswith('@dlc.ui.edu.ng')):
            flash('Use a University of Ibadan email address ending in @ui.edu.ng or @dlc.ui.edu.ng.')
            return render_template('register.html')
        if len(password)<8: flash('Password must be at least 8 characters.'); return render_template('register.html')
        conn=db()
        try:
            cur=conn.execute('INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',(name,email,hash_password(password),'depositor',datetime.utcnow().isoformat())); conn.commit(); uid=cur.lastrowid
        except sqlite3.IntegrityError:
            conn.close(); flash('An account with that email already exists.'); return render_template('register.html')
        conn.close(); session['user_id']=uid; flash('Account created.'); return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form['email'].strip().lower(); password=request.form['password']; conn=db(); u=conn.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone(); conn.close()
        if u and check_password(password,u['password_hash']): session['user_id']=u['id']; return redirect(request.args.get('next') or url_for('index'))
        flash('Invalid email or password.')
    return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('index'))

@app.route('/deposit', methods=['GET','POST'])
@login_required
def deposit():
    if request.method=='POST':
        f=request.files.get('file'); required=['title','authors','abstract','keywords','faculty','department','output_type','year','access_level']
        if any(not request.form.get(x,'').strip() for x in required): flash('Please complete all required fields.'); return render_template('deposit.html')
        year=request.form['year']
        if not year.isdigit() or not 1900 <= int(year) <= datetime.utcnow().year+1: flash('Enter a valid year.'); return render_template('deposit.html')
        stored=None
        if f and f.filename:
            ext=f.filename.rsplit('.',1)[-1].lower() if '.' in f.filename else ''
            if ext not in ALLOWED_EXT: flash('Allowed files: PDF, DOC, DOCX, TXT.'); return render_template('deposit.html')
            stored=uuid.uuid4().hex+'.'+ext; f.save(os.path.join(UPLOADS,stored))
        u=current_user(); conn=db(); cur=conn.execute('''INSERT INTO outputs(title,authors,abstract,keywords,faculty,department,output_type,year,file_name,access_level,status,submitted_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (request.form['title'],request.form['authors'],request.form['abstract'],request.form['keywords'],request.form['faculty'],request.form['department'],request.form['output_type'],int(year),stored,request.form['access_level'],'pending',u['id'],datetime.utcnow().isoformat())); oid=cur.lastrowid; conn.commit(); conn.close(); audit(u['id'],'deposit',oid); flash('Submission received and sent for librarian review.'); return redirect(url_for('my_outputs'))
    return render_template('deposit.html')

@app.route('/my-outputs')
@login_required
def my_outputs():
    u=current_user(); conn=db(); rows=conn.execute('SELECT * FROM outputs WHERE submitted_by=? ORDER BY id DESC',(u['id'],)).fetchall(); conn.close(); return render_template('my_outputs.html',outputs=rows)

@app.route('/admin')
@role_required('librarian','admin')
def admin():
    conn=db(); pending=conn.execute('SELECT o.*,u.name submitter FROM outputs o LEFT JOIN users u ON o.submitted_by=u.id WHERE o.status="pending" ORDER BY o.id DESC').fetchall(); stats=conn.execute('SELECT COUNT(*) total, COALESCE(SUM(views),0) views, COALESCE(SUM(downloads),0) downloads, (SELECT COUNT(*) FROM outputs WHERE status="pending") pending FROM outputs').fetchone(); conn.close(); return render_template('admin.html',pending=pending,stats=stats)

@app.route('/admin/moderate/<int:oid>', methods=['POST'])
@role_required('librarian','admin')
def moderate(oid):
    action=request.form.get('action'); note=request.form.get('note','').strip(); u=current_user()
    if action not in ('approve','reject'): abort(400)
    status='approved' if action=='approve' else 'rejected'; conn=db(); conn.execute('UPDATE outputs SET status=?, moderation_note=? WHERE id=?',(status,note,oid)); conn.commit(); conn.close(); audit(u['id'],action,oid); flash('Submission '+status+'.'); return redirect(url_for('admin'))

@app.route('/api/outputs')
def api_outputs():
    q=request.args.get('q','').strip(); faculty=request.args.get('faculty',''); department=request.args.get('department',''); author=request.args.get('author',''); output_type=request.args.get('output_type',''); year=request.args.get('year','')
    conn=db(); where=['status="approved"']; params=[]
    if q: where.append('(title LIKE ? OR authors LIKE ? OR keywords LIKE ? OR abstract LIKE ?)'); params += [f'%{q}%']*4
    if faculty: where.append('faculty=?'); params.append(faculty)
    if department: where.append('department LIKE ?'); params.append(f'%{department}%')
    if author: where.append('authors LIKE ?'); params.append(f'%{author}%')
    if output_type: where.append('output_type=?'); params.append(output_type)
    if year.isdigit(): where.append('year=?'); params.append(int(year))
    rows=conn.execute('SELECT id,title,authors,abstract,keywords,faculty,department,output_type,year,access_level,views,downloads FROM outputs WHERE '+' AND '.join(where)+' ORDER BY year DESC,id DESC',params).fetchall(); conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/outputs/<int:oid>')
def api_output(oid):
    conn=db(); r=conn.execute('SELECT id,title,authors,abstract,keywords,faculty,department,output_type,year,access_level,views,downloads FROM outputs WHERE id=? AND status="approved"',(oid,)).fetchone(); conn.close()
    if not r: return jsonify({'error':'Not found'}),404
    return jsonify(dict(r))

@app.route('/api/facets')
def api_facets():
    conn=db();
    data={
      'faculties':[dict(r) for r in conn.execute('SELECT faculty,COUNT(*) count FROM outputs WHERE status="approved" GROUP BY faculty ORDER BY faculty')],
      'types':[dict(r) for r in conn.execute('SELECT output_type,COUNT(*) count FROM outputs WHERE status="approved" GROUP BY output_type ORDER BY output_type')],
      'years':[dict(r) for r in conn.execute('SELECT year,COUNT(*) count FROM outputs WHERE status="approved" GROUP BY year ORDER BY year DESC')]
    }; conn.close(); return jsonify(data)

@app.route('/api/register', methods=['POST'])
def api_register():
    data=request.get_json(silent=True) or {}; name=data.get('name','').strip(); email=data.get('email','').strip().lower(); password=data.get('password','')
    if not (email.endswith('@ui.edu.ng') or email.endswith('@dlc.ui.edu.ng')) or len(password) < 8 or not name:
        return jsonify({'error':'Valid name, UI/DLC email and 8+ character password required'}),400
    conn=db()
    try: cur=conn.execute('INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',(name,email,hash_password(password),'depositor',datetime.utcnow().isoformat())); conn.commit(); uid=cur.lastrowid
    except sqlite3.IntegrityError: conn.close(); return jsonify({'error':'Email already registered'}),409
    conn.close(); return jsonify({'id':uid,'message':'registered'}),201

@app.route('/oai')
def oai():
    verb=request.args.get('verb','Identify')
    if verb=='Identify': return jsonify({'repositoryName':'UI-ScholarHub','protocolVersion':'2.0','metadataPrefix':'oai_dc'})
    conn=db()
    if verb=='ListRecords':
        rows=conn.execute('SELECT id,title,authors,abstract,year,output_type FROM outputs WHERE status="approved" ORDER BY id').fetchall(); conn.close()
        return jsonify({'metadataPrefix':'oai_dc','records':[{'identifier':f'oai:ui-scholarhub:{r["id"]}','title':r['title'],'creator':r['authors'],'description':r['abstract'],'date':str(r['year']),'type':r['output_type']} for r in rows]})
    if verb=='ListSets':
        rows=conn.execute('SELECT DISTINCT faculty FROM outputs WHERE status="approved" ORDER BY faculty').fetchall(); conn.close(); return jsonify({'sets':[r['faculty'] for r in rows]})
    if verb=='ListMetadataFormats': conn.close(); return jsonify({'metadataFormats':['oai_dc']})
    if verb=='ListIdentifiers':
        rows=conn.execute('SELECT id FROM outputs WHERE status="approved" ORDER BY id').fetchall(); conn.close(); return jsonify({'identifiers':[f'oai:ui-scholarhub:{r["id"]}' for r in rows]})
    conn.close(); return jsonify({'error':'Unsupported verb in prototype'}),400

@app.route('/manifest.json')
def manifest(): return jsonify({'name':'UI-ScholarHub','short_name':'ScholarHub','start_url':'/','display':'standalone','description':'University of Ibadan research outputs repository'})

@app.errorhandler(403)
def forbidden(e): return render_template('error.html',code=403,message='You do not have permission to access this page.'),403
@app.errorhandler(404)
def not_found(e): return render_template('error.html',code=404,message='The requested resource was not found.'),404

init_db()
if __name__=='__main__': app.run(debug=True)
