import os, csv, io, sqlite3, math
from sklearn.tree import DecisionTreeClassifier
from datetime import date, datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, make_response, abort
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
app = Flask(__name__, instance_path=os.path.join(BASE_DIR, "instance"))
app.config.update(SECRET_KEY=os.environ.get("MEDITRACK_SECRET_KEY", "change-this-demo-key-before-deployment"),
                  DATABASE=os.path.join(app.instance_path, "meditrack.sqlite3"),
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
csrf = CSRFProtect(app)

def connect_db():
    db = sqlite3.connect(app.config["DATABASE"])
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db

def init_db():
    db = connect_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
      full_name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'staff', active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS medicines(id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
      manufacturer TEXT DEFAULT '', batch_number TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0),
      min_stock INTEGER NOT NULL DEFAULT 10 CHECK(min_stock>=0), unit_price REAL NOT NULL DEFAULT 0 CHECK(unit_price>=0),
      manufacturing_date TEXT, expiry_date TEXT NOT NULL, supplier TEXT DEFAULT '', description TEXT DEFAULT '',
      created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS stock_movements(id INTEGER PRIMARY KEY, medicine_id INTEGER NOT NULL REFERENCES medicines(id) ON DELETE CASCADE,
      movement_type TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0), reason TEXT DEFAULT '', username TEXT NOT NULL,
      created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS activity_logs(id INTEGER PRIMARY KEY, message TEXT NOT NULL, kind TEXT DEFAULT 'info', created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS prediction_history(id INTEGER PRIMARY KEY, medicine_id INTEGER REFERENCES medicines(id) ON DELETE SET NULL,
      avg_daily REAL NOT NULL, predicted_days REAL, created_at TEXT NOT NULL);
    """)
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        db.execute("INSERT INTO users(username,password_hash,full_name,role,active,created_at) VALUES(?,?,?,?,1,?)",
                   ("admin", generate_password_hash("Admin@123"), "Administrator", "admin", datetime.now().isoformat(timespec="seconds")))
    if db.execute("SELECT COUNT(*) FROM medicines").fetchone()[0] == 0:
        today = date.today()
        samples = [
          ("Amoxicillin 500mg","Antibiotics","MedLabs","AMX-2401",5,20,2.5,(today+timedelta(days=18)).isoformat(),"HealthPlus"),
          ("Paracetamol 650mg","Analgesics","WellCare","PCM-2308",128,30,0.8,(today+timedelta(days=120)).isoformat(),"City Pharma"),
          ("Metformin 500mg","Cardiovascular","NovaMed","MET-4412",18,50,1.2,(today+timedelta(days=240)).isoformat(),"HealthPlus"),
          ("Ceftriaxone 1g","Antibiotics","MedLabs","CFT-9810",42,15,7.5,(today+timedelta(days=6)).isoformat(),"Care Supply"),
          ("Vitamin D3","Vitamins & Supplements","SunLife","VD3-1212",74,20,1.8,(today+timedelta(days=13)).isoformat(),"City Pharma"),
          ("Omeprazole 20mg","Gastrointestinal","NovaMed","OMP-8811",0,12,1.1,(today-timedelta(days=3)).isoformat(),"Care Supply"),
          ("Salbutamol Inhaler","Respiratory","AirMed","SAL-7721",3,10,5.0,(today+timedelta(days=65)).isoformat(),"HealthPlus"),
          ("Atorvastatin 20mg","Cardiovascular","WellCare","ATV-5560",38,15,2.2,(today+timedelta(days=320)).isoformat(),"City Pharma"),
          ("Aspirin 75mg","Analgesics","WellCare","ASP-0129",96,25,0.5,(today+timedelta(days=400)).isoformat(),"Care Supply"),
          ("Furosemide 40mg","Cardiovascular","NovaMed","FUR-7780",22,15,1.7,(today+timedelta(days=44)).isoformat(),"HealthPlus"),
        ]
        for name,cat,mfr,batch,qty,minimum,price,expiry,supplier in samples:
            db.execute("""INSERT INTO medicines(name,category,manufacturer,batch_number,quantity,min_stock,unit_price,
                manufacturing_date,expiry_date,supplier,description,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (name,cat,mfr,batch,qty,minimum,price,(today-timedelta(days=300)).isoformat(),expiry,supplier,
                 "Demonstration record — replace with verified inventory data.",datetime.now().isoformat(timespec="seconds")))
        # Seed a realistic demo ledger so charts, reports, and shortage forecasts
        # are populated on first launch. These are simulated educational records.
        demo_issue_totals = [36, 120, 75, 24, 45, 42, 30, 48, 66, 28]
        issue_days_ago = [155, 125, 95, 65, 35, 5]
        for index, med in enumerate(db.execute("SELECT id,name,quantity FROM medicines ORDER BY id").fetchall()):
            total_issued = demo_issue_totals[index % len(demo_issue_totals)]
            db.execute("INSERT INTO stock_movements(medicine_id,movement_type,quantity,reason,username,created_at) VALUES(?,?,?,?,?,?)",
                       (med["id"], "RECEIVE", max(1, med["quantity"] + total_issued),
                        "Initial demonstration stock", "admin",
                        (datetime.now()-timedelta(days=160)).isoformat(timespec="seconds")))
            remaining = total_issued
            for issue_index, days_ago in enumerate(issue_days_ago):
                parts_left = len(issue_days_ago) - issue_index
                issue_qty = max(1, remaining // parts_left)
                if issue_index == len(issue_days_ago) - 1:
                    issue_qty = remaining
                remaining -= issue_qty
                db.execute("INSERT INTO stock_movements(medicine_id,movement_type,quantity,reason,username,created_at) VALUES(?,?,?,?,?,?)",
                           (med["id"], "ISSUE", issue_qty, "Demonstration usage", "admin",
                            (datetime.now()-timedelta(days=days_ago)).isoformat(timespec="seconds")))
        db.execute("INSERT INTO activity_logs(message,kind,created_at) VALUES(?,?,?)",
                   ("Demonstration inventory and stock history initialized", "success", datetime.now().isoformat(timespec="seconds")))
    db.commit(); db.close()

@app.before_request
def load_user():
    g.user = None
    if session.get("user_id"):
        db = connect_db()
        g.user = db.execute("SELECT * FROM users WHERE id=? AND active=1", (session["user_id"],)).fetchone()
        db.close()
        if g.user is None: session.clear()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not g.user:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

def log_activity(message, kind="info"):
    db=connect_db()
    db.execute("INSERT INTO activity_logs(message,kind,created_at) VALUES(?,?,?)",
               (message,kind,datetime.now().isoformat(timespec="seconds")))
    db.commit(); db.close()

def medicine_status(m):
    if m["quantity"] <= 0: return "Out of stock"
    if m["quantity"] <= m["min_stock"]: return "Low stock"
    return "In stock"

@app.context_processor
def common_context():
    return {"today": date.today(), "medicine_status": medicine_status}

@app.route("/")
def index():
    return redirect(url_for("dashboard") if g.user else url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if g.user: return redirect(url_for("dashboard"))
    if request.method == "POST":
        username=request.form.get("username","").strip()
        password=request.form.get("password","")
        db=connect_db(); user=db.execute("SELECT * FROM users WHERE username=? AND active=1",(username,)).fetchone(); db.close()
        if user and check_password_hash(user["password_hash"],password):
            session.clear(); session["user_id"]=user["id"]
            log_activity(f"User login — {user['username']}", "success")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Username or password is incorrect, or the account is inactive.", "error")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    username=g.user["username"]; session.clear(); log_activity(f"User logout — {username}")
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    db=connect_db()
    total=db.execute("SELECT COUNT(*) n FROM medicines").fetchone()["n"]
    stock=db.execute("SELECT COALESCE(SUM(quantity),0) n FROM medicines").fetchone()["n"]
    low=db.execute("SELECT COUNT(*) n FROM medicines WHERE quantity>0 AND quantity<=min_stock").fetchone()["n"]
    out=db.execute("SELECT COUNT(*) n FROM medicines WHERE quantity=0").fetchone()["n"]
    exp=db.execute("SELECT COUNT(*) n FROM medicines WHERE date(expiry_date) BETWEEN date('now') AND date('now','+30 day')").fetchone()["n"]
    value=db.execute("SELECT COALESCE(SUM(quantity*unit_price),0) n FROM medicines").fetchone()["n"]
    low_items=db.execute("SELECT * FROM medicines WHERE quantity<=min_stock ORDER BY quantity ASC LIMIT 6").fetchall()
    recent=db.execute("SELECT * FROM medicines ORDER BY id DESC LIMIT 6").fetchall()
    activity=db.execute("SELECT * FROM activity_logs ORDER BY id DESC LIMIT 6").fetchall()
    categories=db.execute("SELECT category, SUM(quantity) qty FROM medicines GROUP BY category ORDER BY qty DESC").fetchall()
    movements=db.execute("""SELECT strftime('%Y-%m',created_at) month,
      SUM(CASE WHEN movement_type='ISSUE' THEN quantity ELSE 0 END) issued,
      SUM(CASE WHEN movement_type='RECEIVE' THEN quantity ELSE 0 END) received
      FROM stock_movements WHERE created_at>=date('now','-5 months') GROUP BY month ORDER BY month""").fetchall()
    db.close()
    labels=[datetime.strptime(x["month"],"%Y-%m").strftime("%b") for x in movements]
    return render_template("dashboard.html", total=total, stock=stock, low=low, out=out, exp=exp, value=value,
        low_items=low_items, recent=recent, activity=activity, categories=categories, movement_labels=labels,
        issued=[x["issued"] or 0 for x in movements], received=[x["received"] or 0 for x in movements])

@app.route("/inventory")
@login_required
def inventory():
    q=request.args.get("q","").strip(); stock_filter=request.args.get("stock",""); expiry_filter=request.args.get("expiry","")
    db=connect_db(); sql="SELECT * FROM medicines WHERE (name LIKE ? OR category LIKE ? OR batch_number LIKE ?)"; params=[f"%{q}%"]*3
    if stock_filter=="low": sql+=" AND quantity>0 AND quantity<=min_stock"
    elif stock_filter=="out": sql+=" AND quantity=0"
    elif stock_filter=="available": sql+=" AND quantity>min_stock"
    if expiry_filter=="expired": sql+=" AND date(expiry_date)<date('now')"
    elif expiry_filter=="soon": sql+=" AND date(expiry_date) BETWEEN date('now') AND date('now','+30 day')"
    sql+=" ORDER BY name COLLATE NOCASE"
    meds=db.execute(sql,params).fetchall(); db.close()
    return render_template("inventory.html", medicines=meds, q=q, stock_filter=stock_filter, expiry_filter=expiry_filter)

def read_medicine_form():
    name=request.form.get("name","").strip(); category=request.form.get("category","").strip()
    batch=request.form.get("batch_number","").strip(); expiry=request.form.get("expiry_date","").strip()
    try:
        qty=int(request.form.get("quantity","0")); minimum=int(request.form.get("min_stock","10")); price=float(request.form.get("unit_price","0"))
        if not name or not category or not batch or not expiry: raise ValueError("Complete all required fields.")
        if qty<0 or minimum<0 or price<0: raise ValueError("Quantity, minimum stock, and price cannot be negative.")
        date.fromisoformat(expiry)
        mfg=request.form.get("manufacturing_date","").strip()
        if mfg: date.fromisoformat(mfg)
        if mfg and mfg>expiry: raise ValueError("Manufacturing date cannot be after expiry date.")
        return {"name":name,"category":category,"manufacturer":request.form.get("manufacturer","").strip(),
            "batch_number":batch,"quantity":qty,"min_stock":minimum,"unit_price":price,
            "manufacturing_date":mfg or None,"expiry_date":expiry,"supplier":request.form.get("supplier","").strip(),
            "description":request.form.get("description","").strip()}, None
    except (ValueError,TypeError) as e: return None, str(e) or "Enter valid numeric values and dates."

@app.route("/medicine/add", methods=["GET","POST"])
@login_required
def add_medicine():
    if request.method=="POST":
        data,error=read_medicine_form()
        if error: flash(error,"error")
        else:
            db=connect_db()
            try:
                cols=",".join(data.keys()); marks=",".join("?" for _ in data)
                db.execute(f"INSERT INTO medicines({cols},created_at) VALUES({marks},?)",tuple(data.values())+(datetime.now().isoformat(timespec="seconds"),))
                mid=db.execute("SELECT last_insert_rowid()").fetchone()[0]
                if data["quantity"]>0: db.execute("INSERT INTO stock_movements(medicine_id,movement_type,quantity,reason,username,created_at) VALUES(?,?,?,?,?,?)",
                    (mid,"RECEIVE",data["quantity"],"Initial quantity",""+g.user["username"],datetime.now().isoformat(timespec="seconds")))
                db.commit(); db.close(); log_activity(f"Medicine added — {data['name']}","success")
                flash("Medicine added successfully.","success"); return redirect(url_for("inventory"))
            except sqlite3.IntegrityError:
                db.rollback(); db.close(); flash("Could not save this medicine. Check the details and try again.","error")
    return render_template("medicine_form.html", medicine=None, page_title="Add Medicine")

@app.route("/medicine/<int:mid>")
@login_required
def view_medicine(mid):
    db=connect_db(); med=db.execute("SELECT * FROM medicines WHERE id=?",(mid,)).fetchone()
    moves=db.execute("SELECT * FROM stock_movements WHERE medicine_id=? ORDER BY id DESC LIMIT 10",(mid,)).fetchall(); db.close()
    if not med: abort(404)
    return render_template("medicine_view.html", medicine=med, movements=moves)

@app.route("/medicine/<int:mid>/edit", methods=["GET","POST"])
@login_required
def edit_medicine(mid):
    db=connect_db(); old=db.execute("SELECT * FROM medicines WHERE id=?",(mid,)).fetchone(); db.close()
    if not old: abort(404)
    if request.method=="POST":
        data,error=read_medicine_form()
        if error: flash(error,"error")
        else:
            db=connect_db(); cols=",".join(f"{k}=?" for k in data)
            db.execute(f"UPDATE medicines SET {cols} WHERE id=?",tuple(data.values())+(mid,)); db.commit(); db.close()
            log_activity(f"Medicine updated — {data['name']}","success"); flash("Medicine updated.","success"); return redirect(url_for("inventory"))
    return render_template("medicine_form.html", medicine=old, page_title="Edit Medicine")

@app.route("/medicine/<int:mid>/delete", methods=["POST"])
@admin_required
def delete_medicine(mid):
    db=connect_db(); med=db.execute("SELECT name FROM medicines WHERE id=?",(mid,)).fetchone()
    if med: db.execute("DELETE FROM medicines WHERE id=?",(mid,)); db.commit()
    db.close()
    if med: log_activity(f"Medicine deleted — {med['name']}","warning"); flash("Medicine deleted.","success")
    else: flash("Medicine not found.","error")
    return redirect(url_for("inventory"))

@app.route("/stock", methods=["GET","POST"])
@login_required
def stock_management():
    db=connect_db()
    if request.method=="POST":
        try:
            mid=int(request.form.get("medicine_id","")); qty=int(request.form.get("quantity","0")); kind=request.form.get("movement_type","")
            reason=request.form.get("reason","").strip()
            if qty<=0 or kind not in ("RECEIVE","ISSUE"): raise ValueError("Choose a valid movement and a quantity greater than zero.")
            db.execute("BEGIN IMMEDIATE")
            med=db.execute("SELECT * FROM medicines WHERE id=?",(mid,)).fetchone()
            if not med: raise ValueError("Select a valid medicine.")
            if kind=="ISSUE" and qty>med["quantity"]: raise ValueError("Cannot issue more stock than is currently available.")
            new_qty=med["quantity"]+qty if kind=="RECEIVE" else med["quantity"]-qty
            db.execute("UPDATE medicines SET quantity=? WHERE id=?",(new_qty,mid))
            db.execute("INSERT INTO stock_movements(medicine_id,movement_type,quantity,reason,username,created_at) VALUES(?,?,?,?,?,?)",
                (mid,kind,qty,reason,g.user["username"],datetime.now().isoformat(timespec="seconds")))
            db.commit(); db.close(); log_activity(f"Stock {kind.lower()} — {med['name']} ({qty} units)","success")
            flash("Stock movement recorded.","success"); return redirect(url_for("stock_management"))
        except (ValueError,TypeError) as e:
            db.rollback(); db.close(); flash(str(e) or "Please enter valid stock details.","error"); return redirect(url_for("stock_management"))
    meds=db.execute("SELECT id,name,quantity FROM medicines ORDER BY name").fetchall()
    moves=db.execute("SELECT sm.*,m.name medicine_name FROM stock_movements sm JOIN medicines m ON m.id=sm.medicine_id ORDER BY sm.id DESC LIMIT 100").fetchall()
    db.close(); return render_template("stock_management.html", medicines=meds, movements=moves)

@app.route("/expiry")
@login_required
def expiry():
    period=request.args.get("days","30")
    if period not in ("30","60","90","all"): period="30"
    db=connect_db()
    sql="SELECT * FROM medicines"
    if period!="all": sql+=" WHERE date(expiry_date)<=date('now',?)"; params=(f"+{period} day",)
    else: params=()
    meds=db.execute(sql+" ORDER BY date(expiry_date)",params).fetchall(); db.close()
    return render_template("expiry.html", medicines=meds, days=period)

def prediction_rows():
    # Example training data: estimated days until stockout
    X_train = [[1], [3], [7], [8], [14],
               [21], [30], [31], [45], [60]]

    y_train = [
        "High", "High", "High",
        "Medium", "Medium", "Medium", "Medium",
        "Monitor", "Monitor", "Monitor"
    ]

    model = DecisionTreeClassifier(random_state=42)
    model.fit(X_train, y_train)

    db = connect_db()
    meds = db.execute(
        "SELECT * FROM medicines ORDER BY name"
    ).fetchall()

    rows = []

    for m in meds:
        history = db.execute("""
            SELECT SUM(quantity) total,
                   MIN(created_at) first_seen,
                   MAX(created_at) last_seen
            FROM stock_movements
            WHERE medicine_id=? AND movement_type='ISSUE'
        """, (m["id"],)).fetchone()

        total = history["total"] or 0

        if (
            total
            and history["first_seen"]
            and history["last_seen"]
            and history["first_seen"][:10] != history["last_seen"][:10]
        ):
            span = max(
                1,
                (
                    date.fromisoformat(history["last_seen"][:10])
                    - date.fromisoformat(history["first_seen"][:10])
                ).days + 1
            )
            avg = total / span
            method = "Decision Tree + Recorded issues"
        else:
            avg = 0.0
            method = "Insufficient issue history"

        days_left = m["quantity"] / avg if avg > 0 else None

        if days_left is not None:
            risk = model.predict([[days_left]])[0]
        else:
            risk = "Insufficient history"

        rows.append({
            "medicine": m,
            "avg": avg,
            "days": days_left,
            "requirement": math.ceil(avg * 30) if avg > 0 else None,
            "method": method,
            "risk": risk
        })

    db.close()
    return rows


@app.route("/predictions")
@login_required
def predictions():
    return render_template("predictions.html", predictions=prediction_rows())

@app.route("/analytics")
@login_required
def analytics():
    db=connect_db()
    cats=db.execute("SELECT category,COUNT(*) count,SUM(quantity) qty FROM medicines GROUP BY category ORDER BY count DESC").fetchall()
    month=db.execute("""SELECT strftime('%Y-%m',created_at) month,
       SUM(CASE WHEN movement_type='ISSUE' THEN quantity ELSE 0 END) issued,
       SUM(CASE WHEN movement_type='RECEIVE' THEN quantity ELSE 0 END) received
       FROM stock_movements GROUP BY month ORDER BY month DESC LIMIT 6""").fetchall()
    db.close(); month=list(reversed(month))
    return render_template("analytics.html", categories=cats, months=month,
        expiry_count=sum(1 for x in get_medicines() if (date.fromisoformat(x["expiry_date"])-date.today()).days<=30),
        low_count=sum(1 for x in get_medicines() if x["quantity"]<=x["min_stock"]))

def get_medicines():
    db=connect_db(); rows=db.execute("SELECT * FROM medicines ORDER BY name").fetchall(); db.close(); return rows

@app.route("/alerts")
@login_required
def alerts():
    meds=get_medicines(); rows=[]
    for m in meds:
        left=(date.fromisoformat(m["expiry_date"])-date.today()).days
        if m["quantity"]==0: rows.append((m,"Out of stock","critical","No units currently available"))
        elif m["quantity"]<=m["min_stock"]: rows.append((m,"Low stock","warning",f"{m['quantity']} units remaining; minimum is {m['min_stock']}"))
        if left<0: rows.append((m,"Expired","critical",f"Expired {-left} days ago"))
        elif left<=30: rows.append((m,"Expiry soon","warning",f"Expires in {left} days"))
    for p in prediction_rows():
        if p["days"] is not None and p["days"]<=7: rows.append((p["medicine"],"Predicted shortage","critical",f"Estimated stockout in {p['days']:.1f} days"))
    return render_template("alerts.html", alerts=rows)

@app.route("/reports")
@login_required
def reports():
    return render_template("reports.html", medicines=get_medicines(), movements=get_movements(), predictions=prediction_rows())

def get_movements():
    db=connect_db(); rows=db.execute("SELECT sm.*,m.name medicine_name FROM stock_movements sm JOIN medicines m ON m.id=sm.medicine_id ORDER BY sm.id DESC").fetchall(); db.close(); return rows

@app.route("/reports/export/<kind>.csv")
@login_required
def export_csv(kind):
    output=io.StringIO(); writer=csv.writer(output)
    if kind=="inventory":
        rows=get_medicines(); writer.writerow(["Medicine","Category","Batch","Quantity","Minimum","Unit price","Expiry","Supplier"])
        for m in rows: writer.writerow([m["name"],m["category"],m["batch_number"],m["quantity"],m["min_stock"],m["unit_price"],m["expiry_date"],m["supplier"]])
    elif kind=="movements":
        rows=get_movements(); writer.writerow(["Medicine","Type","Quantity","Reason","User","Date"])
        for m in rows: writer.writerow([m["medicine_name"],m["movement_type"],m["quantity"],m["reason"],m["username"],m["created_at"]])
    elif kind=="predictions":
        rows=prediction_rows(); writer.writerow(["Medicine","Quantity","Average daily issue","Estimated days left","30-day requirement","Method"])
        for p in rows: writer.writerow([p["medicine"]["name"],p["medicine"]["quantity"],round(p["avg"],3),round(p["days"],1) if p["days"] is not None else "Insufficient data",p["requirement"] if p["requirement"] is not None else "Insufficient data",p["method"]])
    else: abort(404)
    response=make_response("\ufeff"+output.getvalue()); response.headers["Content-Type"]="text/csv; charset=utf-8"
    response.headers["Content-Disposition"]=f"attachment; filename=meditrack-{kind}-{date.today().isoformat()}.csv"
    return response

@app.route("/users", methods=["GET","POST"])
@admin_required
def users():
    db=connect_db()
    if request.method=="POST":
        username=request.form.get("username","").strip(); full_name=request.form.get("full_name","").strip()
        password=request.form.get("password",""); role=request.form.get("role","staff")
        if not username or not full_name or len(password)<8 or role not in ("admin","staff"):
            flash("Enter a username, full name, valid role, and password of at least 8 characters.","error")
        else:
            try:
                db.execute("INSERT INTO users(username,password_hash,full_name,role,active,created_at) VALUES(?,?,?,?,1,?)",
                    (username,generate_password_hash(password),full_name,role,datetime.now().isoformat(timespec="seconds")))
                db.commit(); log_activity(f"User created — {username}","success"); flash("User created.","success")
            except sqlite3.IntegrityError: flash("That username already exists.","error")
        db.close(); return redirect(url_for("users"))
    rows=db.execute("SELECT id,username,full_name,role,active,created_at FROM users ORDER BY id").fetchall(); db.close()
    return render_template("users.html", users=rows)

@app.route("/users/<int:uid>/toggle", methods=["POST"])
@admin_required
def toggle_user(uid):
    if uid==g.user["id"]: flash("You cannot deactivate your own account.","error")
    else:
        db=connect_db(); user=db.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
        if user:
            db.execute("UPDATE users SET active=? WHERE id=?",(0 if user["active"] else 1,uid)); db.commit()
            log_activity(f"User status changed — {user['username']}","warning"); flash("User status updated.","success")
        db.close()
    return redirect(url_for("users"))

@app.errorhandler(403)
def forbidden(e): return render_template("error.html", code=403, message="You do not have permission to access this page."),403
@app.errorhandler(404)
def not_found(e): return render_template("error.html", code=404, message="The page or record could not be found."),404
@app.errorhandler(500)
def server_error(e): return render_template("error.html", code=500, message="Something went wrong. Please try again."),500

with app.app_context(): init_db()
if __name__ == "__main__":
    app.run(debug=True)
