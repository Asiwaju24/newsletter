# Dispatch — newsletter platform (Django)

Write issues in Markdown, collect **confirmed** subscribers (double opt-in), and send or schedule
issues with per-recipient tracking and one-click unsubscribe.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set DJANGO_SECRET_KEY, keep DJANGO_DEBUG=True for development
python manage.py migrate
python manage.py createsuperuser  # optional, for /admin/
python manage.py runserver
python manage.py test           # 72 tests
python manage.py seed_data      # demo users, newsletters, subscribers and issues
```

In development, emails print to the console, so you can copy confirmation links from the terminal.

**Upgrading your existing `db.sqlite3`?** Put it in this folder and run `python manage.py migrate`.
Existing users are kept. Old newsletters get slugs, and old subscribers become confirmed subscriptions.

## Demo data

`python manage.py seed_data` creates two creators (`demo` and `other`, password `demo-pass-1234`) and five newsletters:
public, unlisted, closed to new subscribers, and one belonging to the second user to check data isolation.
Each has 40 subscribers (confirmed, pending and unsubscribed) and issues in every state, including two failed
deliveries to retry and one issue already due, so `python manage.py send_queued_issues` has something to send.
Use `--reset` to recreate it, `--subscribers N` to change the list size. It refuses to run when `DEBUG` is off.

## How it works

| Piece | Where |
|---|---|
| Models: `Newsletter`, `Subscription` (pending / confirmed / unsubscribed), `Issue` (draft / scheduled / sending / sent), `Delivery` | `newsletters/models.py` |
| Subscribe, confirm, compose, send, retry | `newsletters/services.py` |
| Public pages: `/`, `/discover/`, `/n/<slug>/`, issue archive | `newsletters/views/public.py` |
| Creator dashboard: `/dashboard/` | `newsletters/views/dashboard.py` |
| Sign up, login, password reset and change | `accounts/` |
| Queue worker | `manage.py send_queued_issues [--loop]` |

Every dashboard query is scoped to `request.user`, so other people's data returns 404.

## Sending in production

Set `NEWSLETTER_SEND_INLINE=False`. "Send now" and scheduled issues are then picked up by a worker:

```bash
python manage.py send_queued_issues --loop --interval 60
```

Run it as a background worker, or call `python manage.py send_queued_issues` from cron every minute.
Sending is idempotent: a crashed run resumes, nobody gets a duplicate, and failed deliveries can be
retried from the issue page.

## Deploying

```bash
pip install -r requirements.txt
python manage.py collectstatic --noinput && python manage.py migrate
gunicorn wizard_site.wsgi
```

Required environment variables: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `SITE_URL`,
`DATABASE_URL` (Postgres recommended), SMTP settings (`EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`),
and `DEFAULT_FROM_EMAIL` on a domain you've verified with SPF and DKIM. Behind a proxy such as Render, also set
`DJANGO_BEHIND_PROXY=True`. See `.env.example` for everything else.

## Known limits

- Emails are sent from the platform address, with the newsletter name as the display name and the owner as reply-to.
- No open or click tracking (privacy-friendly by default).
- Large lists (many thousands) should use a transactional provider such as SES, Postmark or Resend through SMTP.
