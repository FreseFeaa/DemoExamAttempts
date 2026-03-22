import sqlite3
from fastapi import FastAPI, Form , Request
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
            login text unique not null,
            password text not null,
            email text not null,
            phone text not null,
            fio text not null
                           );


    create table if not exists requests(
            id integer primary key autoincrement,
            user_id integer references user(id) on delete cascade, 
            course_name text not null,
            payment_method text not null,
            date_start text not null,
            status text not null default 'Новая'
                           );                           
""")
init_db()

@app.get("/login")
def get_login(request: Request):
    return templates.TemplateResponse("login.html",{"request":request, "error": None})


@app.get("/register")
def get_register(request: Request):
    return templates.TemplateResponse("register.html",{"request":request, "error": None})

@app.get("/")
def get_base(request: Request):
    return RedirectResponse(url="/login", status_code=302)

@app.get("/logout")
def get_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)

@app.post("/register")
def post_register(request: Request,
                  login: str = Form(...),
                  password: str = Form(...),
                  fio: str = Form(...),
                  email: str = Form(...),
                  phone: str = Form(...)):
    with get_db() as conn:
        conn.execute("insert into users (login,password,email,phone,fio) values (?,?,?,?,?)",(login,password,email,phone,fio))
        return RedirectResponse(url="/login", status_code=302)


@app.post("/login")
def post_login(request: Request,
                  login: str = Form(...),
                  password: str = Form(...)):
    
    if login == "Admin":
        if password == "KorokNET":
            request.session["admin"] = True
            return RedirectResponse(url="/admin", status_code=302)
        else:
            return templates.TemplateResponse("login.html",{"request":request, "error": "Неверные данные"})
        
    with get_db() as conn:
        user = conn.execute("select * from users where login = ?",(login,)).fetchone()
        if user and password == user["password"]:
            request.session["user_id"] = user["id"]
            return RedirectResponse(url="/profile", status_code=302)
        return templates.TemplateResponse("login.html",{"request":request, "error": "Неверные данные"})
    
@app.get("/profile")
def get_profile(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        requests_list = conn.execute("select * from requests where user_id = ?",(user_id,)).fetchall()
    
    return templates.TemplateResponse("profile.html",{"request":request, "requests": requests_list})


COURSES = [    "Основы алгоритмизации и программирования",
    "Основы веб-дизайна",
    "Основы проектирования баз данных"
]
PAYMENTS = ["Наличными", "Переводом по номеру телефона"]

@app.get("/create_request")
def get_create_request(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    return templates.TemplateResponse("create_request.html",{"request":request, "courses": COURSES, "payments": PAYMENTS})

@app.post("/create_request")
def post_create_request(request: Request,
                  course: str = Form(...),
                  date: str = Form(...),
                  payment: str = Form(...)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn: 
        conn.execute("insert into requests (user_id,course_name,payment_method,date_start) values (?,?,?,?)",(user_id,course,payment,date))
    
    return RedirectResponse(url="/profile", status_code=302)

@app.get("/admin")
def get_admin(request: Request):
    user_id = request.session.get("admin")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        requests_list = conn.execute("select requests.*, users.login, users.fio from requests, users where requests.user_id = users.id").fetchall()
    return templates.TemplateResponse("admin.html",{"request":request, "requests": requests_list})

