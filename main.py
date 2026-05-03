import os
import shutil
import asyncio
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import FastAPI, Request, Form, Depends, Cookie, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from deep_translator import GoogleTranslator
import bcrypt

# --- КОНФИГУРАЦИЯ ---
SECRET_KEY = "my_super_secret_key_123"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
ADMIN_EMAILS = {"info.globalmed.clinic@gmail.com", "bogdan.bondarenk0.2020@gmail.com"}

# --- РЕЗЕРВНЫЕ КОПИИ ---
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(_BASE_DIR, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

def make_backup():
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")
    dest = os.path.join(BACKUP_DIR, f"sql_app_{timestamp}.db")
    if os.path.exists(_DB_PATH):
        shutil.copy2(_DB_PATH, dest)

async def backup_loop():
    while True:
        await asyncio.sleep(3600)
        try:
            make_backup()
        except Exception:
            pass

# --- БАЗА ДАННЫХ ---
_DB_PATH = os.path.join(_BASE_DIR, "sql_app.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{_DB_PATH}"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- МОДЕЛИ ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)

class PatientInquiry(Base):
    __tablename__ = "inquiries"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    phone = Column(String)
    service = Column(String)
    user_id = Column(Integer, index=True)

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    author_name = Column(String)
    text = Column(String)
    rating = Column(Integer, default=5)
    created_at = Column(String)

Base.metadata.create_all(bind=engine)

# --- ИНИЦИАЛИЗАЦИЯ ---
app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(_BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))

@app.on_event("startup")
async def startup():
    make_backup()
    asyncio.create_task(backup_loop())

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_password_hash(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def ensure_admin():
    db = SessionLocal()
    try:
        for email in ADMIN_EMAILS:
            if not db.query(User).filter(User.email == email).first():
                db.add(User(email=email, password_hash=get_password_hash("Globalqwer")))
        db.commit()
    finally:
        db.close()

ensure_admin()

async def get_current_user(access_token: str = Cookie(None), db: Session = Depends(get_db)):
    if not access_token:
        return None
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
        return db.query(User).filter(User.email == email).first()
    except JWTError:
        return None

# --- ЭНДПОИНТЫ ---

@app.get("/", response_class=HTMLResponse)
async def read_home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"page_title": "Global Medicine Clinic"}
    )

@app.get("/about_us", response_class=HTMLResponse)
async def read_about(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="about_us.html",
        context={"page_title": "About us"}
    )

@app.get("/contacts", response_class=HTMLResponse)
async def contacts_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="contacts.html",
        context={"page_title": "Контакти — GlobalMed"}
    )

@app.get("/gallery", response_class=HTMLResponse)
async def gallery_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="gallery.html",
        context={"page_title": "Галерея — GlobalMed"}
    )

@app.get("/reviews", response_class=HTMLResponse)
async def reviews_page(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    user = await get_current_user(token, db)
    db_reviews = db.query(Review).order_by(Review.id.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="reviews.html",
        context={"page_title": "Відгуки — GlobalMed", "user": user, "db_reviews": db_reviews}
    )

@app.post("/reviews/submit")
async def submit_review(
    request: Request,
    author_name: str = Form(...),
    text: str = Form(...),
    rating: int = Form(5),
    db: Session = Depends(get_db)
):
    token = request.cookies.get("access_token")
    user = await get_current_user(token, db)
    if not user:
        return RedirectResponse(url="/reviews", status_code=302)
    from datetime import datetime as dt, timezone
    review = Review(
        user_id=user.id,
        author_name=author_name,
        text=text,
        rating=max(1, min(5, rating)),
        created_at=dt.now(timezone.utc).strftime("%d.%m.%Y")
    )
    db.add(review)
    db.commit()
    return RedirectResponse(url="/reviews", status_code=302)

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="privacy.html",
        context={"page_title": "Політика конфіденційності — GlobalMed"}
    )

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={"page_title": "Реєстрація — GlobalMed"}
    )

@app.post("/register")
async def register(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user_exists = db.query(User).filter(User.email == email).first()
    if user_exists:
        return {"error": "Email вже зареєстрований"}
    new_user = User(email=email, password_hash=get_password_hash(password))
    db.add(new_user)
    db.commit()
    return {"message": "Акаунт створено!"}

@app.post("/login")
async def login(response: Response, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return {"error": "Невірний email або пароль"}
    token = create_access_token(data={"sub": user.email})
    response.set_cookie(key="access_token", value=token, httponly=True)
    response.set_cookie(key="_auth", value="1", httponly=False, max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, samesite="lax")
    redirect = "/admin" if user.email in ADMIN_EMAILS else "/dashboard"
    return {"message": "Успішний вхід!", "redirect": redirect}

@app.get("/logout")
async def logout():
    resp = RedirectResponse(url="/", status_code=302)
    resp.delete_cookie("access_token")
    resp.delete_cookie("_auth")
    return resp

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    user = await get_current_user(token, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    if user.email in ADMIN_EMAILS:
        return RedirectResponse(url="/admin", status_code=302)
    my_inquiries = db.query(PatientInquiry).filter(PatientInquiry.user_id == user.id).all()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"user": user, "inquiries": my_inquiries}
    )

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    user = await get_current_user(token, db)
    if not user or user.email not in ADMIN_EMAILS:
        return RedirectResponse(url="/", status_code=302)

    all_users = db.query(User).all()
    users_map = {u.id: u.email for u in all_users}
    all_inquiries = db.query(PatientInquiry).order_by(PatientInquiry.id.desc()).all()

    rows = []
    for inq in all_inquiries:
        rows.append({
            "id": inq.id,
            "name": inq.name or "",
            "phone": inq.phone or "",
            "service": inq.service or "",
            "user_email": users_map.get(inq.user_id, "") if inq.user_id else "",
        })

    users_count = max(0, len(all_users) - 1)
    inquiries_count = len(rows)
    registered_count = sum(1 for r in rows if r["user_email"])

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "user": user,
            "rows": rows,
            "users_count": users_count,
            "inquiries_count": inquiries_count,
            "registered_count": registered_count,
            "guest_count": inquiries_count - registered_count,
        }
    )

@app.post("/submit-order")
async def create_order(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    service_text: str = Form(""),
    db: Session = Depends(get_db)
):
    token = request.cookies.get("access_token")
    user = await get_current_user(token, db)
    user_id = user.id if user else None

    try:
        translated_text = GoogleTranslator(source='auto', target='uk').translate(service_text) if service_text else "Немає опису"
    except:
        translated_text = service_text

    new_inquiry = PatientInquiry(name=name, phone=phone, service=translated_text, user_id=user_id)
    db.add(new_inquiry)
    db.commit()
    db.refresh(new_inquiry)
    return {"status": "success", "translated_text": translated_text}

@app.get("/view-data")
async def view_data(db: Session = Depends(get_db)):
    return db.query(PatientInquiry).all()

@app.get("/ping")
async def ping():
    return {"status": "alive"}
