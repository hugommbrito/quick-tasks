from fastapi import FastAPI, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
from datetime import datetime

app = FastAPI()
DB_PATH = "tasks.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'todo',
            is_urgent INTEGER DEFAULT 0,
            is_important INTEGER DEFAULT 0,
            order_index REAL DEFAULT 0,
            parent_id INTEGER DEFAULT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_id) REFERENCES tasks(id)
        )
    """)
    conn.commit()
    conn.close()


init_db()


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    status: Optional[str] = "todo"
    is_urgent: Optional[bool] = False
    is_important: Optional[bool] = False
    parent_id: Optional[int] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    is_urgent: Optional[bool] = None
    is_important: Optional[bool] = None
    order_index: Optional[float] = None


class ReorderItem(BaseModel):
    id: int
    order_index: float
    status: str


# ─── API ROUTES ───────────────────────────────────────────────────────────────

@app.get("/api/tasks")
def get_tasks():
    conn = get_db()
    tasks = conn.execute(
        "SELECT * FROM tasks WHERE parent_id IS NULL ORDER BY order_index, created_at"
    ).fetchall()
    result = []
    for task in tasks:
        task_dict = dict(task)
        subtasks = conn.execute(
            "SELECT * FROM tasks WHERE parent_id = ? ORDER BY order_index, created_at",
            (task["id"],),
        ).fetchall()
        task_dict["subtasks"] = [dict(s) for s in subtasks]
        result.append(task_dict)
    conn.close()
    return result


@app.post("/api/tasks")
def create_task(task: TaskCreate):
    conn = get_db()
    max_order = conn.execute(
        "SELECT MAX(order_index) FROM tasks WHERE status = ? AND parent_id IS NULL",
        (task.status,),
    ).fetchone()[0]
    order_index = (max_order or 0) + 1000
    cursor = conn.execute(
        """INSERT INTO tasks (title, description, status, is_urgent, is_important, order_index, parent_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (task.title, task.description, task.status, int(task.is_urgent),
         int(task.is_important), order_index, task.parent_id),
    )
    conn.commit()
    new_task = conn.execute("SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
    result = dict(new_task)
    result["subtasks"] = []
    conn.close()
    return result


@app.put("/api/tasks/{task_id}")
def update_task(task_id: int, task: TaskUpdate):
    conn = get_db()
    existing = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    fields = {}
    if task.title is not None:       fields["title"] = task.title
    if task.description is not None: fields["description"] = task.description
    if task.status is not None:      fields["status"] = task.status
    if task.is_urgent is not None:   fields["is_urgent"] = int(task.is_urgent)
    if task.is_important is not None: fields["is_important"] = int(task.is_important)
    if task.order_index is not None: fields["order_index"] = task.order_index
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", (*fields.values(), task_id))
    conn.commit()
    updated = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(updated)


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    conn = get_db()
    conn.execute("DELETE FROM tasks WHERE parent_id = ?", (task_id,))
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/tasks/reorder")
def reorder_tasks(items: List[ReorderItem]):
    conn = get_db()
    for item in items:
        conn.execute(
            "UPDATE tasks SET order_index = ?, status = ? WHERE id = ?",
            (item.order_index, item.status, item.id),
        )
    conn.commit()
    conn.close()
    return {"ok": True}


# ─── KINDLE SSR (sem JavaScript) ──────────────────────────────────────────────

KINDLE_CSS = """<style>
* { -webkit-box-sizing: border-box; box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: Georgia, serif; background: #f0f0f0; color: #111; font-size: 16px; line-height: 1.5; }
a { color: #111; }
#hdr { background: #fff; border-bottom: 2px solid #333; padding: 10px 14px; overflow: hidden; }
#hdr h1 { font-size: 20px; float: left; }
.hbtn { float: right; background: #333; color: #fff; padding: 8px 14px; font-size: 14px; text-decoration: none; display: inline-block; margin-left: 6px; }
.hbtn-sec { background: #fff; color: #333; border: 1px solid #333; }
/* MODO HORIZONTAL (Kindle de lado) - compativel com WebKit 528 / Safari 4.
   ATENCAO: este navegador NAO suporta unidades vh/vw nem 'transform' sem prefixo.
   Por isso o tamanho do #wrap e a rotacao 90deg sao aplicados via JavaScript em px
   (lendo window.innerWidth/innerHeight) - ver _lsApply() no script abaixo.
   Aqui ficam so propriedades que o WebKit 528 entende. */
html.landscape, html.landscape body { width: 100%; height: 100%; overflow: hidden; }
#wrap.landscape {
  position: absolute;
  top: 0;
  left: 0;
  overflow: auto;
  -webkit-transform-origin: top left;
  /* width, height e -webkit-transform sao definidos pelo JS */
}
html.landscape #main {
  padding: 4px;
  -webkit-column-count: 4;
  -webkit-column-gap: 6px;
}
html.landscape .section { margin: 0; widht: 80px}
html.landscape .sec-head { -webkit-column-break-inside: avoid; margin-top: 8px; }
html.landscape .card { -webkit-column-break-inside: avoid; height: 7.5em; widht: 70px; overflow: auto; margin-bottom: 6px; }
html.landscape .empty { -webkit-column-break-inside: avoid; }
#main { padding: 12px; }
.section { margin-bottom: 16px}
.sec-head { background: #e0e0e0; border: 1px solid #999; border-bottom: 2px solid #555; padding: 7px 10px; font-size: 13px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; }
.sec-cnt { font-size: 11px; background: #bbb; padding: 1px 7px; -webkit-border-radius: 8px; border-radius: 8px; margin-left: 6px; font-weight: normal; }
.card { background: #fff; border: 1px solid #ccc; padding: 10px 12px; margin-bottom: 6px; }
.card.urgent { border-left: 4px solid #333; }
.ctitle { font-size: 15px; font-weight: bold; margin-bottom: 4px; }
.cdesc { font-size: 13px; color: #555; margin-bottom: 6px; }
.cbadges { margin-bottom: 6px; }
.badge { font-size: 11px; border: 1px solid #888; padding: 1px 6px; margin-right: 4px; font-weight: bold; }
.cactions { border-top: 1px solid #eee; padding-top: 7px; margin-top: 6px; }
.cactions form { display: inline; margin-right: 3px; }
.cactions button, .cactions a { font-size: 13px; background: #fff; border: 1px solid #aaa; padding: 6px 12px; cursor: pointer; text-decoration: none; color: #111; display: inline-block; }
.empty { padding: 12px; font-size: 13px; color: #888; font-style: italic; background: #fff; border: 1px solid #ddd; }
.fp { background: #fff; border: 1px solid #ccc; padding: 16px; margin: 12px; }
.fp h2 { font-size: 18px; margin-bottom: 14px; border-bottom: 1px solid #ddd; padding-bottom: 8px; }
.fg { margin-bottom: 14px; }
.fg label { display: block; font-size: 13px; font-weight: bold; margin-bottom: 5px; }
.fg input[type=text], .fg textarea, .fg select { width: 100%; border: 1px solid #bbb; padding: 9px 11px; font-size: 15px; font-family: inherit; }
.fg textarea { resize: vertical; }
.cr label { font-size: 14px; margin-right: 18px; font-weight: normal; }
.cr input { margin-right: 5px; }
.fa { margin-top: 16px; }
.fa button, .fa a { font-size: 14px; padding: 10px 22px; cursor: pointer; border: 1px solid #999; margin-right: 8px; text-decoration: none; display: inline-block; background: #fff; color: #111; }
.bsub { background: #333; color: #fff; border-color: #333; }
.sub-row { padding: 5px 0; border-bottom: 1px solid #eee; overflow: hidden; font-size: 13px; }
.sub-row form { float: right; }
.sub-row form button { font-size: 12px; background: none; border: 1px solid #ccc; padding: 2px 8px; cursor: pointer; }
.err { color: #a00; margin-bottom: 10px; font-size: 14px; }
</style>"""


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _kindle_wrap(content: str, title: str = "Quick Tasks") -> str:
    return (
        "<!DOCTYPE html><html lang='pt-BR'><head>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        "<title>" + _esc(title) + "</title>"
        + KINDLE_CSS
        + "</head><body>"
        "<div id='wrap'>"
        "<div id='hdr'>"
        "<h1>Quick Tasks</h1>"
        "<a class='hbtn' href='/kindle/new'>+ Nova Task</a>"
        "<button class='hbtn hbtn-sec' onclick='toggleLandscape()'>&#x1F504;</button>"
        "<div style='clear:both'></div>"
        "</div>"
        + content
        + "</div>"
        "<script>"
        # WebKit 528/Safari 4: sem vh/vw e sem String.trim(). Tudo em px via JS.
        "function _trim(s){return s.replace(/^\\s+|\\s+$/g,'');}"
        "function _lsApply(w){"
        "var W=window.innerWidth||document.documentElement.clientWidth||600;"
        "var H=window.innerHeight||document.documentElement.clientHeight||800;"
        "w.style.width=H+'px';w.style.height=W+'px';"          # area de leitura (paisagem)
        "w.style.webkitTransformOrigin='top left';"
        "w.style.webkitTransform='translateX('+W+'px) rotate(90deg)';"  # gira 90deg e encaixa na tela
        "}"
        "function _lsClear(w){"
        "w.style.width='';w.style.height='';"
        "w.style.webkitTransform='';w.style.webkitTransformOrigin='';"
        "}"
        "function toggleLandscape(){"
        "var h=document.documentElement,w=document.getElementById('wrap');"
        "var on=w.className.indexOf('landscape')>=0;"
        "if(on){h.className=_trim(h.className.replace(/\\blandscape\\b/g,''));"
        "w.className=_trim(w.className.replace(/\\blandscape\\b/g,''));"
        "_lsClear(w);"
        "try{localStorage.setItem('kls','0');}catch(e){}}"
        "else{h.className=_trim(h.className+' landscape');"
        "w.className=_trim(w.className+' landscape');"
        "_lsApply(w);"
        "try{localStorage.setItem('kls','1');}catch(e){}}"
        "}"
        "(function(){try{if(localStorage.getItem('kls')==='1'){"
        "var h=document.documentElement,w=document.getElementById('wrap');"
        "h.className=_trim(h.className+' landscape');"
        "if(w){w.className=_trim(w.className+' landscape');_lsApply(w);}"
        "}}catch(e){}})();"
        "</script>"
        "</body></html>"
    )


def _kindle_get_all_tasks() -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE parent_id IS NULL ORDER BY order_index, created_at"
    ).fetchall()
    result = []
    for row in rows:
        task = dict(row)
        subs = conn.execute(
            "SELECT * FROM tasks WHERE parent_id = ? ORDER BY order_index, created_at",
            (task["id"],)
        ).fetchall()
        task["subtasks"] = [dict(s) for s in subs]
        result.append(task)
    conn.close()
    return result


def _kindle_get_task(task_id: int) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        conn.close()
        return None
    task = dict(row)
    subs = conn.execute(
        "SELECT * FROM tasks WHERE parent_id = ? ORDER BY order_index, created_at",
        (task_id,)
    ).fetchall()
    task["subtasks"] = [dict(s) for s in subs]
    conn.close()
    return task


def _kindle_task_card(task: dict) -> str:
    subs = task.get("subtasks", [])
    done_subs = sum(1 for s in subs if s.get("status") == "done")
    tid = str(task["id"])

    badges = ""
    if task.get("is_urgent"):
        badges += "<span class='badge'>[U]</span>"
    if task.get("is_important"):
        badges += "<span class='badge'>[I]</span>"

    status = task.get("status", "todo")
    if status == "todo":
        moves = (
            "<form method='post' action='/kindle/" + tid + "/move'>"
            "<input type='hidden' name='to' value='doing'/>"
            "<button>-&gt; Doing</button></form>"
        )
    elif status == "doing":
        moves = (
            "<form method='post' action='/kindle/" + tid + "/move'>"
            "<input type='hidden' name='to' value='todo'/>"
            "<button>&lt;- Todo</button></form>"
            "<form method='post' action='/kindle/" + tid + "/move'>"
            "<input type='hidden' name='to' value='waiting'/>"
            "<button>-&gt; Waiting</button></form>"
        )
    elif status == "waiting":
        moves = (
            "<form method='post' action='/kindle/" + tid + "/move'>"
            "<input type='hidden' name='to' value='doing'/>"
            "<button>&lt;- Doing</button></form>"
            "<form method='post' action='/kindle/" + tid + "/move'>"
            "<input type='hidden' name='to' value='done'/>"
            "<button>-&gt; Done</button></form>"
        )
    else:
        moves = (
            "<form method='post' action='/kindle/" + tid + "/move'>"
            "<input type='hidden' name='to' value='waiting'/>"
            "<button>&lt;- Waiting</button></form>"
        )

    return (
        "<div class='" + ("card urgent" if task.get("is_urgent") else "card") + "'>"
        "<div class='ctitle'>" + _esc(task.get("title", "")) + "</div>"
        + ("<p class='cdesc'>" + _esc(task.get("description", "")) + "</p>" if task.get("description") else "")
        + ("<div class='cbadges'>" + badges + "</div>" if badges else "")
        + ("<div style='font-size:12px;color:#666;margin-bottom:4px'>Sub: " + str(done_subs) + "/" + str(len(subs)) + "</div>" if subs else "")
        + "<div class='cactions'>"
        + moves
        + " <a href='/kindle/" + tid + "/edit'>Editar</a>"
        + " <a href='/kindle/" + tid + "/confirm-delete'>Deletar</a>"
        + "</div></div>"
    )


def _kindle_main_html(tasks: list) -> str:
    doing   = [t for t in tasks if t.get("status") == "doing"]
    todo    = [t for t in tasks if t.get("status") == "todo"]
    waiting = [t for t in tasks if t.get("status") == "waiting"]
    done    = [t for t in tasks if t.get("status") == "done"]

    def section_html(label, group):
        cards = "".join(_kindle_task_card(t) for t in group) if group else "<div class='empty'>Nenhuma task</div>"
        return (
            "<div class='section'>"
            "<div class='sec-head'>" + label + "<span class='sec-cnt'>" + str(len(group)) + "</span></div>"
            + cards + "</div>"
        )

    return _kindle_wrap(
        "<div id='main'>"
        + section_html("Doing", doing)
        + section_html("To Do", todo)
        + section_html("Waiting Thirdparties", waiting)
        + section_html("Done", done)
        + "</div>"
    )


def _kindle_new_form_html(default_status: str = "todo", error: str = "") -> str:
    opts = "".join(
        "<option value='" + v + "'" + (" selected" if v == default_status else "") + ">" + l + "</option>"
        for v, l in [("todo", "To Do"), ("doing", "Doing"), ("waiting", "Waiting Thirdparties"), ("done", "Done")]
    )
    return _kindle_wrap(
        "<div class='fp'><h2>Nova Task</h2>"
        + ("<p class='err'>" + _esc(error) + "</p>" if error else "")
        + "<form method='post' action='/kindle/new'>"
        + "<div class='fg'><label>Titulo *</label>"
        + "<input type='text' name='title' placeholder='O que precisa ser feito?' /></div>"
        + "<div class='fg'><label>Descricao</label>"
        + "<textarea name='description' rows='3' placeholder='Detalhes opcionais...'></textarea></div>"
        + "<div class='fg'><label>Status</label><select name='status'>" + opts + "</select></div>"
        + "<div class='fg cr'>"
        + "<label><input type='checkbox' name='is_urgent' value='1' /> Urgente</label>"
        + "<label><input type='checkbox' name='is_important' value='1' /> Importante</label>"
        + "</div>"
        + "<div class='fa'><button class='bsub' type='submit'>Salvar</button>"
        + "<a href='/kindle'>Cancelar</a></div>"
        + "</form></div>",
        "Nova Task"
    )


def _kindle_edit_form_html(task: dict, error: str = "") -> str:
    tid = str(task["id"])
    opts = "".join(
        "<option value='" + v + "'" + (" selected" if v == task.get("status") else "") + ">" + l + "</option>"
        for v, l in [("todo", "To Do"), ("doing", "Doing"), ("waiting", "Waiting Thirdparties"), ("done", "Done")]
    )
    subs = task.get("subtasks", [])
    sub_html = ""
    if subs:
        sub_html = "<div class='fg'><label>Subtasks</label>"
        for s in subs:
            strike = " style='text-decoration:line-through;color:#888'" if s.get("status") == "done" else ""
            sub_html += (
                "<div class='sub-row'>"
                "<span" + strike + ">" + _esc(s.get("title", "")) + "</span>"
                "<form method='post' action='/kindle/" + str(s["id"]) + "/delete-sub'>"
                "<button type='submit'>[remover]</button></form>"
                "</div>"
            )
        sub_html += "</div>"

    return _kindle_wrap(
        "<div class='fp'><h2>Editar Task</h2>"
        + ("<p class='err'>" + _esc(error) + "</p>" if error else "")
        + "<form method='post' action='/kindle/" + tid + "/edit'>"
        + "<div class='fg'><label>Titulo *</label>"
        + "<input type='text' name='title' value='" + _esc(task.get("title", "")) + "' /></div>"
        + "<div class='fg'><label>Descricao</label>"
        + "<textarea name='description' rows='3'>" + _esc(task.get("description", "")) + "</textarea></div>"
        + "<div class='fg'><label>Status</label><select name='status'>" + opts + "</select></div>"
        + "<div class='fg cr'>"
        + "<label><input type='checkbox' name='is_urgent' value='1'" + (" checked" if task.get("is_urgent") else "") + " /> Urgente</label>"
        + "<label><input type='checkbox' name='is_important' value='1'" + (" checked" if task.get("is_important") else "") + " /> Importante</label>"
        + "</div>"
        + sub_html
        + "<div class='fg'><label>Adicionar Subtask</label>"
        + "<input type='text' name='new_subtask' placeholder='Titulo da nova subtask (opcional)' /></div>"
        + "<div class='fa'><button class='bsub' type='submit'>Salvar</button>"
        + "<a href='/kindle'>Cancelar</a></div>"
        + "</form></div>",
        "Editar Task"
    )


def _kindle_confirm_html(task: dict) -> str:
    tid = str(task["id"])
    return _kindle_wrap(
        "<div class='fp'><h2>Deletar task?</h2>"
        + "<p style='margin-bottom:14px'>\"" + _esc(task.get("title", "")) + "\" e todas as subtasks serao removidas permanentemente.</p>"
        + "<form method='post' action='/kindle/" + tid + "/delete'>"
        + "<button class='bsub' type='submit'>Confirmar</button></form>"
        + " <a href='/kindle' style='margin-left:10px'>Cancelar</a>"
        + "</div>",
        "Confirmar"
    )


# ─── KINDLE ROUTES ────────────────────────────────────────────────────────────

@app.get("/kindle", response_class=HTMLResponse)
def kindle_root():
    tasks = _kindle_get_all_tasks()
    return HTMLResponse(_kindle_main_html(tasks))


@app.get("/kindle/new", response_class=HTMLResponse)
def kindle_new_page(status: str = "todo"):
    return HTMLResponse(_kindle_new_form_html(status))


@app.post("/kindle/new")
async def kindle_create(
    title: str = Form(""),
    description: str = Form(""),
    status: str = Form("todo"),
    is_urgent: Optional[str] = Form(None),
    is_important: Optional[str] = Form(None),
):
    title = title.strip()
    if not title:
        return HTMLResponse(_kindle_new_form_html(status, "Titulo e obrigatorio"))
    conn = get_db()
    max_order = conn.execute(
        "SELECT MAX(order_index) FROM tasks WHERE status = ? AND parent_id IS NULL", (status,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO tasks (title, description, status, is_urgent, is_important, order_index) VALUES (?, ?, ?, ?, ?, ?)",
        (title, description.strip(), status, 1 if is_urgent else 0, 1 if is_important else 0, (max_order or 0) + 1000)
    )
    conn.commit()
    conn.close()
    return RedirectResponse("/kindle", status_code=303)


@app.get("/kindle/{task_id}/edit", response_class=HTMLResponse)
def kindle_edit_page(task_id: int):
    task = _kindle_get_task(task_id)
    if not task:
        return RedirectResponse("/kindle", status_code=303)
    return HTMLResponse(_kindle_edit_form_html(task))


@app.post("/kindle/{task_id}/edit")
async def kindle_update(
    task_id: int,
    title: str = Form(""),
    description: str = Form(""),
    status: str = Form("todo"),
    is_urgent: Optional[str] = Form(None),
    is_important: Optional[str] = Form(None),
    new_subtask: str = Form(""),
):
    title = title.strip()
    task = _kindle_get_task(task_id)
    if not task:
        return RedirectResponse("/kindle", status_code=303)
    if not title:
        return HTMLResponse(_kindle_edit_form_html(task, "Titulo e obrigatorio"))
    conn = get_db()
    conn.execute(
        "UPDATE tasks SET title=?, description=?, status=?, is_urgent=?, is_important=?, updated_at=? WHERE id=?",
        (title, description.strip(), status, 1 if is_urgent else 0, 1 if is_important else 0, datetime.now().isoformat(), task_id)
    )
    ns = new_subtask.strip()
    if ns:
        max_ord = conn.execute("SELECT MAX(order_index) FROM tasks WHERE parent_id = ?", (task_id,)).fetchone()[0]
        conn.execute(
            "INSERT INTO tasks (title, status, order_index, parent_id) VALUES (?, 'todo', ?, ?)",
            (ns, (max_ord or 0) + 1000, task_id)
        )
    conn.commit()
    conn.close()
    return RedirectResponse("/kindle", status_code=303)


@app.post("/kindle/{task_id}/move")
async def kindle_move(task_id: int, to: str = Form("todo")):
    conn = get_db()
    conn.execute("UPDATE tasks SET status=?, updated_at=? WHERE id=?",
                 (to, datetime.now().isoformat(), task_id))
    conn.commit()
    conn.close()
    return RedirectResponse("/kindle", status_code=303)


@app.get("/kindle/{task_id}/confirm-delete", response_class=HTMLResponse)
def kindle_confirm_delete_page(task_id: int):
    task = _kindle_get_task(task_id)
    if not task:
        return RedirectResponse("/kindle", status_code=303)
    return HTMLResponse(_kindle_confirm_html(task))


@app.post("/kindle/{task_id}/delete")
async def kindle_delete(task_id: int):
    conn = get_db()
    conn.execute("DELETE FROM tasks WHERE parent_id = ?", (task_id,))
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/kindle", status_code=303)


@app.post("/kindle/{task_id}/delete-sub")
async def kindle_delete_sub(task_id: int):
    conn = get_db()
    sub = conn.execute("SELECT parent_id FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    parent_id = sub["parent_id"] if sub else None
    conn.close()
    if parent_id:
        return RedirectResponse("/kindle/" + str(parent_id) + "/edit", status_code=303)
    return RedirectResponse("/kindle", status_code=303)


# ─── STATIC & ROOT ────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
