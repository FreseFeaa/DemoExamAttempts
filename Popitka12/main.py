import re
import sqlite3
from fastapi import FastAPI, Form, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="banana")

templates = Jinja2Templates(directory="templates")

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
create table if not exists users(
                           id integer primary key autoincrement,
                           login text unique not null,
                           password text not null,
                           fio text not null,
                           phone text not null,
                           email text not null
                           );

create table if not exists requests(
                           id integer primary key autoincrement,
                           user_id integer references users(id) on delete cascade,
                           course_name text not null,
                           payment_method text not null,
                           date_start text not null,
                           status text default 'Новая',
                           review text
                           );

""")
        


init_db()

@app.get("/")
def get_base(request: Request):
    return RedirectResponse(url="/login", status_code=302)

@app.get("/logout")
def get_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)

@app.get("/register")
def get_register(request: Request):
    return templates.TemplateResponse("register.html",{"request": request, "error": None})


@app.get("/login")
def get_login(request: Request):
    return templates.TemplateResponse("login.html",{"request": request, "error": None})

@app.post("/register")
def post_register(request: Request,
                  login: str = Form(...),
                  password: str = Form(...),
                  fio: str = Form(...),
                  email: str = Form(...),
                  phone: str = Form(...)):
    
    error = None

    if not re.fullmatch(r'[a-zA-Z0-9]{6,}', login):
        error = "Логин латинские буквы, больше 6 символов"
    elif len(password) < 8:
        error = "Пароль минимум 8 символов"
    elif not re.fullmatch(r'[а-яА-Я\s]+', fio):
        error = "ФИО кириллица и пробел"
    elif not re.fullmatch(r'8\(\d{3}\)-\d{3}-\d{2}-\d{2}', phone):
        error = "Телефон формата 8(XXX)-XXX-XX-XX"
    elif not re.fullmatch(r'[^@]+@[^@]+\.[^@]+', email):
        error = "Неверный ввод почты"
    else:
        with get_db() as conn:
            cur = conn.execute("select * from users where login = ?" , (login,)).fetchone()
            if not cur:
                conn.execute("insert into users (login,password,fio,email,phone) values (?,?,?,?,?)" , (login,password,fio,email,phone))
                return RedirectResponse(url="/login", status_code=302)
            else:
                error = "Логин занят"
    return templates.TemplateResponse("register.html",{"request": request,"error": error,"login": login,"fio": fio,"phone": phone, "email": email})


@app.post("/login")
def post_login(request: Request,
                  login: str = Form(...),
                  password: str = Form(...)):

    if login == "Admin":
        if password == "KorokNET":
            request.session["admin"] = True
            return RedirectResponse(url="/admin", status_code=302)
        else:
            return templates.TemplateResponse("login.html",{"request": request, "error": "Неверные данные"})
            
    with get_db() as conn:
        user = conn.execute("select * from users where login = ?" , (login,)).fetchone()
        if user and user["password"] == password:
            request.session["user_id"] = user["id"]   
            return RedirectResponse(url="/profile", status_code=302)

    return templates.TemplateResponse("login.html",{"request": request, "error": "Неверные данные"})



@app.get("/profile")
def get_profile(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        requests_list = conn.execute("select * from requests where user_id = ?", (user_id,)).fetchall()

    return templates.TemplateResponse("profile.html",{"request": request, "requests": requests_list})

COURSES = ["Алгоритмы", "Базы данных" , "Оригами"]
PAYMENTS = ["Наличные", "Перевод по номеру" ]


@app.get("/create_request")
def get_create_request(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse("create_request.html",{"request": request, "courses": COURSES, "payments": PAYMENTS})


@app.post("/create_request")
def post_create_request(request: Request,
                        course: str = Form(...),
                        date: str = Form(...),
                        payment: str = Form(...)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        conn.execute("insert into requests (course_name,date_start,payment_method,user_id) values (?,?,?,?)" , (course,date,payment,user_id))

    return RedirectResponse(url="/profile", status_code=302)



@app.get("/admin")
def get_admin(request: Request):
    user_id = request.session.get("admin")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        requests_list = conn.execute("select requests.*, users.login, users.fio from requests, users where requests.user_id = users.id").fetchall()

    return templates.TemplateResponse("admin.html",{"request": request, "requests": requests_list})


@app.post("/add_review")
def post_add_review(request: Request,
                        review: str = Form(...),
                        request_id: str = Form(...)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        cur = conn.execute("select * from requests where id = ? AND status = 'Обучение завершено' AND review is null" , (request_id,)).fetchone()
        if cur:
            conn.execute("update requests set review = ? where id = ?", (review, request_id))

    return RedirectResponse(url="/profile", status_code=302)

@app.post("/admin/change_status")
def post_add_review(request: Request,
                        status: str = Form(...),
                        request_id: str = Form(...)):
    user_id = request.session.get("admin")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        conn.execute("update requests set status = ? where id = ?", (status, request_id))
    return RedirectResponse(url="/admin", status_code=302)