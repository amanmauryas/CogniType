import os, io, csv, json, random, difflib, statistics as st
from datetime import datetime
from flask import (Flask, render_template, request, jsonify, redirect,
                   url_for, Response, session, abort)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config.update(
    SQLALCHEMY_DATABASE_URI="sqlite:///cognitype.db",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.environ.get("SECRET_KEY", "change-me-in-production"),
)
db = SQLAlchemy(app)

# Two passages matched for length and character mix; assignment to condition is randomised.
PASSAGES = [
    "Attention is a limited resource. When two tasks compete for the same mental "
    "workspace, people slow down, hesitate more often, and make more mistakes than "
    "they would on either task alone, even when each task feels easy.",
    "Memory works best when information is organised into meaningful groups. A "
    "reader who pauses to connect new ideas with old ones will usually remember "
    "more, although the process feels slower while it is happening.",
]
CONDITIONS = {
    "baseline": "Type the passage at a comfortable pace.",
    "dual_task": "Type the passage while counting backwards aloud from 983 in steps of 7 "
                 "(983, 976, 969 ...). Keep counting the whole time you type.",
}
METRICS = [
    ("iki_mean", "Typing pace (time between keys)", 1, "Average time from one key press to the next. Under higher load people slow down, because planning and typing compete for the same attention."),
    ("iki_sd", "Rhythm unevenness", 1, "How irregular your timing is. Load tends to make typing stop-start rather than steady."),
    ("dwell_mean", "Key hold time", 0, "How long you keep each key down. This is mostly a habit of your hands, so it usually changes very little."),
    ("pauses", "Long pauses (over 1 s)", 1, "Gaps where typing stalled while you thought. More stalls usually means more mental juggling."),
    ("backspaces", "Corrections", 1, "Number of Backspace presses. More corrections often means more slips under load."),
    ("wpm", "Speed (words per minute)", -1, "Characters typed per minute, counted as words of 5 characters. Higher load usually lowers it."),
    ("accuracy", "Accuracy to the passage", -1, "How closely your text matched the passage. Careful typists protect accuracy by slowing down instead."),
]

# ---------- models ----------
class Participant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False)
    study = db.Column(db.String(60), default="open")
    external_id = db.Column(db.String(80))
    touch_typist = db.Column(db.String(10))
    keyboard = db.Column(db.String(20))
    plan = db.Column(db.Text, nullable=False)  # [[condition, passage_idx], ...]
    consented_at = db.Column(db.DateTime, default=datetime.utcnow)
    blocks = db.relationship("Block", backref="participant", order_by="Block.order_index")

class Block(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey("participant.id"), nullable=False)
    order_index = db.Column(db.Integer, nullable=False)
    condition = db.Column(db.String(20), nullable=False)
    passage_idx = db.Column(db.Integer, nullable=False)
    typed_text = db.Column(db.Text)
    effort = db.Column(db.Integer)  # Paas mental effort scale, 1-9
    features = db.Column(db.Text)   # JSON
    keys = db.relationship("Keystroke", backref="block")

class Keystroke(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    block_id = db.Column(db.Integer, db.ForeignKey("block.id"), nullable=False)
    code = db.Column(db.String(20), nullable=False)   # physical key, e.g. KeyA
    press_ms = db.Column(db.Float, nullable=False)    # relative to first keydown in block
    release_ms = db.Column(db.Float, nullable=False)

class Setting(db.Model):
    key = db.Column(db.String(40), primary_key=True)
    value = db.Column(db.Text, nullable=False)

# ---------- feature extraction ----------
def _m(x): return round(st.fmean(x), 2) if x else None
def _sd(x): return round(st.pstdev(x), 2) if len(x) > 1 else None

def extract_features(keys, target, typed):
    keys = sorted(keys, key=lambda k: k["p"])
    dwell = [k["r"] - k["p"] for k in keys if 0 < k["r"] - k["p"] < 1000]
    iki = [keys[i + 1]["p"] - keys[i]["p"] for i in range(len(keys) - 1)]
    iki = [x for x in iki if 0 < x < 5000]
    flight = [keys[i + 1]["p"] - keys[i]["r"] for i in range(len(keys) - 1)]
    flight = [x for x in flight if -500 < x < 5000]  # negative = key rollover
    dur = (keys[-1]["r"] - keys[0]["p"]) if keys else 0
    return {
        "n_keys": len(keys), "duration_ms": round(dur),
        "iki_mean": _m(iki), "iki_sd": _sd(iki),
        "dwell_mean": _m(dwell), "dwell_sd": _sd(dwell),
        "flight_mean": _m(flight), "flight_sd": _sd(flight),
        "pauses": sum(1 for k in range(len(keys) - 1) if keys[k + 1]["p"] - keys[k]["r"] > 1000),
        "backspaces": sum(1 for k in keys if k["c"] == "Backspace"),
        "wpm": round((len(typed) / 5) / (dur / 60000), 1) if dur > 0 else None,
        "accuracy": round(100 * difflib.SequenceMatcher(None, target, typed).ratio(), 1),
    }

# ---------- participant flow ----------
def me():
    return db.session.get(Participant, session.get("pid")) if session.get("pid") else None

@app.route("/")
def index():
    return render_template("index.html", study=request.args.get("study", "open"),
                           ext=request.args.get("pid", ""))

@app.post("/start")
def start():
    if not request.form.get("consent"):
        return redirect(url_for("index"))
    conds, idx = list(CONDITIONS), [0, 1]
    random.shuffle(conds); random.shuffle(idx)
    p = Participant(code=os.urandom(4).hex(), study=request.form.get("study", "open")[:60],
                    external_id=request.form.get("ext", "")[:80],
                    touch_typist=request.form.get("touch_typist"), keyboard=request.form.get("keyboard"),
                    plan=json.dumps(list(zip(conds, idx))))
    db.session.add(p); db.session.commit()
    session["pid"] = p.id
    return redirect(url_for("task", i=0))

@app.route("/task/<int:i>")
def task(i):
    p = me()
    if not p: return redirect(url_for("index"))
    plan, done = json.loads(p.plan), len(p.blocks)
    if done >= len(plan): return redirect(url_for("results"))
    if i != done: return redirect(url_for("task", i=done))
    cond, pi = plan[i]
    return render_template("task.html", i=i, total=len(plan), cond=cond,
                           instruction=CONDITIONS[cond], text=PASSAGES[pi])

@app.post("/api/block/<int:i>")
def api_block(i):
    p = me()
    if not p: abort(401)
    plan = json.loads(p.plan)
    if i >= len(plan) or i != len(p.blocks): abort(400)
    d = request.get_json(force=True)
    try:
        keys = [{"c": str(k["c"])[:20], "p": float(k["p"]), "r": float(k["r"])} for k in d["keys"][:4000]]
        effort = min(9, max(1, int(d["effort"])))
    except (KeyError, TypeError, ValueError):
        abort(400)
    cond, pi = plan[i]
    typed = str(d.get("typed", ""))[:2000]
    b = Block(participant_id=p.id, order_index=i, condition=cond, passage_idx=pi, typed_text=typed,
              effort=effort, features=json.dumps(extract_features(keys, PASSAGES[pi], typed)))
    db.session.add(b); db.session.flush()
    db.session.bulk_save_objects([Keystroke(block_id=b.id, code=k["c"], press_ms=k["p"], release_ms=k["r"]) for k in keys])
    db.session.commit()
    nxt = url_for("task", i=i + 1) if i + 1 < len(plan) else url_for("results")
    return jsonify(next=nxt)

@app.route("/results")
def results():
    p = me()
    if not p or len(p.blocks) < 2: return redirect(url_for("index"))
    by = {b.condition: dict(json.loads(b.features), effort=b.effort) for b in p.blocks}
    cards, chart, hits, tested = [], {"labels": [], "values": [], "colors": []}, 0, 0
    colors = {"load": "#4b46b8", "against": "#0e6b72", "same": "#9aa7b4", "neutral": "#9aa7b4"}
    for key, label, sign, meaning in METRICS:
        a, c = by["baseline"].get(key), by["dual_task"].get(key)
        if a is None or c is None: continue
        rel = (c - a) / a if a else (1.0 if c > a else 0.0)
        pct = round(100 * rel) if a else None
        if sign: tested += 1
        if abs(rel) < 0.05:
            state, note = "same", "Barely changed between the two tasks."
        elif sign == 0:
            state, note = "neutral", "Changed, but this measure is a weak signal of load. It may just reflect how you pressed the keys."
        elif (rel > 0) == (sign > 0):
            state, note = "load", "Moved the way it usually does under higher mental load."; hits += 1
        else:
            state, note = "against", "Moved the opposite way. This can be practice, a careful strategy, or plain noise."
        cards.append(dict(label=label, base=a, load=c, pct=pct, state=state, note=note, meaning=meaning))
        if pct is not None:
            chart["labels"].append(label); chart["values"].append(pct); chart["colors"].append(colors[state])
    e0, e1 = by["baseline"]["effort"], by["dual_task"]["effort"]
    ratio = hits / tested if tested else 0
    felt = (f"You also rated counting as more effortful ({e0} to {e1}), which supports this." if e1 > e0 else
            f"You rated both tasks similarly effortful ({e0} and {e1}), so the counting may not have loaded you much." if e1 == e0 else
            f"You rated counting as less effortful ({e0} to {e1}), which is unusual.")
    if ratio >= 0.6:
        level, headline = "clear", f"Your typing shifted in {hits} of {tested} ways that usually go with higher mental load."
    elif ratio >= 0.3:
        level, headline = "mixed", f"Your typing shifted in {hits} of {tested} expected ways, so the signal is mixed."
    else:
        level, headline = "weak", f"Only {hits} of {tested} measures moved the way load usually pushes them, so your rhythm held up well."
    return render_template("results.html", cards=cards, chart=chart, code=p.code, level=level,
                           headline=headline, felt=felt)

# ---------- researcher area ----------
def admin_hash():
    row = db.session.get(Setting, "admin_hash")
    return row.value if row else None

def admin_only(f):
    def w(*a, **k):
        if not admin_hash(): return redirect(url_for("admin_setup"))
        return f(*a, **k) if session.get("admin") else redirect(url_for("admin_login"))
    w.__name__ = f.__name__
    return w

@app.route("/admin/setup", methods=["GET", "POST"])
def admin_setup():
    if admin_hash(): return redirect(url_for("admin_login"))  # one-time only
    error = None
    if request.method == "POST":
        pw, pw2 = request.form.get("password", ""), request.form.get("confirm", "")
        if len(pw) < 10: error = "Use at least 10 characters."
        elif pw != pw2: error = "The two passwords do not match."
        else:
            db.session.add(Setting(key="admin_hash", value=generate_password_hash(pw)))
            db.session.commit(); session["admin"] = True
            return redirect(url_for("admin"))
    return render_template("admin_setup.html", error=error)

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    h = admin_hash()
    if not h: return redirect(url_for("admin_setup"))
    if request.method == "POST" and check_password_hash(h, request.form.get("password", "")):
        session["admin"] = True
        return redirect(url_for("admin"))
    return render_template("admin_login.html", failed=request.method == "POST")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("index"))

@app.route("/admin")
@admin_only
def admin():
    study = request.args.get("study", "")
    q = Participant.query.order_by(Participant.consented_at.desc())
    if study: q = q.filter_by(study=study)
    ps = [p for p in q.all()]
    summary = {}
    for c in CONDITIONS:
        bl = [b for p in ps for b in p.blocks if b.condition == c]
        f = [json.loads(b.features) for b in bl]
        summary[c] = {"n": len(bl), "effort": _m([b.effort for b in bl]),
                      "iki": _m([x["iki_mean"] for x in f if x["iki_mean"]]),
                      "pauses": _m([x["pauses"] for x in f])}
    studies = [s for (s,) in db.session.query(Participant.study).distinct()]
    return render_template("admin.html", ps=ps, summary=summary, studies=studies, study=study)

def _csv(header, rows, name):
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(header); w.writerows(rows)
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}"})

@app.route("/admin/export/features.csv")
@admin_only
def export_features():
    fk = ["n_keys", "duration_ms", "iki_mean", "iki_sd", "dwell_mean", "dwell_sd",
          "flight_mean", "flight_sd", "pauses", "backspaces", "wpm", "accuracy"]
    rows = []
    for b in Block.query.all():
        f, p = json.loads(b.features), b.participant
        rows.append([p.code, p.study, p.external_id, p.touch_typist, p.keyboard, b.order_index,
                     b.condition, b.passage_idx, b.effort] + [f.get(k) for k in fk])
    return _csv(["participant", "study", "external_id", "touch_typist", "keyboard", "block_order",
                 "condition", "passage", "effort_1to9"] + fk, rows, "features.csv")

@app.route("/admin/export/keystrokes.csv")
@admin_only
def export_keystrokes():
    rows = [[k.block.participant.code, k.block.condition, k.block.order_index, k.code,
             round(k.press_ms, 2), round(k.release_ms, 2)] for k in Keystroke.query.all()]
    return _csv(["participant", "condition", "block_order", "key_code", "press_ms", "release_ms"],
                rows, "keystrokes_raw.csv")

if __name__ == "__main__":
    with app.app_context(): db.create_all()
    app.run(debug=True)
