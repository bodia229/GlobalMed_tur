# GlobalMed — Medical Tourism Platform

Web platform for a medical tourism agency connecting patients from Prague with certified clinics in Turkey. Built with FastAPI and Jinja2.

---

## Features

- **6 service categories** with tabbed UI — Dental, Aesthetics, Hair Transplant, Eye Surgery, Bariatric Surgery, IVF
- **JWT authentication** — login, registration, secure httponly cookies
- **Patient dashboard** — view submitted inquiries
- **Admin panel** — manage all users and inquiries
- **Reviews system** — verified reviews from registered users
- **Gallery** — photo gallery with lightbox
- **Contacts page** — embedded Google Maps, WhatsApp link
- **Privacy policy** page in Ukrainian
- **Auto-translation** via Google Translate widget
- **Hourly DB backups** — saved automatically to `/backups`
- Fully responsive, mobile-friendly

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI 0.136 + Uvicorn |
| Templates | Jinja2 |
| Database | SQLite + SQLAlchemy 2.0 |
| Auth | python-jose (JWT) + bcrypt |
| Translation | deep-translator (Google) |
| Static files | FastAPI StaticFiles + aiofiles |

---

## Project Structure

```
my_project/
├── main.py              # FastAPI app, routes, models
├── sql_app.db           # SQLite database
├── templates/           # Jinja2 HTML templates
│   ├── index.html
│   ├── about_us.html
│   ├── contacts.html
│   ├── gallery.html
│   ├── reviews.html
│   ├── privacy.html
│   ├── register.html
│   ├── dashboard.html
│   └── admin.html
├── static/
│   └── images/          # Local images
├── backups/             # Hourly DB backups
└── venv/                # Python virtual environment
```

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/your-username/my_project.git
cd my_project
```

### 2. Create and activate virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install fastapi uvicorn sqlalchemy python-jose bcrypt deep-translator python-multipart aiofiles jinja2
```

### 4. Run the server

```bash
uvicorn main:app --reload
```

Open [http://localhost:8000](http://localhost:8000)

---

## Default Admin Accounts

| Email | Password |
|---|---|
| info.globalmed.clinic@gmail.com | Globalqwer |
| bogdan.bondarenk0.2020@gmail.com | Globalqwer |

> Admin accounts are created automatically on first startup.

---

## Routes

| Route | Description |
|---|---|
| `GET /` | Home page |
| `GET /about_us` | About page |
| `GET /contacts` | Contacts + map |
| `GET /gallery` | Photo gallery |
| `GET /reviews` | Patient reviews |
| `POST /reviews/submit` | Submit a review (auth required) |
| `GET /privacy` | Privacy policy |
| `GET /dashboard` | Patient dashboard |
| `GET /admin` | Admin panel |
| `POST /login` | Login |
| `POST /register` | Register |
| `GET /logout` | Logout |
| `POST /submit-order` | Submit inquiry |
