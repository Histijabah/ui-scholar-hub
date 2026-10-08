# UI-ScholarHub

A CSC 476 prototype for a University of Ibadan academic/research outputs repository using web and mobile-ready technology.

## Stack
- Python 3
- Flask
- SQLite
- HTML5/CSS3/JavaScript
- Responsive/PWA-ready interface
- REST-style JSON API

## Core features
- Public search across title, authors, keywords and abstract
- Filters for faculty, department, author, output type and year
- Research-output detail pages
- Open/restricted download handling
- UI-email registration (`@ui.edu.ng`)
- Depositor submission workflow
- Librarian approval/rejection workflow
- My submissions page
- Librarian statistics
- API endpoints for web/mobile clients
- Prototype OAI-PMH-style metadata endpoint
- Password hashing with PBKDF2-HMAC-SHA256

## Run locally
```bash
python -m venv venv
# Windows: venv\\Scripts\\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`.

## Demo librarian account
- Email: `admin@ui.edu.ng`
- Password: `Admin@12345`

Change the demo password before any real deployment.

## API examples
- `GET /api/outputs?q=machine`
- `GET /api/outputs?faculty=Science&year=2025`
- `GET /api/facets`
- `GET /api/outputs/1`
- `POST /api/register`
- `GET /oai?verb=Identify`
- `GET /oai?verb=ListRecords`

## Scope note
This is an academic prototype. Production deployment would need HTTPS, secure secret management, rate limiting, CSRF protection, stronger upload scanning, database hardening, email notifications, formal OAI-PMH implementation, real-device testing and user-acceptance evaluation.
