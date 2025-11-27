# app.py — robust, error-tolerant Flask app with Parents Login
import os
import json
import uuid
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_from_directory, jsonify
)
from werkzeug.utils import secure_filename

# --- CONFIG ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ALLOWED_SUBMIT_EXT = {"pdf", "txt", "zip", "rar"}

# ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "homework"), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "submissions"), exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = "change-this-in-prod-please"

# --- JSON helpers (robust) ---
def _safe_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def read_json(fname, default):
    path = os.path.join(DATA_DIR, fname)
    if not os.path.exists(path):
        try:
            _safe_write(path, default)
        except Exception:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f)
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        try:
            _safe_write(path, default)
        except Exception:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f)
        return default
    if isinstance(data, dict):
        for key in ("students", "teachers", "admins", "homework", "submissions", "pending_admissions"):
            if key in data and isinstance(data[key], list):
                return data[key]
        list_values = [v for v in data.values() if isinstance(v, list)]
        if len(list_values) == 1:
            return list_values[0]
        return default
    elif isinstance(data, list):
        return data
    else:
        return default

def save_json(fname, obj):
    path = os.path.join(DATA_DIR, fname)
    try:
        if isinstance(obj, (list, dict)):
            _safe_write(path, obj)
        else:
            _safe_write(path, obj)
    except Exception:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)

# initialize defaults
read_json("students.json", [])
read_json("teachers.json", [])
read_json("admin.json", [{"id": "admin", "username": "admin", "email": "admin@example.com", "password": "admin123"}])
read_json("homework.json", [])
read_json("submissions.json", [])
read_json("admissions-pending.json", [])

# --- Auth helpers ---
def login_user(role, user_id):
    session.clear()
    session["role"] = role
    session["user_id"] = str(user_id)

def get_current_user():
    role = session.get("role")
    uid = session.get("user_id")
    if not role or not uid:
        return None
    uid = str(uid)
    if role == "teacher":
        teachers = read_json("teachers.json", [])
        return next((t for t in teachers if str(t.get("id")) == uid), None)
    if role == "student":
        students = read_json("students.json", [])
        return next((s for s in students if str(s.get("id")) == uid), None)
    if role == "admin":
        admins = read_json("admin.json", [])
        return next((a for a in admins if str(a.get("id")) == uid), None)
    return None

def allowed_file(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED_SUBMIT_EXT

# ---- ROUTES ----

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/about")
def about():
    return render_template("about.html")

# Admission form
@app.route("/admission", methods=["GET", "POST"])
def admission():
    if request.method == "POST":
        data = {
            "id": str(uuid.uuid4()),
            "name": request.form.get("name"),
            "father_name": request.form.get("father_name"),
            "class": request.form.get("class"),
            "previous_school": request.form.get("previous_school"),
            "phone": request.form.get("phone"),
            "email": request.form.get("email"),
            "cnic": request.form.get("cnic"),
            "photo": None,
            "created_at": datetime.utcnow().isoformat(),
            "password": request.form.get("password") or "changeme"  # student password
        }
        photo = request.files.get("photo")
        if photo and photo.filename:
            fn = secure_filename(photo.filename)
            dest = os.path.join(UPLOAD_DIR, "homework", f"admission-{uuid.uuid4().hex}-{fn}")
            photo.save(dest)
            data["photo"] = os.path.relpath(dest, BASE_DIR)
        pend = read_json("admissions-pending.json", [])
        pend.append(data)
        save_json("admissions-pending.json", pend)
        flash("Admission submitted. Admin will review.", "success")
        return redirect(url_for("home"))
    return render_template("admission.html")

# Generic login (student / teacher / admin)
@app.route("/login/<role>", methods=["GET", "POST"])
def login(role):
    role = (role or "").lower()
    if request.method == "POST":
        identifier = (request.form.get("identifier") or "").strip()
        password = (request.form.get("password") or "").strip()

        if role == "student":
            studs = read_json("students.json", [])
            user = next((s for s in studs if str(s.get("cnic") or "").strip() == identifier or str(s.get("email") or "").strip() == identifier and str(s.get("password") or "") == password), None)
            if user:
                login_user("student", user.get("id"))
                return redirect(url_for("student_dashboard"))
            flash("Invalid student credentials", "danger")

        elif role == "teacher":
            tlist = read_json("teachers.json", [])
            user = next((t for t in tlist if (str(t.get("username") or "").strip() == identifier or str(t.get("email") or "").strip() == identifier) and str(t.get("password") or "") == password), None)
            if user:
                login_user("teacher", user.get("id"))
                return redirect(url_for("teacher_dashboard"))
            flash("Invalid teacher credentials", "danger")

        elif role == "admin":
            admins = read_json("admin.json", [])
            user = next((a for a in admins if (str(a.get("username") or "").strip() == identifier or str(a.get("email") or "").strip() == identifier) and str(a.get("password") or "") == password), None)
            if user:
                login_user("admin", user.get("id"))
                return redirect(url_for("admin_dashboard"))
            flash("Invalid admin credentials", "danger")
        else:
            flash("Unknown role", "danger")

    return render_template("login.html", role=role)

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("home"))

# === Teacher Dashboard & create homework ===
@app.route("/teacher/dashboard")
def teacher_dashboard():
    user = get_current_user()
    if not user or session.get("role") != "teacher":
        return redirect(url_for("login", role="teacher"))
    th = user
    studs = read_json("students.json", [])
    hw = [h for h in read_json("homework.json", []) if str(h.get("teacher_id")) == str(th.get("id"))]
    subs = [s for s in read_json("submissions.json", []) if any(str(s.get("homework_id")) == str(h.get("id")) for h in hw)]
    return render_template("teacher_dashboard.html", teacher=th, students=studs, homeworks=hw, submissions=subs)

@app.route("/teacher/homework/create", methods=["POST"])
def create_homework():
    user = get_current_user()
    if not user or session.get("role") != "teacher":
        return redirect(url_for("login", role="teacher"))
    title = request.form.get("title")
    description = request.form.get("description")
    target_class = request.form.get("class")
    due_date = request.form.get("due_date")
    expiry_date = request.form.get("expiry_date")
    file = request.files.get("file")
    attached = None
    if file and file.filename:
        if not allowed_file(file.filename):
            flash("File type not allowed for homework attachment.", "danger")
            return redirect(url_for("teacher_dashboard"))
        fn = secure_filename(file.filename)
        saved = f"{uuid.uuid4().hex}-{fn}"
        dest = os.path.join(UPLOAD_DIR, "homework", saved)
        file.save(dest)
        attached = saved
    hw = {
        "id": str(uuid.uuid4()),
        "teacher_id": user.get("id"),
        "title": title,
        "description": description,
        "class": str(target_class),
        "due_date": due_date,
        "expiry_date": expiry_date,
        "file": attached,
        "created_at": datetime.utcnow().isoformat()
    }
    all_hw = read_json("homework.json", [])
    all_hw.append(hw)
    save_json("homework.json", all_hw)
    flash("Homework created", "success")
    return redirect(url_for("teacher_dashboard"))

@app.route("/uploads/homework/<filename>")
def download_homework_file(filename):
    return send_from_directory(os.path.join(UPLOAD_DIR, "homework"), filename, as_attachment=True)

# === Student dashboard & submit ===
@app.route("/student/dashboard")
def student_dashboard():
    user = get_current_user()
    if not user or session.get("role") != "student":
        return redirect(url_for("login", role="student"))
    s = user
    hw_all = read_json("homework.json", [])
    class_hw = [h for h in hw_all if str(h.get("class")) == str(s.get("class"))]
    subs = read_json("submissions.json", [])
    for h in class_hw:
        h["submitted"] = any(sub for sub in subs if str(sub.get("homework_id")) == str(h.get("id")) and str(sub.get("student_id")) == str(s.get("id")))
    return render_template("student_dashboard.html", student=s, homeworks=class_hw)

@app.route("/student/homework/submit/<hw_id>", methods=["POST"])
def submit_homework(hw_id):
    user = get_current_user()
    if not user or session.get("role") != "student":
        return redirect(url_for("login", role="student"))
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("No file selected", "danger")
        return redirect(url_for("student_dashboard"))
    if not allowed_file(file.filename):
        flash("File type not allowed. Allowed: PDF, TXT, ZIP, RAR", "danger")
        return redirect(url_for("student_dashboard"))
    fn = secure_filename(file.filename)
    saved_name = f"{uuid.uuid4().hex}-{fn}"
    dest = os.path.join(UPLOAD_DIR, "submissions", saved_name)
    file.save(dest)
    sub = {
        "id": str(uuid.uuid4()),
        "homework_id": hw_id,
        "student_id": user.get("id"),
        "filename": saved_name,
        "original_name": fn,
        "uploaded_at": datetime.utcnow().isoformat()
    }
    all_subs = read_json("submissions.json", [])
    all_subs.append(sub)
    save_json("submissions.json", all_subs)
    flash("Submitted successfully", "success")
    return redirect(url_for("student_dashboard"))

@app.route("/uploads/submissions/<filename>")
def download_submission(filename):
    user = get_current_user()
    if not user or session.get("role") != "teacher":
        flash("Not authorized", "danger")
        return redirect(url_for("home"))
    return send_from_directory(os.path.join(UPLOAD_DIR, "submissions"), filename, as_attachment=True)

# --- Admin dashboard ---
@app.route("/admin/dashboard")
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect(url_for("login", role="admin"))
    studs = read_json("students.json", [])
    tchs = read_json("teachers.json", [])
    hw = read_json("homework.json", [])
    subs = read_json("submissions.json", [])
    pend = read_json("admissions-pending.json", [])
    student_progress = []
    for s in studs:
        total = len([h for h in hw if str(h.get("class")) == str(s.get("class"))])
        submitted = len([x for x in subs if str(x.get("student_id")) == str(s.get("id"))])
        student_progress.append({"student": s, "total_hw": total, "submitted": submitted})
    teacher_activity = []
    for t in tchs:
        tcount = len([h for h in hw if str(h.get("teacher_id")) == str(t.get("id"))])
        teacher_activity.append({"teacher": t, "homeworks_given": tcount})
    return render_template("admin_dashboard.html", students=student_progress, teachers=teacher_activity, pending=pend)

@app.route("/admin/admission/decide/<admission_id>/<action>")
def decide_admission(admission_id, action):
    if session.get("role") != "admin":
        return redirect(url_for("login", role="admin"))
    pend = read_json("admissions-pending.json", [])
    item = next((p for p in pend if str(p.get("id")) == str(admission_id)), None)
    if not item:
        flash("Admission not found", "danger")
        return redirect(url_for("admin_dashboard"))
    if action == "accept":
        studs = read_json("students.json", [])
        new_student = {
            "id": str(uuid.uuid4()),
            "name": item.get("name"),
            "father_name": item.get("father_name"),
            "class": item.get("class"),
            "previous_school": item.get("previous_school"),
            "phone": item.get("phone"),
            "email": item.get("email"),
            "cnic": item.get("cnic"),
            "photo": item.get("photo"),
            "password": "changeme",
            "created_at": datetime.utcnow().isoformat()
        }
        studs.append(new_student)
        save_json("students.json", studs)
        pend = [p for p in pend if str(p.get("id")) != str(admission_id)]
        save_json("admissions-pending.json", pend)
        flash("Admission accepted and student created", "success")
    else:
        pend = [p for p in pend if str(p.get("id")) != str(admission_id)]
        save_json("admissions-pending.json", pend)
        flash("Admission declined", "info")
    return redirect(url_for("admin_dashboard"))

# --- Parents Login Integration ---

@app.route("/parent/login", methods=["GET", "POST"])
def parent_login():
    if request.method == "POST":
        father_name = (request.form.get("father_name") or "").strip()
        password = (request.form.get("password") or "").strip()
        students = read_json("students.json", [])
        student = next((s for s in students if str(s.get("father_name") or "").strip().lower() == father_name.lower() and str(s.get("password") or "") == password), None)
        if student:
            session.clear()
            session["role"] = "parent"
            session["child_id"] = str(student.get("id"))
            session["child_name"] = student.get("name")
            session["child_class"] = student.get("class")
            flash(f"Welcome parent of {student.get('name')}", "success")
            return redirect(url_for("parent_dashboard"))
        flash("Father name or password is incorrect!", "danger")
        return redirect(url_for("parent_login"))
    return render_template("parent_login.html")

@app.route("/parent/dashboard")
def parent_dashboard():
    if session.get("role") != "parent":
        flash("Please login as parent", "danger")
        return redirect(url_for("parent_login"))

    child_id = session.get("child_id")
    child_class = session.get("child_class")
    child_name = session.get("child_name")

    teachers = read_json("teachers.json", [])
    teachers_in_class = [t for t in teachers if str(t.get("class")) == str(child_class)]

    homeworks = read_json("homework.json", [])
    submissions = read_json("submissions.json", [])

    teacher_data = []
    for t in teachers_in_class:
        t_hw = [h for h in homeworks if str(h.get("teacher_id")) == str(t.get("id"))]
        for hw in t_hw:
            sub = next((s for s in submissions if str(s.get("homework_id")) == str(hw.get("id")) and str(s.get("student_id")) == str(child_id)), None)
            hw["submitted"] = bool(sub)
        t["homeworks"] = t_hw
        teacher_data.append(t)

    return render_template("parent_dashboard.html", child_name=child_name, teachers=teacher_data)

@app.route("/parent/logout")
def parent_logout():
    for k in ["role", "child_id", "child_name", "child_class"]:
        session.pop(k, None)
    flash("Parent logged out", "info")
    return redirect(url_for("parent_login"))

# --- simple API ---
@app.route("/api/status")
def status():
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(debug=True)
