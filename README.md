# QueryNest v2 — AI-Based Smart FAQ Chatbot for SWE Students
**Group 03 | SE331 Spring 2026 | Rakib · Rashed · Bappy**

---

## All 21 Features Implemented

### Module 01 — Chatbot & Query System
| # | Feature | Status |
|---|---------|--------|
| 1 | Keyword-Based FAQ Chatbot with Confidence Scoring | ✅ |
| 2 | Unmatched Query Detection & Auto-Flagging | ✅ |
| 3 | Chatbot Quick Suggestion Chips (Top 6 most-used) | ✅ |
| 4 | Chatbot Conversation History with Timestamps | ✅ |
| 5 | Per-Response Rating System (Helpful / Not Helpful) | ✅ |
| 6 | Student Feedback & Suggestion Submission | ✅ |
| 7 | FAQ Browse & Category Filter | ✅ |

### Module 02 — Resources & Public Information
| # | Feature | Status |
|---|---------|--------|
| 8  | Programming Resource Library | ✅ |
| 9  | Trending Questions Leaderboard | ✅ |
| 10 | SWE Career Roadmap Page | ✅ |
| 11 | Tech Event & Hackathon Board | ✅ |
| 12 | Study Material Download Center | ✅ |
| 13 | Campus Info Hub (Clubs, Scholarships, Internships) | ✅ |
| 14 | Notice Board with Full Admin CRUD | ✅ |

### Module 03 — Admin Panel & Analytics
| # | Feature | Status |
|---|---------|--------|
| 15 | Admin Analytics Dashboard | ✅ |
| 16 | Unanswered Query Review & FAQ Conversion | ✅ |
| 17 | Admin FAQ Manager (Full CRUD) | ✅ |
| 18 | Admin Chat Log Viewer (filter by student/date) | ✅ |
| 19 | Admin Feedback Manager (Pending/Resolved) | ✅ |
| 20 | Notice Search & Date Filter | ✅ |
| 21 | Student Profile Page (edit info + change password) | ✅ |

---

## Setup & Run

```bash
# 1. Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python app.py
```

Then open: **http://127.0.0.1:5000**

## Default Credentials
- **Admin:** username `admin` / password `admin123`
- **Student:** Register a new account from the Register page

## Project Structure
```
QueryNest/
├── app.py                    # Main Flask application (all 21 features)
├── querynest.db              # SQLite database (auto-created on first run)
├── requirements.txt
├── static/
│   └── uploads/              # Uploaded study materials
└── templates/
    ├── base.html             # Base layout with navbar
    ├── home.html
    ├── login.html
    ├── register.html
    ├── profile.html          # Feature #21
    ├── chatbot.html          # Features #1–5
    ├── feedback.html         # Feature #6
    ├── faq_browse.html       # Feature #7
    ├── resources.html        # Feature #8
    ├── trending.html         # Feature #9
    ├── career.html           # Feature #10
    ├── events.html           # Feature #11
    ├── materials.html        # Feature #12
    ├── campus.html           # Feature #13
    ├── notices.html          # Features #14, #20
    ├── academic.html
    ├── faq_form.html
    ├── notice_form.html
    ├── admin_dashboard.html  # Feature #15
    ├── admin_faqs.html       # Feature #17
    ├── admin_unmatched.html  # Feature #16
    ├── admin_convert.html    # Feature #16
    ├── admin_chatlogs.html   # Feature #18
    ├── admin_feedback.html   # Feature #19
    ├── admin_notices.html    # Feature #14
    ├── admin_materials.html
    └── admin_material_upload.html
```
