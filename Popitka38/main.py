import re
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Query, Form, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="Banana")
app.mount("/static", StaticFiles(directory="static"))
templates = Jinja2Templates(directory="templates")

def get_db():
    conn = psycopg2.connect(database="passRF", user="postgres", password="123", host="localhost", port="5432")
    conn.cursor_factory = psycopg2.extras.DictCursor
    return conn

def init_db():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            create table if not exists users(
                    id serial primary key,
                    login text unique not null,
                    password text not null,
                    date_b text not null,
                    fio text not null,
                    email text not null,
                    phone text not null
                    );
            """)
        cur.execute("""
            create table if not exists requests(
                    id serial primary key,
                    user_id integer references users(id) on delete cascade,
                    transport text not null,
                    date_start text not null,
                    payment_method text not null,
                    status text default 'Новая',
                    review text 
                    );
            """)
        conn.commit()

init_db()


@app.get("/")
def get_base(request: Request):
    return RedirectResponse("/login", status_code=302)

@app.get("/logout")
def get_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

@app.get("/register")
def get_register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@app.get("/login")
def get_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/register")
def post_register(request: Request,
                  login: str = Form(...),
                  password: str = Form(...),
                  date_b: str = Form(...),
                  fio: str = Form(...),
                  email: str = Form(...),
                  phone: str = Form(...)):
    
    error = None

    if not re.fullmatch(r'[a-zA-Z0-9]{6,}',login):
        error = "Логин: Латиница и цифры, минимум 6 символов"
    elif len(password) < 8:
        error = "Пароль: Минимум 8 символов"
    elif not re.fullmatch(r'[а-яА-ЯёЁ\s]+',fio):
        error = "ФИО: Кириллица и пробелы"
    elif not re.fullmatch(r'[^@]+@[^@]+\.[^@]+',email):
        error = "Почта: Неверный формат"
    elif not re.fullmatch(r'8\(\d{3}\)\d{3}-\d{2}-\d{2}',phone):
        error = "Телефон: Маска 8(XXX)XXX-XX-XX"
    else:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("select * from users where login = %s", (login,))
            user = cur.fetchone()
            if not user:
                cur.execute("insert into users (login,password,fio,date_b,email,phone) values (%s,%s,%s,%s,%s,%s)",(login,password,fio,date_b,email,phone))
                conn.commit()
                return RedirectResponse("/login", status_code=302)
            else:
                error = "Логин уже занят"

    return templates.TemplateResponse("register.html", {"request": request, "error": error, "login": login, "date_b": date_b, "fio": fio, "email": email, "phone": phone})


@app.post("/login")
def post_login(request: Request,
                  login: str = Form(...),
                  password: str = Form(...)):
    
    if login == "Admin26":
        if password == "Demo20":
            request.session["admin"] = True
            return RedirectResponse("/admin", status_code=302)
        else:
            return templates.TemplateResponse("login.html", {"request": request, "error": "Неверные данные"})

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("select * from users where login = %s", (login,))
        user = cur.fetchone()
        if user and user["password"] == password:
            request.session["user_id"] = user["id"]
            return RedirectResponse("/profile", status_code=302)

    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверные данные"})


@app.get("/profile")
def get_profile(request: Request):

    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)
    
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("select * from requests where user_id = %s", (user_id,))
        requests_list = cur.fetchall()

    return templates.TemplateResponse("profile.html", {"request": request, "requests": requests_list})

TRANSPORTS = ["Автобус","Электробус","Трамвай"]
PAYMENTS = ["Наличные", "Перевод по номеру"]

@app.get("/create_request")
def get_create_request(request: Request):

    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse("create_request.html", {"request": request, "transports": TRANSPORTS, "payments": PAYMENTS})

@app.post("/create_request")
def post_create_request(
    request: Request,
    transport: str = Form(...),
    date: str = Form(...),
    payment: str = Form(...),
    change_amount: float | None = Form(None)   # новое поле, необязательное
):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    # Если оплата не наличными, игнорируем change_amount (ставим NULL)
    if payment != "Наличные":
        change_amount = None

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO requests (transport, date_start, payment_method, user_id, change_amount) VALUES (%s, %s, %s, %s, %s)",
            (transport, date, payment, user_id, change_amount)
        )
        conn.commit()
        return RedirectResponse("/profile", status_code=302)


@app.get("/admin")
def get_admin(
    request: Request,
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(5, ge=1, le=50),
    sort_by: str = Query("id", regex="^(id|date_start|status)$"),
    order: str = Query("desc", regex="^(asc|desc)$")
):
    if not request.session.get("admin"):
        return RedirectResponse("/login", status_code=302)

    # 1. Построение запроса с фильтрацией
    base = """
        SELECT requests.*, users.login, users.fio
        FROM requests, users
        WHERE requests.user_id = users.id
    """
    params = []
    if status and status != "Все":
        base += " AND status = %s"
        params.append(status)

    # 2. Сортировка
    sort_dir = "ASC" if order == "asc" else "DESC"
    base += f" ORDER BY {sort_by} {sort_dir}"

    # 3. Пагинация (LIMIT и OFFSET)
    offset = (page - 1) * per_page
    base += " LIMIT %s OFFSET %s"
    params.extend([per_page, offset])

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(base, params)
        requests_list = cur.fetchall()

        # 4. Получить общее количество записей (для пагинации)
        count_sql = """
            SELECT COUNT(*) FROM requests
        """
        count_params = []
        if status and status != "Все":
            count_sql += " WHERE status = %s"
            count_params.append(status)
        cur.execute(count_sql, count_params)
        total = cur.fetchone()[0]

    total_pages = (total + per_page - 1) // per_page

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "requests": requests_list,
        "cur_status": status or "Все",
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total": total,
        "sort_by": sort_by,
        "order": order
    })
@app.post("/add_review")
def post_add_review(request: Request,
                    request_id: str = Form(...),
                    review: str = Form(...)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)
    
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("select * from requests where id = %s and status = 'Обучение завершено' and review is null",(request_id,))
        isdate = cur.fetchone()
        if isdate:
            cur.execute("update requests set review = %s where id = %s", (review,request_id))
            conn.commit()
        return RedirectResponse("/profile", status_code=302)

@app.post("/admin/change_status")
def post_add_review(request: Request,
                    request_id: str = Form(...),
                    status: str = Form(...)):
    user_id = request.session.get("admin")
    if not user_id:
        return RedirectResponse("/login", status_code=302)
    
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("update requests set status = %s where id = %s", (status,request_id))
        conn.commit()
        return RedirectResponse(f"/admin?msg=updated&status={request.query_params.get('status', '')}", status_code=302)


