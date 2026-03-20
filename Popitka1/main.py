import sqlite3
import re
import bcrypt
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key="BANANA")
templates = Jinja2Templates(directory="templates")

DATABASE = "database.db"

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript(
"""

create table if not exists users(
id integer PRIMARY KEY AUTOINCREMENT,
login text unique not null,
password text not null,
fullname text not null,
phone text not null,
email text not null
);

create table if not exists requests(
id integer PRIMARY KEY AUTOINCREMENT,
user_id int  not null,
course_name text not null,
start_date text not null,
payment_method text not null,
status text not null DEFAULT 'Новая',
review text,
foreign key (user_id) references users(id) on delete cascade
);
"""

)

init_db()


def hash_password(password):
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'),salt)
    return hashed.decode('utf-8')

def verify_password(plain,hashed):
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))

@app.get("/register")
def register_form(request: Request):
    return templates.TemplateResponse("register.html",{"request":request, "error":None})

@app.post("/register")
def register_post(
                request: Request,
                login: str = Form(...),
                password: str = Form(...),
                fio: str = Form(...),
                phone: str = Form(...),
                email: str = Form(...), 
                ):

    erorr = None
    with get_db() as conn:
        cur = conn.execute("select id from users where login = ? ", (login,))
        if cur.fetchone():
            error = "Логин занят так-то"
        else:
            hashed = hash_password(password)
            conn.execute(
                "insert into users (login,password,fullname,phone,email) values (?,?,?,?,?)",
                (login,hashed,fio,phone,email)
            )
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("register.html",{"request":request, "error":erorr})

@app.get("/login")
def register_form(request: Request):
    return templates.TemplateResponse("login.html",{"request":request, "error":None})

@app.post("/login")
def register_post(
                request: Request,
                login: str = Form(...),
                password: str = Form(...),
                ):
    if login == "Admin" and password == "KorokNET":
        request.session["admin"] = True
        return RedirectResponse(url="/admin", status_code=302)


    with get_db() as conn:
        user = conn.execute("select * from users where login = ? ", (login,)).fetchone()
        if user and verify_password(password, user["password"]):
            request.session["user_id"]= user["id"]
            return RedirectResponse(url="/profile",status_code=302)
        else:
            return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль или логин"})
        

@app.get("/profile")
def register_form(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login",status_code=302)
    
    with get_db() as conn:
        requests_list = conn.execute("select * from requests where user_id = ? order by id desc",(user_id,)).fetchall()
        return templates.TemplateResponse("profile.html",{"request":request, "requests":requests_list})

COURSES = [
    "Основы алгоритмизации и программирования",
    "Основы веб-дизайна",
    "Основы проектирования баз данных"
]
PAYMENTS = ["наличными", "переводом по номеру телефона"]

@app.get("/create_request")
def create_request_form(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login",status_code=302)
    return templates.TemplateResponse("create_request.html",{"request":request, "course":COURSES, "payments": PAYMENTS,"error":None})

@app.post("/create_request")
def create_request_post(request: Request,
                        course: str = Form(),
                        date: str = Form(),
                        payment: str = Form()):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login",status_code=302)
    with get_db() as conn:
        conn.execute("insert into requests (user_id,course_name,start_date,payment_method) values (?,?,?,?)",(user_id,course,date,payment))
    return RedirectResponse(url="/profile",status_code=302)


@app.get("/admin")
def admin_panel(request: Request):
    user_id = request.session.get("admin")
    if not user_id:
        return RedirectResponse(url="/login",status_code=302)
    with get_db() as conn:
        requests_list = conn.execute("select r.*, u.login, u.fullname from requests r join users u on r.user_id = u.id order by r.id desc").fetchall()
    return templates.TemplateResponse("admin.html",{"request":request, "requests":requests_list})

@app.post("/admin/change_status")
def change_status(request: Request,
                  request_id: int = Form(...),
                  status: int = Form(...)):
    if not request.session.get("admin"):
        return RedirectResponse(url="/login", status_code=302)
    with get_db() as conn:
        conn.execute("update requests set status ? where id = ?",(status,request_id))
    return RedirectResponse(url="/admin", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
