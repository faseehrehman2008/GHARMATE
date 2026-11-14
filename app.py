import os, json
from datetime import date, datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from database import init_db, get_db

app=Flask(__name__)
app.config['SECRET_KEY']=os.environ.get('GHARMATE_SECRET') or os.environ.get('HOMEMATE_SECRET') or 'local-development-only-change-before-deploy'
if os.environ.get('RENDER') and app.config['SECRET_KEY']=='local-development-only-change-before-deploy':
    raise RuntimeError('Set GHARMATE_SECRET in the hosting environment before deploying.')
init_db()

def login_required(fn):
    @wraps(fn)
    def wrapped(*a,**kw):
        if 'user_id' not in session: return redirect(url_for('login'))
        return fn(*a,**kw)
    return wrapped
def admin_required(fn):
    @wraps(fn)
    def wrapped(*a,**kw):
        if session.get('role')!='admin': flash('Only the administrator can do that.','error'); return redirect(url_for('dashboard'))
        return fn(*a,**kw)
    return wrapped
@app.context_processor
def inject_user(): return {'current_name':session.get('name'),'current_role':session.get('role')}
@app.route('/')
def index(): return redirect(url_for('dashboard') if 'user_id' in session else url_for('login'))
@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        with get_db() as db: user=db.execute('SELECT * FROM users WHERE username=?',(request.form.get('username','').strip(),)).fetchone()
        if user and check_password_hash(user['password_hash'],request.form.get('password','')):
            session.update(user_id=user['id'],name=user['name'],role=user['role'],lang=user['language']); return redirect(url_for('dashboard'))
        flash('Incorrect username or password.','error')
    return render_template('login.html')
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))
@app.route('/language/<lang>')
@login_required
def language(lang):
    if lang in ('en','ur'):
        with get_db() as db: db.execute('UPDATE users SET language=? WHERE id=?',(lang,session['user_id']))
        session['lang']=lang
    return redirect(request.referrer or url_for('dashboard'))
@app.route('/dashboard')
@login_required
def dashboard():
    with get_db() as db:
        chores=db.execute('SELECT c.*,u.name AS member_name FROM chores c LEFT JOIN users u ON u.id=c.assigned_to ORDER BY c.done,c.due_date LIMIT 8').fetchall()
        events=db.execute('SELECT * FROM events ORDER BY event_date LIMIT 6').fetchall()
        announcements=db.execute('SELECT a.*,u.name AS author FROM announcements a JOIN users u ON u.id=a.created_by ORDER BY a.created_at DESC LIMIT 5').fetchall()
        members=db.execute('SELECT id,name,role FROM users ORDER BY name').fetchall()
        away=db.execute("SELECT o.*,u.name AS member_name FROM outings o JOIN users u ON u.id=o.user_id WHERE o.status='away' ORDER BY o.departure_at DESC").fetchall()
        polls=db.execute('SELECT * FROM polls WHERE is_closed=0 ORDER BY created_at DESC LIMIT 4').fetchall()
    return render_template('dashboard.html',chores=chores,events=events,announcements=announcements,members=members,today=date.today(),away=away,open_polls=polls)
@app.route('/family',methods=['GET','POST'])
@login_required
@admin_required
def family():
    if request.method=='POST':
        name=request.form.get('name','').strip(); username=request.form.get('username','').strip(); password=request.form.get('password','')
        if not name or not username or len(password)<8: flash('Enter name, username and password (at least 8 characters).','error')
        else:
            try:
                with get_db() as db: db.execute("INSERT INTO users(name,username,password_hash,role,language) VALUES(?,?,?,'member','en')",(name,username,generate_password_hash(password)))
                flash(f'Account created for {name}.','success')
            except Exception: flash('That username is already in use.','error')
        return redirect(url_for('family'))
    with get_db() as db: members=db.execute('SELECT id,name,username,role,language FROM users ORDER BY name').fetchall()
    return render_template('family.html',members=members)
@app.route('/timetable',methods=['GET','POST'])
@login_required
def timetable():
    if request.method=='POST':
        with get_db() as db: db.execute('INSERT INTO timetable(title,activity_time,days,notes,created_by) VALUES(?,?,?,?,?)',(request.form['title'],request.form['activity_time'],request.form.get('days','Every day'),request.form.get('notes',''),session['user_id']))
        flash('Activity added.','success'); return redirect(url_for('timetable'))
    with get_db() as db: rows=db.execute('SELECT t.*,u.name AS creator FROM timetable t JOIN users u ON u.id=t.created_by ORDER BY activity_time').fetchall()
    return render_template('timetable.html',rows=rows)
@app.route('/chores',methods=['GET','POST'])
@login_required
def chores():
    if request.method=='POST':
        with get_db() as db: db.execute('INSERT INTO chores(title,assigned_to,due_date,notes,created_by) VALUES(?,?,?,?,?)',(request.form['title'],request.form.get('assigned_to') or None,request.form.get('due_date') or None,request.form.get('notes',''),session['user_id']))
        flash('Chore assigned.','success'); return redirect(url_for('chores'))
    with get_db() as db:
        rows=db.execute('SELECT c.*,u.name AS member_name FROM chores c LEFT JOIN users u ON u.id=c.assigned_to ORDER BY c.done,c.due_date').fetchall()
        members=db.execute('SELECT id,name FROM users ORDER BY name').fetchall()
        rules=db.execute('SELECT * FROM chore_rotation_rules WHERE active=1 ORDER BY id DESC').fetchall()
    return render_template('chores.html',rows=rows,members=members,rules=rules)
@app.route('/chores/<int:chore_id>/toggle',methods=['POST'])
@login_required
def toggle_chore(chore_id):
    with get_db() as db: db.execute('UPDATE chores SET done=CASE done WHEN 0 THEN 1 ELSE 0 END WHERE id=?',(chore_id,))
    return redirect(url_for('chores'))
@app.route('/chores/rotation',methods=['POST'])
@login_required
@admin_required
def create_rotation():
    title=request.form.get('title','').strip(); ids=[int(x) for x in request.form.getlist('member_ids') if x.isdigit()]; frequency=request.form.get('frequency','weekly')
    if not title or not ids or frequency not in ('daily','weekly','monthly'): flash('Enter a chore, select members and choose a valid frequency.','error')
    else:
        with get_db() as db: db.execute('INSERT INTO chore_rotation_rules(title,member_ids,frequency,next_due_date,created_by) VALUES(?,?,?,?,?)',(title,json.dumps(ids),frequency,date.today().isoformat(),session['user_id']))
        flash('Chore rotation created.','success')
    return redirect(url_for('chores'))
@app.route('/chores/rotation/<int:rule_id>/run',methods=['POST'])
@login_required
@admin_required
def run_rotation(rule_id):
    with get_db() as db:
        rule=db.execute('SELECT * FROM chore_rotation_rules WHERE id=? AND active=1',(rule_id,)).fetchone()
        if not rule: flash('Rotation not found.','error')
        else:
            ids=json.loads(rule['member_ids']); last=rule['last_assigned_to']; idx=(ids.index(last)+1)%len(ids) if last in ids else 0; assigned=ids[idx]
            delta={'daily':timedelta(days=1),'weekly':timedelta(days=7),'monthly':timedelta(days=30)}[rule['frequency']]
            due=date.today()+delta
            db.execute('INSERT INTO chores(title,assigned_to,due_date,notes,created_by) VALUES(?,?,?,?,?)',(rule['title'],assigned,due.isoformat(),'Automatically assigned by chore rotation',session['user_id']))
            db.execute('UPDATE chore_rotation_rules SET last_assigned_to=?,next_due_date=? WHERE id=?',(assigned,due.isoformat(),rule_id)); flash('Next rotation chore assigned.','success')
    return redirect(url_for('chores'))
@app.route('/calendar',methods=['GET','POST'])
@login_required
def calendar():
    if request.method=='POST':
        with get_db() as db: db.execute('INSERT INTO events(title,event_date,event_time,details,created_by,event_type,person_id) VALUES(?,?,?,?,?,?,?)',(request.form['title'],request.form['event_date'],request.form.get('event_time',''),request.form.get('details',''),session['user_id'],request.form.get('event_type','general'),request.form.get('person_id') or None))
        flash('Family event added.','success'); return redirect(url_for('calendar'))
    with get_db() as db:
        rows=db.execute('SELECT e.*,u.name AS creator,p.name AS person_name FROM events e JOIN users u ON u.id=e.created_by LEFT JOIN users p ON p.id=e.person_id ORDER BY event_date,event_time').fetchall()
        members=db.execute('SELECT id,name FROM users ORDER BY name').fetchall()
    return render_template('calendar.html',rows=rows,members=members)
@app.route('/prayers',methods=['GET','POST'])
@login_required
def prayers():
    names=['Fajr','Dhuhr','Asr','Maghrib','Isha']
    if request.method=='POST':
        with get_db() as db:
            for name in names: db.execute('INSERT INTO prayer_times(prayer_name,prayer_time,updated_by) VALUES(?,?,?) ON CONFLICT(prayer_name) DO UPDATE SET prayer_time=excluded.prayer_time,updated_by=excluded.updated_by',(name,request.form.get(name,''),session['user_id']))
        flash('Prayer times saved.','success'); return redirect(url_for('prayers'))
    with get_db() as db: times={r['prayer_name']:r['prayer_time'] for r in db.execute('SELECT * FROM prayer_times').fetchall()}
    return render_template('prayers.html',names=names,times=times)
@app.route('/announcements',methods=['GET','POST'])
@login_required
def announcements():
    if request.method=='POST':
        with get_db() as db: db.execute('INSERT INTO announcements(title,message,created_by) VALUES(?,?,?)',(request.form['title'],request.form['message'],session['user_id']))
        flash('Announcement published.','success'); return redirect(url_for('announcements'))
    with get_db() as db: rows=db.execute('SELECT a.*,u.name AS author FROM announcements a JOIN users u ON u.id=a.created_by ORDER BY created_at DESC').fetchall()
    return render_template('announcements.html',rows=rows)
@app.route('/polls',methods=['GET','POST'])
@login_required
def polls():
    if request.method=='POST':
        q=request.form.get('question','').strip(); opts=[x.strip() for x in request.form.get('options','').splitlines() if x.strip()]
        if not q or len(opts)<2: flash('A poll needs a question and at least two options.','error')
        else:
            with get_db() as db:
                db.execute('INSERT INTO polls(question,description,closes_at,created_by) VALUES(?,?,?,?)',(q,request.form.get('description',''),request.form.get('closes_at') or None,session['user_id']))
                pid=db.execute('SELECT id FROM polls ORDER BY id DESC LIMIT 1').fetchone()['id']
                for opt in opts: db.execute('INSERT INTO poll_options(poll_id,option_text) VALUES(?,?)',(pid,opt))
            flash('Poll created.','success')
        return redirect(url_for('polls'))
    with get_db() as db:
        allpolls=db.execute('SELECT p.*,u.name AS creator FROM polls p JOIN users u ON u.id=p.created_by ORDER BY p.created_at DESC').fetchall(); data=[]
        for p in allpolls:
            options=db.execute('SELECT o.id,o.option_text,COUNT(v.id) AS votes FROM poll_options o LEFT JOIN poll_votes v ON v.option_id=o.id WHERE o.poll_id=? GROUP BY o.id,o.option_text ORDER BY o.id',(p['id'],)).fetchall()
            mine=db.execute('SELECT option_id FROM poll_votes WHERE poll_id=? AND user_id=?',(p['id'],session['user_id'])).fetchone()
            data.append({'poll':p,'options':options,'my_vote':mine['option_id'] if mine else None})
    return render_template('polls.html',polls=data)
@app.route('/polls/<int:poll_id>/vote',methods=['POST'])
@login_required
def vote_poll(poll_id):
    oid=request.form.get('option_id','')
    with get_db() as db:
        poll=db.execute('SELECT * FROM polls WHERE id=?',(poll_id,)).fetchone(); valid=db.execute('SELECT id FROM poll_options WHERE id=? AND poll_id=?',(oid,poll_id)).fetchone()
        if not poll or poll['is_closed'] or not valid: flash('This poll is closed or the option is invalid.','error')
        else:
            try: db.execute('INSERT INTO poll_votes(poll_id,option_id,user_id) VALUES(?,?,?)',(poll_id,oid,session['user_id'])); flash('Your vote has been recorded.','success')
            except Exception: flash('You have already voted in this poll.','error')
    return redirect(url_for('polls'))
@app.route('/polls/<int:poll_id>/close',methods=['POST'])
@login_required
@admin_required
def close_poll(poll_id):
    with get_db() as db: db.execute('UPDATE polls SET is_closed=1 WHERE id=?',(poll_id,))
    flash('Poll closed.','success'); return redirect(url_for('polls'))
@app.route('/outings',methods=['GET','POST'])
@login_required
def outings():
    if request.method=='POST':
        with get_db() as db: db.execute("INSERT INTO outings(user_id,destination,purpose,departure_at,expected_return_at,status) VALUES(?,?,?,?,?,'away')",(session['user_id'],request.form['destination'],request.form.get('purpose',''),request.form['departure_at'],request.form.get('expected_return_at') or None))
        flash('Your outing has been recorded.','success'); return redirect(url_for('outings'))
    with get_db() as db:
        rows=db.execute('SELECT o.*,u.name AS member_name FROM outings o JOIN users u ON u.id=o.user_id ORDER BY o.created_at DESC').fetchall()
    return render_template('outings.html',rows=rows)
@app.route('/outings/<int:outing_id>/return',methods=['POST'])
@login_required
def return_outing(outing_id):
    with get_db() as db:
        row=db.execute('SELECT * FROM outings WHERE id=?',(outing_id,)).fetchone()
        if row and (row['user_id']==session['user_id'] or session.get('role')=='admin'): db.execute("UPDATE outings SET status='returned',actual_return_at=? WHERE id=?",(datetime.now().isoformat(timespec='minutes'),outing_id)); flash('Return marked.','success')
        else: flash('You cannot update this outing.','error')
    return redirect(url_for('outings'))
@app.route('/emergency',methods=['GET','POST'])
@login_required
def emergency():
    if request.method=='POST':
        if session.get('role')!='admin': flash('Only the administrator can add emergency contacts.','error')
        else:
            with get_db() as db: db.execute('INSERT INTO emergency_contacts(title,contact_name,phone,address,instructions,created_by) VALUES(?,?,?,?,?,?)',(request.form['title'],request.form.get('contact_name',''),request.form.get('phone',''),request.form.get('address',''),request.form.get('instructions',''),session['user_id']))
            flash('Emergency contact saved.','success')
        return redirect(url_for('emergency'))
    with get_db() as db: rows=db.execute('SELECT * FROM emergency_contacts ORDER BY id DESC').fetchall()
    return render_template('emergency.html',rows=rows)
@app.route('/emergency/<int:contact_id>/delete',methods=['POST'])
@login_required
@admin_required
def delete_emergency(contact_id):
    with get_db() as db: db.execute('DELETE FROM emergency_contacts WHERE id=?',(contact_id,))
    flash('Contact deleted.','success'); return redirect(url_for('emergency'))
@app.route('/visitors',methods=['GET','POST'])
@login_required
def visitors():
    if request.method=='POST':
        with get_db() as db: db.execute('INSERT INTO visitors(visitor_name,phone,purpose,host_id,expected_at,notes,created_by) VALUES(?,?,?,?,?,?,?)',(request.form['visitor_name'],request.form.get('phone',''),request.form.get('purpose',''),request.form.get('host_id') or None,request.form.get('expected_at') or None,request.form.get('notes',''),session['user_id']))
        flash('Visitor entry saved.','success'); return redirect(url_for('visitors'))
    with get_db() as db:
        rows=db.execute('SELECT v.*,u.name AS host_name FROM visitors v LEFT JOIN users u ON u.id=v.host_id ORDER BY v.created_at DESC').fetchall(); members=db.execute('SELECT id,name FROM users ORDER BY name').fetchall()
    return render_template('visitors.html',rows=rows,members=members)
@app.route('/visitors/<int:visitor_id>/<action>',methods=['POST'])
@login_required
def visitor_status(visitor_id,action):
    if action not in ('arrive','depart'): return redirect(url_for('visitors'))
    with get_db() as db:
        row=db.execute('SELECT * FROM visitors WHERE id=?',(visitor_id,)).fetchone()
        if row and (session.get('role')=='admin' or row['created_by']==session['user_id']):
            col='arrived_at' if action=='arrive' else 'departed_at'; db.execute(f'UPDATE visitors SET {col}=? WHERE id=?',(datetime.now().isoformat(timespec='minutes'),visitor_id)); flash('Visitor status updated.','success')
        else: flash('You cannot update this visitor record.','error')
    return redirect(url_for('visitors'))
@app.route('/assistant',methods=['GET','POST'])
@login_required
def assistant():
    answer=None
    if request.method=='POST':
        question=request.form.get('question','').lower()
        with get_db() as db:
            if any(w in question for w in ('chore','task','safai','kaam')):
                rows=db.execute('SELECT c.title,c.due_date,c.done,u.name AS member FROM chores c LEFT JOIN users u ON u.id=c.assigned_to ORDER BY c.done,c.due_date LIMIT 10').fetchall(); answer='Chore summary: '+('; '.join(f"{r['title']} — {r['member'] or 'Unassigned'} — {'Done' if r['done'] else 'Pending'}" for r in rows) if rows else 'No chores are listed yet.')
            elif any(w in question for w in ('outing','away','bahar')):
                rows=db.execute("SELECT u.name,o.destination,o.expected_return_at FROM outings o JOIN users u ON u.id=o.user_id WHERE o.status='away'").fetchall(); answer='Currently away: '+('; '.join(f"{r['name']} at {r['destination']} (expected return: {r['expected_return_at'] or 'not set'})" for r in rows) if rows else 'No family member is marked as away.')
            elif any(w in question for w in ('event','birthday','anniversary')):
                rows=db.execute('SELECT title,event_date,event_type FROM events ORDER BY event_date LIMIT 10').fetchall(); answer='Upcoming events: '+('; '.join(f"{r['title']} on {r['event_date']} ({r['event_type']})" for r in rows) if rows else 'No events are listed.')
            elif any(w in question for w in ('poll','vote')):
                rows=db.execute('SELECT question,is_closed FROM polls ORDER BY created_at DESC LIMIT 8').fetchall(); answer='Family polls: '+('; '.join(f"{r['question']} — {'Closed' if r['is_closed'] else 'Open'}" for r in rows) if rows else 'No polls have been created.')
            elif any(w in question for w in ('visitor','guest','mehmaan')):
                rows=db.execute('SELECT visitor_name,arrived_at,departed_at FROM visitors ORDER BY created_at DESC LIMIT 8').fetchall(); answer='Recent visitors: '+('; '.join(f"{r['visitor_name']} — {'departed' if r['departed_at'] else 'arrived' if r['arrived_at'] else 'expected/not checked in'}" for r in rows) if rows else 'No visitor records found.')
            elif any(w in question for w in ('member','family','who')):
                rows=db.execute('SELECT name,role FROM users ORDER BY name').fetchall(); answer='Family members: '+(', '.join(r['name'] for r in rows) if rows else 'No members found.')
            else: answer='I can help with chores, outings, family events and birthdays, polls, visitors, and family members. Try asking: “Who is currently away?”'
    return render_template('assistant.html',answer=answer)
if __name__=='__main__': app.run(host='0.0.0.0',port=5000,debug=False)
