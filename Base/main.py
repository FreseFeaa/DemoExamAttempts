import re
import bcrypt
from datetime import datetime

import sqlite3
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware


# ---------- НАСТРОЙКИ ПРИЛОЖЕНИЯ ----------
app = FastAPI()
# Добавляем поддержку сессий (подписанные cookies)
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")
# Подключаем папку с HTML-шаблонами
templates = Jinja2Templates(directory="templates")

# ---------- РАБОТА С БАЗОЙ ДАННЫХ SQLITE ----------
DATABASE = "database.db"

def get_db():
    """Возвращает соединение с БД, строки преобразуются в словареподобные объекты."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Создаёт таблицы users и requests, если их ещё нет."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                login TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                fullname TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                course_name TEXT NOT NULL CHECK(course_name IN ('Основы алгоритмизации и программирования', 'Основы веб-дизайна', 'Основы проектирования баз данных')),
                start_date DATE NOT NULL,
                payment_method TEXT NOT NULL CHECK(payment_method IN ('наличными', 'переводом по номеру телефона')),
                status TEXT DEFAULT 'Новая' CHECK(status IN ('Новая', 'Идет обучение', 'Обучение завершено')),
                review TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

# Инициализация БД при запуске
init_db()

# ---------- ФУНКЦИИ ДЛЯ ХЕШИРОВАНИЯ ПАРОЛЕЙ (bcrypt) ----------
def hash_password(password: str) -> str:
    """Принимает сырой пароль, возвращает хеш (строку)."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    """Проверяет, совпадает ли сырой пароль с хешем."""
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))

# ---------- РЕГИСТРАЦИЯ ----------
@app.get("/register")
def register_form(request: Request):
    """Показывает форму регистрации."""
    return templates.TemplateResponse("register.html", {"request": request, "error": None})

@app.post("/register")
def register_post(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    fio: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...)
):
    """Обрабатывает отправку формы регистрации."""
    error = None

    # Валидация полей
    if not re.match(r'^[a-zA-Z0-9]{6,}$', login):
        error = "Логин: только латиница и цифры, минимум 6 символов"
    elif len(password) < 8:
        error = "Пароль минимум 8 символов"
    elif len(password.encode('utf-8')) > 72:  # bcrypt ограничение
        error = "Пароль слишком длинный (максимум 72 байта в UTF-8)"
    elif not re.match(r'^[а-яА-ЯёЁ\s]+$', fio):
        error = "ФИО только кириллица и пробелы"
    elif not re.match(r'^8\(\d{3}\)\d{3}-\d{2}-\d{2}$', phone):
        error = "Телефон в формате 8(XXX)XXX-XX-XX"
    elif not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        error = "Некорректный email"
    else:
        with get_db() as conn:
            # Проверяем, не занят ли логин
            cur = conn.execute("SELECT id FROM users WHERE login = ?", (login,))
            if cur.fetchone():
                error = "Логин уже занят"
            else:
                # Всё хорошо – сохраняем пользователя
                hashed = hash_password(password)
                conn.execute(
                    "INSERT INTO users (login, password, fullname, phone, email) VALUES (?,?,?,?,?)",
                    (login, hashed, fio, phone, email)
                )
                # После успешной регистрации отправляем на страницу входа
                return RedirectResponse(url="/login", status_code=302)

    # Если были ошибки, снова показываем форму с сообщением
    return templates.TemplateResponse("register.html", {"request": request, "error": error})

# ---------- АВТОРИЗАЦИЯ (ЕДИНАЯ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ И АДМИНА) ----------
@app.get("/login")
def login_form(request: Request):
    """Показывает форму входа."""
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
def login_post(
    request: Request,
    login: str = Form(...),
    password: str = Form(...)
):
    """Обрабатывает вход: проверяет админа (хардкод) или обычного пользователя."""
    # Проверка на администратора (жёстко заданные логин/пароль)
    if login == "Admin" and password == "KorokNET":
        request.session["admin"] = True          # ставим флаг админа в сессии
        return RedirectResponse(url="/admin", status_code=302)

    # Проверка обычного пользователя по БД
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE login = ?", (login,)).fetchone()
        if user and verify_password(password, user["password"]):
            request.session["user_id"] = user["id"]   # запоминаем ID пользователя
            return RedirectResponse(url="/profile", status_code=302)
        else:
            # Ошибка: неверный логин или пароль
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Неверный логин или пароль"}
            )

# ---------- ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ (СПИСОК ЕГО ЗАЯВОК) ----------
@app.get("/profile")
def profile(request: Request):
    """Показывает все заявки текущего пользователя."""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    with get_db() as conn:
        requests_list = conn.execute(
            "SELECT * FROM requests WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        ).fetchall()
    return templates.TemplateResponse(
        "profile.html",
        {"request": request, "requests": requests_list}
    )

# ---------- ДОБАВЛЕНИЕ ОТЗЫВА ----------
@app.post("/add_review")
def add_review(
    request: Request,
    request_id: int = Form(...),
    review: str = Form(...)
):
    """Сохраняет отзыв, если заявка принадлежит пользователю, статус 'завершено' и отзыва ещё нет."""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    with get_db() as conn:
        # Проверяем условия
        cur = conn.execute(
            """SELECT id FROM requests 
               WHERE id = ? AND user_id = ? AND status = 'Обучение завершено' AND review IS NULL""",
            (request_id, user_id)
        )
        if cur.fetchone():
            # Обновляем запись – добавляем отзыв
            conn.execute(
                "UPDATE requests SET review = ? WHERE id = ?",
                (review, request_id)
            )
    return RedirectResponse(url="/profile", status_code=302)

# ---------- СОЗДАНИЕ НОВОЙ ЗАЯВКИ ----------
COURSES = [
    "Основы алгоритмизации и программирования",
    "Основы веб-дизайна",
    "Основы проектирования баз данных"
]
PAYMENTS = ["наличными", "переводом по номеру телефона"]

@app.get("/create_request")
def create_request_form(request: Request):
    """Показывает форму создания заявки."""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        "create_request.html",
        {"request": request, "courses": COURSES, "payments": PAYMENTS, "error": None}
    )

@app.post("/create_request")
def create_request_post(
    request: Request,
    course: str = Form(...),
    date: str = Form(...),
    payment: str = Form(...)
):
    """Сохраняет новую заявку в БД после простейшей проверки даты."""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    error = None
    if not date:
        error = "Дата не указана"
    else:
        try:
            # Проверяем, что дата корректна (например, не 2025-02-30)
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            error = "Некорректная дата"
        else:
            # Всё ок – вставляем запись
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO requests (user_id, course_name, start_date, payment_method) VALUES (?,?,?,?)",
                    (user_id, course, date, payment)
                )
            return RedirectResponse(url="/profile", status_code=302)

    # Если ошибка, показываем форму снова
    return templates.TemplateResponse(
        "create_request.html",
        {"request": request, "courses": COURSES, "payments": PAYMENTS, "error": error}
    )

# ---------- ПАНЕЛЬ АДМИНИСТРАТОРА ----------
@app.get("/admin")
def admin_panel(request: Request):
    """Показывает все заявки всех пользователей (только для админа)."""
    if not request.session.get("admin"):
        return RedirectResponse(url="/login", status_code=302)

    with get_db() as conn:
        requests_list = conn.execute("""
            SELECT r.*, u.login, u.fullname FROM requests r
            JOIN users u ON r.user_id = u.id
            ORDER BY r.id DESC
        """).fetchall()
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "requests": requests_list}
    )

@app.post("/admin/change_status")
def change_status(
    request: Request,
    request_id: int = Form(...),
    status: str = Form(...)
):
    """Изменяет статус заявки (только для админа).""" 
    if not request.session.get("admin"):
        return RedirectResponse(url="/login", status_code=302)

    with get_db() as conn:
        conn.execute(
            "UPDATE requests SET status = ? WHERE id = ?",
            (status, request_id)
        )
    return RedirectResponse(url="/admin", status_code=302)

# ---------- ВЫХОД ИЗ СИСТЕМЫ ----------
@app.get("/logout")
def logout(request: Request):
    """Очищает сессию и перенаправляет на страницу входа."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)