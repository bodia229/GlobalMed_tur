import os
import re
import shutil
import asyncio
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import FastAPI, Request, Form, Depends, Cookie, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
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
_DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{_DB_PATH}")
# Render повертає postgres://, SQLAlchemy потребує postgresql://
if _DATABASE_URL.startswith("postgres://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql://", 1)
_is_sqlite = _DATABASE_URL.startswith("sqlite")
engine = create_engine(
    _DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {}
)
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

class BlogPost(Base):
    __tablename__ = "blog_posts"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    slug = Column(String, unique=True, index=True)
    excerpt = Column(String)
    content = Column(String)
    image_url = Column(String, default="")
    author = Column(String, default="GlobalMed")
    created_at = Column(String)

class NewsletterSubscriber(Base):
    __tablename__ = "newsletter"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    subscribed_at = Column(String)

Base.metadata.create_all(bind=engine)

# --- ИНИЦИАЛИЗАЦИЯ ---
limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.mount("/static", StaticFiles(directory=os.path.join(_BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return templates.TemplateResponse(
        request=request,
        name="404.html",
        context={"page_title": "Сторінку не знайдено — GlobalMed"},
        status_code=404
    )

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

def _make_slug(title: str, db) -> str:
    slug_base = re.sub(r"[^a-zA-Zа-яА-ЯіїєёЄІЇ0-9]+", "-", title.lower()).strip("-")
    slug, counter = slug_base, 1
    while db.query(BlogPost).filter(BlogPost.slug == slug).first():
        slug = f"{slug_base}-{counter}"; counter += 1
    return slug

def seed_blog_posts():
    db = SessionLocal()
    try:
        if db.query(BlogPost).first():
            return
        today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
        articles = [
            {
                "title": "Операція Femto LASIK: як виконується та кому підходить?",
                "excerpt": "Femto LASIK — передовий метод корекції зору за допомогою фемтосекундного лазера. Дізнайтеся, як проходить процедура та хто є ідеальним кандидатом.",
                "content": """<p>Femto LASIK — це передовий метод корекції зору, який використовує технологію фемтосекундного лазера для зміни форми рогівки. На відміну від традиційного LASIK, ця процедура виконується повністю без лез — сучасні лазерні системи формують клапоть рогівки з точністю до мікрометра.</p>

<h2>Які порушення зору виправляє Femto LASIK?</h2>
<p>Процедура усуває три основних порушення рефракції:</p>
<ul>
  <li>Короткозорість (міопія)</li>
  <li>Далекозорість (гіперметропія)</li>
  <li>Астигматизм</li>
</ul>

<h2>Як проходить операція?</h2>
<p>Операція складається з кількох послідовних етапів:</p>
<ol>
  <li>Комплексне обстеження очей</li>
  <li>Застосування місцевої анестезії</li>
  <li>Формування клаптя фемтосекундним лазером</li>
  <li>Корекція форми рогівки ексимерним лазером</li>
  <li>Репозиція клаптя</li>
</ol>
<p>Весь процес зазвичай займає <strong>10–15 хвилин для обох очей</strong>.</p>

<h2>Відновлення після операції</h2>
<p>Більшість пацієнтів відчувають швидке покращення зору, а його стабілізація відбувається протягом короткого часу. Повернення до офісної роботи, як правило, можливе вже через 1–2 дні, хоча деякі види діяльності тимчасово обмежені.</p>

<h2>Кому підходить Femto LASIK?</h2>
<p>Підходящими кандидатами зазвичай є особи, які відповідають таким критеріям:</p>
<ul>
  <li>Вік понад 18 років</li>
  <li>Стабільний зір протягом щонайменше одного року</li>
  <li>Достатня товщина рогівки</li>
  <li>Відсутність серйозних захворювань очей</li>
</ul>
<blockquote>Процедура протипоказана вагітним жінкам та особам із певними офтальмологічними патологіями.</blockquote>

<h2>Безпечність процедури</h2>
<p>За умови виконання досвідченими офтальмологами з використанням сучасних технологій Femto LASIK є надзвичайно безпечним методом — точний лазерний контроль суттєво знижує ризик ускладнень.</p>""",
                "author": "GlobalMed",
                "image_url": "https://www.ru.renewalmedicalclinic.com/wp-content/uploads/2026/02/10-1024x683.jpg",
            },
            {
                "title": "Що таке операція Smart Lens? Кому вона підходить?",
                "excerpt": "Smart Lens — сучасна офтальмологічна процедура заміни кришталика трифокальним імплантом для чіткого зору без окулярів на будь-якій відстані.",
                "content": """<p>Smart Lens — це сучасна офтальмологічна процедура, під час якої природний кришталик ока хірургічно видаляється та замінюється <strong>трифокальним інтраокулярним імплантом</strong>. Ця технологія дозволяє пацієнтам бачити чітко на різних відстанях — поблизу, на середній та далекій дистанції — без залежності від окулярів.</p>

<h2>Як працює Smart Lens?</h2>
<p>Імплант розподіляє вхідне світло на три фокусні зони, кожна з яких відповідає за певний діапазон відстаней. Це імітує фокусувальну здатність, якою природно наділені молоді здорові очі, але яка поступово втрачається з роками.</p>

<h2>Які проблеми вирішує процедура?</h2>
<p>За одну операцію усуваються кілька рефракційних порушень:</p>
<ul>
  <li>Пресбіопія (вікове погіршення зору зблизька)</li>
  <li>Катаракта</li>
  <li>Короткозорість</li>
  <li>Далекозорість</li>
  <li>Астигматизм</li>
</ul>

<h2>Кому підходить Smart Lens?</h2>
<p>Підходящі кандидати, як правило, відповідають таким критеріям:</p>
<ul>
  <li>Вік понад 40 років</li>
  <li>Труднощі через пресбіопію або катаракту</li>
  <li>Бажання знизити залежність від окулярів</li>
  <li>Відповідний стан рогівки й очей загалом</li>
</ul>

<h2>Як проходить операція?</h2>
<p>Мінімально інвазивна процедура займає близько <strong>10–15 хвилин на кожне око</strong> під місцевою анестезією. Більшість пацієнтів відчувають покращення зору вже через кілька днів, а повна адаптація займає кілька тижнів.</p>
<blockquote>Штучний кришталик зберігається протягом усього життя, забезпечуючи постійну корекцію зору.</blockquote>""",
                "author": "GlobalMed",
                "image_url": "https://www.ru.renewalmedicalclinic.com/wp-content/uploads/2026/02/9-1024x683.jpg",
            },
            {
                "title": "Видалення ретинованого зуба: що це таке і як проходить операція?",
                "excerpt": "Ретинований зуб — серйозна стоматологічна проблема. Розповідаємо, чому важливо не відкладати видалення та як виглядає сам хірургічний процес.",
                "content": """<p>Ретинований зуб — це зуб, який не може прорізатися у своє нормальне функціональне положення через недостатній простір у щелепі, неправильний кут прорізування, щільну кісткову тканину або генетичні фактори.</p>

<h2>Типи ретенції</h2>
<ul>
  <li><strong>Повна ретенція</strong> — зуб повністю знаходиться в кістці</li>
  <li><strong>Часткова ретенція</strong> — зуб частково прорізався</li>
  <li><strong>М\'якотканинна або кісткова ретенція</strong></li>
</ul>

<h2>Чому важливо не зволікати з лікуванням?</h2>
<p>Якщо не вжити заходів, ретиновані зуби можуть спричинити:</p>
<ul>
  <li>Хронічний біль</li>
  <li>Рецидивні інфекції (перикоронарит)</li>
  <li>Пошкодження сусідніх зубів</li>
  <li>Утворення кіст</li>
  <li>Захворювання ясен і скутість щелепи</li>
</ul>
<blockquote>Клініка рекомендує видалення навіть до появи симптомів, якщо рентгенологічні дані вказують на ризик ускладнень у майбутньому.</blockquote>

<h2>Як проходить операція?</h2>
<ol>
  <li>Передопераційна візуалізація (панорамний рентген або 3D КТ)</li>
  <li>Місцева анестезія</li>
  <li>Розріз ясен</li>
  <li>Обережне видалення кісткової тканини</li>
  <li>Екстракція зуба (іноді частинами)</li>
  <li>Накладання швів</li>
</ol>

<h2>Відновлення після операції</h2>
<p>Нормальні постопераційні симптоми включають незначний набряк, тимчасовий дискомфорт і синці тривалістю кілька днів. Рекомендується:</p>
<ul>
  <li>Прикладати холодні компреси</li>
  <li>Приймати призначені ліки</li>
  <li>Уникати куріння</li>
  <li>Вживати м\'яку їжу</li>
  <li>Ретельно дотримуватися гігієни порожнини рота</li>
</ul>""",
                "author": "GlobalMed",
                "image_url": "https://www.ru.renewalmedicalclinic.com/wp-content/uploads/2026/02/8-1024x683.jpg",
            },
            {
                "title": "Типи зубних коронок: яка коронка підходить саме вам?",
                "excerpt": "Металокерамічна, цирконієва, E-max чи металева? Розбираємося, які бувають зубні коронки та як обрати оптимальний варіант для кожного випадку.",
                "content": """<p>Зубна коронка — це незнімна реставрація, яка повністю покриває пошкоджений або ослаблений зуб. Мета процедури — відновити форму, розмір і міцність зуба, виконуючи як терапевтичну, так і естетичну функцію.</p>

<h2>Коли потрібна коронка?</h2>
<ul>
  <li>Значна втрата зубної тканини</li>
  <li>Зуб після лікування кореневих каналів</li>
  <li>Зламаний або тріснутий зуб</li>
  <li>Глибокий карієс</li>
  <li>Естетичні проблеми</li>
  <li>Відновлення на імплантах</li>
</ul>

<h2>Основні типи зубних коронок</h2>

<h3>Металокерамічна коронка</h3>
<p>Металева основа з керамічним покриттям. Відрізняється <strong>високою міцністю</strong>, але обмеженою світлопроникністю. Найкраще підходить для жувальних зубів, де естетика менш критична.</p>

<h3>Цирконієва коронка</h3>
<p>Сучасний <strong>металовільний варіант</strong> з відмінною світлопроникністю та природним виглядом. Підходить як для передніх, так і для жувальних зубів.</p>

<h3>Цільнокерамічна коронка (E-max)</h3>
<p>Чудова естетика з <strong>високою прозорістю</strong>. Ідеальна для дизайну посмішки та реставрації фронтальних зубів.</p>

<h3>Металева коронка</h3>
<p>Суцільна металева конструкція максимальної міцності з обмеженою естетикою. Застосовується для прихованих задніх ділянок.</p>

<h2>Як відбувається процес виготовлення?</h2>
<ol>
  <li>Клінічне обстеження</li>
  <li>Препарування зуба</li>
  <li>Встановлення тимчасової коронки</li>
  <li>Лабораторне виготовлення (CAD/CAM технології)</li>
  <li>Остаточна фіксація</li>
</ol>
<blockquote>Вибір коронки залежить від положення зуба, жувального навантаження, естетичних вимог та загального стану порожнини рота.</blockquote>""",
                "author": "GlobalMed",
                "image_url": "https://www.ru.renewalmedicalclinic.com/wp-content/uploads/2026/01/7-1024x683.jpg",
            },
            {
                "title": "Лазерне лікування ясен: як проводиться і який термін відновлення?",
                "excerpt": "Лазерне лікування ясен — сучасна альтернатива традиційній хірургії з мінімальним болем і коротким відновленням. Дізнайтеся про показання та переваги.",
                "content": """<p>Лазерне лікування ясен — це процедура, під час якої ясенна тканина точно розрізається, очищається або моделюється за допомогою спеціальних стоматологічних лазерів. Сучасні лазерні системи дозволяють надточно обробляти тканини з <strong>мінімальною кровотечею</strong> та без пошкодження оточуючих структур.</p>

<h2>Показання до лазерного лікування ясен</h2>
<ul>
  <li>Запалення ясен (гінгівіт, пародонтит)</li>
  <li>Рецесія ясен</li>
  <li>Утворення пародонтальних кишень</li>
  <li>Корекція «ясенної посмішки» (gummy smile)</li>
  <li>Пігментація ясен</li>
</ul>

<h2>Як проходить процедура?</h2>
<ol>
  <li>Клінічне обстеження та діагностика</li>
  <li>Місцева анестезія</li>
  <li>Лазерна обробка — очищення або корекція форми ясен</li>
  <li>Постпроцедурне спостереження та рекомендації щодо догляду</li>
</ol>

<h2>Переваги лазерного лікування</h2>
<ul>
  <li>Мінімальна кровотеча під час процедури</li>
  <li>Як правило, не потрібні шви</li>
  <li>Швидше загоєння порівняно з традиційною хірургією</li>
  <li>Знижений ризик інфекцій</li>
  <li>Менший постопераційний біль і набряк</li>
</ul>

<h2>Відновлення після лазерного лікування</h2>
<p>Більшість пацієнтів відчувають зменшення чутливості вже через <strong>24–48 годин</strong> і можуть швидко повернутися до звичного ритму життя. Відновлення тканин починається через кілька днів, а повне загоєння настає впродовж <strong>1–2 тижнів</strong>.</p>
<blockquote>За умови проведення досвідченими стоматологами з використанням сучасного обладнання процедура є абсолютно безпечною та ефективною.</blockquote>""",
                "author": "GlobalMed",
                "image_url": "https://www.ru.renewalmedicalclinic.com/wp-content/uploads/2026/01/6-1024x683.jpg",
            },
            {
                "title": "Синусліфтинг: що це таке і коли він необхідний?",
                "excerpt": "Синусліфтинг — хірургічна операція для нарощування кісткової тканини перед імплантацією. Розповідаємо про показання, методи та терміни відновлення.",
                "content": """<p>Синусліфтинг — це операція, під час якої підіймається дно верхньощелепної пазухи та в утворений простір укладається кісткова маса для відновлення достатнього об\'єму кістки <strong>перед встановленням зубних імплантів</strong>.</p>

<h2>Коли необхідний синусліфтинг?</h2>
<ul>
  <li>Недостатня висота кістки у ділянці бічних зубів верхньої щелепи</li>
  <li>Близьке розташування гайморових пазух до місця майбутніх імплантів</li>
  <li>Необхідність одночасної кісткової пластики та імплантації</li>
  <li>Потреба у надійній кістковій основі для незнімних протезів</li>
</ul>

<h2>Причини нестачі кісткової тканини</h2>
<p>Дефіцит кістки може виникати внаслідок:</p>
<ul>
  <li>Тривалої відсутності зубів</li>
  <li>Резорбції кістки після видалення</li>
  <li>Вродженої недостатньої висоти кістки</li>
  <li>Анатомічно великих гайморових пазух</li>
</ul>

<h2>Два методи операції</h2>
<h3>Закрита техніка</h3>
<p>Підходить при незначній нестачі кістки. Виконується <strong>одночасно з встановленням імплантів</strong> — більш щадний варіант з коротшим терміном відновлення.</p>

<h3>Відкрита (латеральна) техніка</h3>
<p>Застосовується при значному дефіциті кістки. Формується хірургічне «вікно» у стінці пазухи. <strong>Імпланти встановлюються після формування нової кістки</strong> — через кілька місяців.</p>

<h2>Відновлення після операції</h2>
<p>Після синусліфтингу пацієнти зазвичай відчувають незначний набряк і відчуття закладеності носа протягом кількох днів. Процес дозрівання кістки займає <strong>кілька місяців</strong>, після чого можна безпечно встановлювати імпланти.</p>
<blockquote>За умови виконання досвідченими фахівцями та правильного відбору пацієнтів процедура демонструє високий відсоток успіху й значно підвищує стабільність імплантів.</blockquote>""",
                "author": "GlobalMed",
                "image_url": "https://www.ru.renewalmedicalclinic.com/wp-content/uploads/2026/01/5-1024x683.jpg",
            },
        ]
        for art in articles:
            slug = _make_slug(art["title"], db)
            db.add(BlogPost(
                title=art["title"], slug=slug, excerpt=art["excerpt"],
                content=art["content"], image_url=art["image_url"],
                author=art["author"], created_at=today
            ))
        db.commit()
    finally:
        db.close()

seed_blog_posts()

def update_blog_images():
    image_map = [
        ("Femto LASIK",  "https://www.ru.renewalmedicalclinic.com/wp-content/uploads/2026/02/10-1024x683.jpg"),
        ("Smart Lens",   "https://www.ru.renewalmedicalclinic.com/wp-content/uploads/2026/02/9-1024x683.jpg"),
        ("ретинованого", "https://www.ru.renewalmedicalclinic.com/wp-content/uploads/2026/02/8-1024x683.jpg"),
        ("коронок",      "https://www.ru.renewalmedicalclinic.com/wp-content/uploads/2026/01/7-1024x683.jpg"),
        ("ясен",         "https://www.ru.renewalmedicalclinic.com/wp-content/uploads/2026/01/6-1024x683.jpg"),
        ("Синусліфтинг", "https://www.ru.renewalmedicalclinic.com/wp-content/uploads/2026/01/5-1024x683.jpg"),
    ]
    db = SessionLocal()
    try:
        for keyword, url in image_map:
            post = db.query(BlogPost).filter(
                BlogPost.title.contains(keyword),
                BlogPost.image_url == ""
            ).first()
            if post:
                post.image_url = url
        db.commit()
    finally:
        db.close()

update_blog_images()

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
@limiter.limit("5/minute")
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
    review = Review(
        user_id=user.id,
        author_name=author_name,
        text=text,
        rating=max(1, min(5, rating)),
        created_at=datetime.now(timezone.utc).strftime("%d.%m.%Y")
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
@limiter.limit("5/minute")
async def register(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user_exists = db.query(User).filter(User.email == email).first()
    if user_exists:
        return {"error": "Email вже зареєстрований"}
    new_user = User(email=email, password_hash=get_password_hash(password))
    db.add(new_user)
    db.commit()
    return {"message": "Акаунт створено!"}

@app.get("/login")
async def login_redirect():
    return RedirectResponse(url="/", status_code=302)

@app.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, response: Response, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
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

    subscribers = db.query(NewsletterSubscriber).order_by(NewsletterSubscriber.id.desc()).all()
    blog_posts = db.query(BlogPost).order_by(BlogPost.id.desc()).all()
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
            "subscribers": subscribers,
            "blog_posts": blog_posts,
        }
    )

@app.post("/admin/delete-inquiries")
async def delete_inquiries(
    request: Request,
    ids: str = Form(...),
    db: Session = Depends(get_db)
):
    token = request.cookies.get("access_token")
    user = await get_current_user(token, db)
    if not user or user.email not in ADMIN_EMAILS:
        return RedirectResponse(url="/", status_code=302)
    id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
    if id_list:
        db.query(PatientInquiry).filter(PatientInquiry.id.in_(id_list)).delete(synchronize_session=False)
        db.commit()
    return RedirectResponse(url="/admin", status_code=302)

@app.post("/submit-order")
@limiter.limit("10/minute")
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

@app.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request, db: Session = Depends(get_db)):
    posts = db.query(BlogPost).order_by(BlogPost.id.desc()).all()
    return templates.TemplateResponse(request=request, name="blog.html",
        context={"page_title": "Блог — GlobalMed", "posts": posts})

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_post(slug: str, request: Request, db: Session = Depends(get_db)):
    post = db.query(BlogPost).filter(BlogPost.slug == slug).first()
    if not post:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request=request, name="blog_post.html",
        context={"page_title": f"{post.title} — GlobalMed", "post": post})

@app.post("/admin/blog/create")
async def blog_create(
    request: Request,
    title: str = Form(...),
    excerpt: str = Form(...),
    content: str = Form(...),
    image_url: str = Form(""),
    author: str = Form("GlobalMed"),
    db: Session = Depends(get_db)
):
    token = request.cookies.get("access_token")
    user = await get_current_user(token, db)
    if not user or user.email not in ADMIN_EMAILS:
        return RedirectResponse(url="/", status_code=302)
    slug = _make_slug(title, db)
    post = BlogPost(title=title, slug=slug, excerpt=excerpt, content=content,
                    image_url=image_url, author=author,
                    created_at=datetime.now(timezone.utc).strftime("%d.%m.%Y"))
    db.add(post); db.commit()
    return RedirectResponse(url="/admin#blog", status_code=302)

@app.post("/admin/blog/delete")
async def blog_delete(request: Request, post_id: int = Form(...), db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    user = await get_current_user(token, db)
    if not user or user.email not in ADMIN_EMAILS:
        return RedirectResponse(url="/", status_code=302)
    db.query(BlogPost).filter(BlogPost.id == post_id).delete()
    db.commit()
    return RedirectResponse(url="/admin#blog", status_code=302)

@app.get("/admin/blog/edit/{post_id}", response_class=HTMLResponse)
async def blog_edit_page(post_id: int, request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    user = await get_current_user(token, db)
    if not user or user.email not in ADMIN_EMAILS:
        return RedirectResponse(url="/", status_code=302)
    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request=request, name="blog_edit.html",
        context={"user": user, "post": post})

@app.post("/admin/blog/update")
async def blog_update(
    request: Request,
    post_id: int = Form(...),
    title: str = Form(...),
    excerpt: str = Form(""),
    content: str = Form(...),
    image_url: str = Form(""),
    author: str = Form("GlobalMed"),
    db: Session = Depends(get_db)
):
    token = request.cookies.get("access_token")
    user = await get_current_user(token, db)
    if not user or user.email not in ADMIN_EMAILS:
        return RedirectResponse(url="/", status_code=302)
    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if post:
        post.title = title
        post.excerpt = excerpt
        post.content = content
        post.image_url = image_url
        post.author = author
        db.commit()
    return RedirectResponse(url="/admin#blog", status_code=302)

@app.post("/subscribe")
@limiter.limit("5/minute")
async def subscribe(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    existing = db.query(NewsletterSubscriber).filter(NewsletterSubscriber.email == email).first()
    if existing:
        return {"status": "already", "message": "Ви вже підписані на новини!"}
    subscriber = NewsletterSubscriber(
        email=email,
        subscribed_at=datetime.now(timezone.utc).strftime("%d.%m.%Y")
    )
    db.add(subscriber)
    db.commit()
    return {"status": "success", "message": "Дякуємо! Ви успішно підписались на новини."}

@app.get("/ping")
async def ping():
    return {"status": "alive"}
