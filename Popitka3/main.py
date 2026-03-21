import sqlite3
import re
import bcrypt
from datetime import datetime

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware


app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="Banana")

templates = Jinja2Templates(directory="templates")

DATABASE = "database.db"

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
    create table if not exists users(
        id integer primary key autoincrement,
        login text not null unique,
        password  text not null,
        fio  text not null,
        email  text not null,
        phone  text not null 
                           );

    create table if not exists requests(
        id integer primary key autoincrement,
        user_id integer not null,
        course_name  text not null,
        date_start  text not null,
        payment_method  text not null,
        status text not null default 'Новая',
        foreign key (user_id) references users(id) on delete cascade
                           );

""")
init_db()

@app.get("/register")
def get_register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})

@app.get("/login")
def get_register(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.get("/")
def get_base(request: Request):
    return RedirectResponse(url="/login", status_code=302)



@app.post("/register")
def post_register(request: Request,
             login: str = Form(...),
             password: str = Form(...),
             fio: str = Form(...),
             email: str = Form(...),
             phone: str = Form(...)):
    
    with get_db() as conn:
        conn.execute("insert into users (login, password,fio,email,phone) values(?,?,?,?,?)", (login,password,fio,email,phone))
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("register.html", {"request": request, "error": "Чет не так"})

@app.post("/login")
def post_login(request: Request,
             login: str = Form(...),
             password: str = Form(...)):
    
    if login == "Admin" and password == "KorokNET":
        request.session["admin"] = True
        return RedirectResponse(url="/admin", status_code=302)


    with get_db() as conn:
        user =conn.execute("select * from users where login = ?", (login,)).fetchone()
        if user and user["password"] == password:
            request.session["user_id"] = user["id"]
            return RedirectResponse(url="/profile", status_code=302)

    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})

COURSES = [    "Основы алгоритмизации и программирования",
    "Основы веб-дизайна",
    "Основы проектирования баз данных"
]
PAYMENTS = ["Наличными", "Переводом по номеру телефона"]

@app.get("/create_request")
def get_create_request(request: Request):
    user_id = request.session["user_id"]
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("create_request.html", {"request": request, "courses": COURSES, "payments":PAYMENTS})

@app.post("/create_request")
def post_register(request: Request,
             course_name: str = Form(...),
             date: str = Form(...),
             payment_method: str = Form(...)):
    user_id = request.session["user_id"]
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        conn.execute("insert into requests (user_id, course_name,date_start,payment_method) values(?,?,?,?)", (user_id,course_name,date,payment_method))
        return RedirectResponse(url="/profile", status_code=302)



@app.get("/profile")
def get_profile(request: Request):
    user_id = request.session["user_id"]
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        requests_list = conn.execute("select * from requests where user_id = ?", (user_id,)).fetchall()
    
    return templates.TemplateResponse("profile.html", {"request": request, "requests": requests_list})

@app.get("/admin")
def get_profile(request: Request):
    user_id =  request.session.get("admin")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        requests_list = conn.execute("SELECT requests.*, users.login, users.fio FROM requests, users WHERE requests.user_id = users.id").fetchall()
    
    return templates.TemplateResponse("admin.html", {"request": request, "requests": requests_list})



@app.get("/logout")
def get_profile(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
