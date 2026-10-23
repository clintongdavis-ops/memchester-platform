"""Memchester Soccer finances. Python 3.12+, no external dependencies."""
import csv, hashlib, hmac, html, io, os, secrets, sqlite3, time
from datetime import date
from decimal import Decimal, InvalidOperation
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs

DATA = Path(os.environ.get('MEMCHESTER_DATA', str(Path(__file__).parent / 'data')))
DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
DB = DATA / 'finance.sqlite3'
SESSIONS = {}
ATTEMPTS = {}
CATEGORIES = ['Membership fees','Sponsorship','Fundraising','Donations','Pitch hire','Referees','Equipment','Travel','Other']

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

with db() as c:
    c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, digest TEXT NOT NULL, owner INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY, day TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL, cents INTEGER NOT NULL, author INTEGER NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);''')
os.chmod(DB, 0o600)

def digest(pin, salt):
    return hashlib.pbkdf2_hmac('sha256', pin.encode(), bytes.fromhex(salt), 300000).hex()

def esc(s): return html.escape(str(s), quote=True)
def money(n): return f'{n / 100:,.2f}'

STYLE = '''*{box-sizing:border-box}body{margin:0;background:#f3f5f2;color:#172c25;font:16px system-ui}header{background:#143e32;color:white;padding:24px 5%;display:flex;justify-content:space-between;align-items:center}main{max-width:1100px;margin:32px auto;padding:0 20px}h1{font-size:25px;margin:0}h2{font-size:20px}small{color:#65756d}header small{color:#bbd3c5}section,.card{background:white;border:1px solid #dbe3dd;border-radius:14px;padding:24px;margin:20px 0}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.stats strong{font-size:28px;display:block;margin-top:12px}.stats .card{margin:0}input,select,button{font:inherit;border:1px solid #bbc9c0;border-radius:7px;padding:11px;max-width:100%}label{display:block;font-size:14px;margin:12px 0}label input,label select{display:block;width:100%;margin-top:5px}button,.button{background:#176044;color:white;cursor:pointer;text-decoration:none;border:0;border-radius:7px;padding:11px 17px;display:inline-block}form.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;align-items:end}.table{overflow:auto}table{border-collapse:collapse;width:100%;white-space:nowrap}td,th{text-align:left;border-bottom:1px solid #e4e9e5;padding:13px 9px}.negative{color:#a13434}.notice{background:#fff2d5;padding:15px;border-radius:8px}.login{max-width:460px}a{color:#176044}header a{color:white}.inline{display:inline}footer{margin:25px 0;color:#65756d;font-size:13px}@media(max-width:700px){.stats,form.grid{grid-template-columns:1fr}header{gap:20px;align-items:start}.stats strong{font-size:24px}}'''

class App(BaseHTTPRequestHandler):
    def log_message(self, *args): pass  # Do not log credentials or transaction descriptions.
    def send(self, content, status=200, kind='text/html; charset=utf-8', cookie=None):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(content.encode())
    def page(self, body, status=200):
        self.send(f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Memchester Soccer · Finances</title><style>{STYLE}</style><header><div><small>MEMCHESTER SOCCER</small><h1>Club finances</h1></div><a href="/">Dashboard</a></header><main>{body}<footer>Amounts use your selected currency. Balance reflects recorded transactions, not a bank connection.</footer></main></html>',status)
    def session(self):
        cookies = dict(p.strip().split('=',1) for p in self.headers.get('Cookie','').split(';') if '=' in p)
        token=cookies.get('session','')
        s=SESSIONS.get(token)
        if s and s['expires'] > time.time():
            with db() as c: user=c.execute('SELECT * FROM users WHERE id=? AND active=1',(s['uid'],)).fetchone()
            if user: return s, user
        return None, None
    def redirect(self, cookie=None):
        self.send_response(303); self.send_header('Location','/')
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers()
    def csrf(self, s): return f'<input type="hidden" name="csrf" value="{s["csrf"]}">'
    def do_GET(self):
        s,u=self.session()
        with db() as c: count=c.execute('SELECT count(*) FROM users').fetchone()[0]
        if not count:
            token=secrets.token_urlsafe(24)
            SESSIONS[token]={'csrf':secrets.token_urlsafe(24),'uid':None,'expires':time.time()+1800}
            form=f'<section class="login"><h2>Create your owner account</h2><p>Use your email as your login name and a private PIN of at least 8 digits. Email delivery is not enabled.</p><form action="/setup" method="post">{self.csrf(SESSIONS[token])}<label>Email<input type="email" name="email" required></label><label>PIN<input type="password" name="pin" pattern="[0-9]{{8,32}}" minlength="8" maxlength="32" required autocomplete="new-password"></label><label>Currency code<input name="currency" value="GBP" pattern="[A-Za-z]{{3}}" maxlength="3" required></label><button>Create account</button></form></section>'
            self.send_response(200); self.send_header('Set-Cookie',f'setup={token}; HttpOnly; SameSite=Strict; Path=/'); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.end_headers()
            self.wfile.write(f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Memchester setup</title><style>{STYLE}</style><main>{form}</main></html>'.encode()); return
        if not u:
            self.page('<section class="login"><h2>Welcome back</h2><p>Sign in with the email and PIN assigned by the club owner.</p><form method="post" action="/login"><label>Email<input type="email" name="email" required autocomplete="username"></label><label>PIN<input type="password" name="pin" required autocomplete="current-password"></label><button>Sign in</button></form></section>'); return
        with db() as c:
            rows=c.execute('SELECT * FROM transactions ORDER BY day DESC,id DESC').fetchall()
            currency=c.execute("SELECT value FROM settings WHERE key='currency'").fetchone()[0]
            users=c.execute('SELECT id,email,owner,active FROM users').fetchall()
        if self.path=='/export.csv':
            out=io.StringIO(); w=csv.writer(out); w.writerow(['Date','Description','Category','Amount', 'Currency'])
            for r in rows:
                safe=lambda x: "'"+x if x.startswith(('=','+','-','@','\t','\r','\n')) else x
                w.writerow([r['day'],safe(r['description']),safe(r['category']),f'{Decimal(r["cents"])/100:.2f}',currency])
            self.send(out.getvalue(),kind='text/csv; charset=utf-8'); return
        incoming=sum(r['cents'] for r in rows if r['cents']>0); outgoing=-sum(r['cents'] for r in rows if r['cents']<0)
        body=f'<p>Signed in as {esc(u["email"])} · {esc(currency)} <form class="inline" method="post" action="/logout">{self.csrf(s)}<button>Sign out</button></form></p><div class="stats">'+''.join(f'<div class="card">{label}<strong>{money(n)}</strong></div>' for label,n in [('Recorded balance',incoming-outgoing),('Total income',incoming),('Total expenses',outgoing)])+'</div>'
        options=''.join(f'<option>{esc(x)}</option>' for x in CATEGORIES)
        body+=f'<section><h2>Add a transaction</h2><form class="grid" action="/transaction" method="post">{self.csrf(s)}<label>Date<input type="date" name="day" value="{date.today()}" required></label><label>Description<input name="description" maxlength="300" required placeholder="e.g. October pitch hire"></label><label>Category<select name="category">{options}</select></label><label>Type<select name="kind"><option value="income">Income</option><option value="expense">Expense</option></select></label><label>Amount ({esc(currency)})<input type="number" name="amount" min="0.01" max="999999999.99" step="0.01" required></label><button>Add transaction</button></form></section>'
        body+='<section><h2>Transactions</h2><a class="button" href="/export.csv">Export CSV</a><div class="table"><table><tr><th>Date</th><th>Description</th><th>Category</th><th>Amount</th></tr>'
        for r in rows: body+=f'<tr><td>{esc(r["day"])}</td><td>{esc(r["description"])}</td><td>{esc(r["category"])}</td><td class="{"negative" if r["cents"]<0 else ""}">{money(r["cents"])}</td></tr>'
        body+='</table></div>'+('' if rows else '<p>No transactions yet. Add your first income or expense above. To record an opening balance, use an “Other” transaction dated before your first entry.</p>')+'</section>'
        if u['owner']:
            body+=f'<section><h2>Access portal</h2><p>People you add can view finances, add transactions and export records. Only you can manage access. Share the PIN privately; adding an email does not send an invitation.</p><form class="grid" action="/invite" method="post">{self.csrf(s)}<label>Email<input type="email" name="email" required></label><label>New PIN (8–32 digits)<input type="password" name="pin" pattern="[0-9]{{8,32}}" required autocomplete="new-password"></label><button>Add person / reset PIN</button></form><ul>'
            for user in users:
                body+=f'<li>{esc(user["email"])} — {"Owner" if user["owner"] else ("Active" if user["active"] else "Revoked")}'
                if not user['owner'] and user['active']: body+=f' <form class="inline" action="/revoke" method="post">{self.csrf(s)}<input type="hidden" name="id" value="{user["id"]}"><button>Revoke</button></form>'
                body+='</li>'
            body+='</ul></section>'
        self.page(body)
    def do_POST(self):
        try: self.post()
        except (ValueError, InvalidOperation): self.page('<section><h2>Check your entry</h2><p>Use a valid email, an 8–32 digit PIN, a valid date and a positive amount with at most two decimal places.</p><a href="/">Return</a></section>',400)
    def post(self):
        length=int(self.headers.get('Content-Length','0'))
        if not 0<length<=8192: self.send('Invalid request',400); return
        f={k:v[0] for k,v in parse_qs(self.rfile.read(length).decode()).items()}
        s,u=self.session()
        if self.path=='/setup':
            cookies=dict(p.strip().split('=',1) for p in self.headers.get('Cookie','').split(';') if '=' in p)
            setup=SESSIONS.get(cookies.get('setup',''))
            if not setup or setup['expires']<time.time() or not hmac.compare_digest(f.get('csrf',''),setup['csrf']): self.send('Invalid setup session',403); return
            email,pin=self.credentials(f); currency=f.get('currency','').upper()
            if len(currency)!=3 or not currency.isascii() or not currency.isalpha(): raise ValueError()
            salt=secrets.token_hex(16)
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                if c.execute('SELECT count(*) FROM users').fetchone()[0]: self.send('Already initialized',409); return
                c.execute('INSERT INTO users(email,salt,digest,owner) VALUES(?,?,?,1)',(email,salt,digest(pin,salt)))
                c.execute('INSERT INTO settings VALUES(?,?)',('currency',currency))
            self.redirect(); return
        if self.path=='/login':
            key=self.client_address[0]; now=time.time(); recent=[t for t in ATTEMPTS.get(key,[]) if t>now-900]; ATTEMPTS[key]=recent
            if len(recent)>=10: self.send('Too many attempts. Try again in 15 minutes.',429); return
            recent.append(now)
            with db() as c: user=c.execute('SELECT * FROM users WHERE email=? AND active=1',(f.get('email','').strip().lower(),)).fetchone()
            salt=user['salt'] if user else '00'*16
            candidate=digest(f.get('pin','')[:128],salt)
            if not user or not hmac.compare_digest(candidate,user['digest']): self.page('<p>Email or PIN not recognized.</p><a href="/">Try again</a>',401); return
            token=secrets.token_urlsafe(32); SESSIONS[token]={'uid':user['id'],'csrf':secrets.token_urlsafe(24),'expires':now+8*3600}
            secure='; Secure' if os.environ.get('MEMCHESTER_SECURE_COOKIE')=='1' else ''
            self.redirect(f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{secure}'); return
        if not u or not hmac.compare_digest(s['csrf'],f.get('csrf','')): self.send('Sign in again or reload the form.',403); return
        if self.path=='/logout':
            s['expires']=0; self.redirect('session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'); return
        if self.path=='/transaction':
            day=date.fromisoformat(f.get('day','')).isoformat(); description=f.get('description','').strip(); category=f.get('category',''); amount=Decimal(f.get('amount',''))
            if not description or len(description)>300 or category not in CATEGORIES or not amount.is_finite() or not 0<amount<=Decimal('999999999.99') or amount*100!=(amount*100).to_integral_value() or f.get('kind') not in ('income','expense'): raise ValueError()
            cents=int(amount*100)*(1 if f['kind']=='income' else -1)
            with db() as c: c.execute('INSERT INTO transactions(day,description,category,cents,author) VALUES(?,?,?,?,?)',(day,description,category,cents,u['id']))
        elif self.path in ('/invite','/revoke'):
            if not u['owner']: self.send('Owner access required',403); return
            with db() as c:
                if self.path=='/revoke': c.execute('UPDATE users SET active=0 WHERE id=? AND owner=0',(int(f.get('id','0')),))
                else:
                    email,pin=self.credentials(f); salt=secrets.token_hex(16)
                    old=c.execute('SELECT id,owner FROM users WHERE email=?',(email,)).fetchone()
                    if old and old['owner']: self.send('Owner account cannot be changed here.',400); return
                    c.execute('INSERT INTO users(email,salt,digest) VALUES(?,?,?) ON CONFLICT(email) DO UPDATE SET salt=excluded.salt,digest=excluded.digest,active=1',(email,salt,digest(pin,salt)))
                    if old:
                        for session in SESSIONS.values():
                            if session['uid']==old['id']: session['expires']=0
        else: self.send('Not found',404); return
        self.redirect()
    def credentials(self,f):
        email=f.get('email','').strip().lower(); pin=f.get('pin','')
        if '@' not in email or len(email)>254 or not pin.isascii() or not pin.isdigit() or not 8<=len(pin)<=32: raise ValueError()
        return email,pin

if __name__=='__main__':
    server=ThreadingHTTPServer((os.environ.get('MEMCHESTER_HOST','127.0.0.1'),int(os.environ.get('PORT','8000'))),App)
    print('Memchester finance server started.',flush=True)
    server.serve_forever()
