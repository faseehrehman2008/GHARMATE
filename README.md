# GHARMATE

Family management web application built with Flask and SQLite/PostgreSQL (Supabase-compatible).

## Features
- Family accounts and admin/member roles
- Daily timetable, chores, calendar, prayer times and announcements
- Smart chore rotation (admin creates and advances rotations)
- Family polls and one vote per member
- Leave & outing tracker
- Emergency contact center
- Birthday, anniversary and event manager
- Visitor register with arrival/departure log
- Built-in family assistant (rule-based; no external AI API required)

## Local setup
1. Install Python 3.10 or newer.
2. Run `py -m venv .venv` and activate it.
3. Run `pip install -r requirements.txt`.
4. Create an admin account with `py create_admin.py`.
5. Start with `py app.py` and open http://127.0.0.1:5000.

## Supabase / hosting
Set `DATABASE_URL` to the PostgreSQL connection string and set `GHARMATE_SECRET` to a long random secret. The app creates the new feature tables and adds the event type/person columns during startup. Back up your existing database before deploying migrations.

## Notes
- The assistant is rule-based in this version, not a generative AI model.
- Prayer times are entered manually; push notifications are not included.
- Use HTTPS in production. Add CSRF protection and review account permissions before public production use.
