# ParkSense

ParkSense is a Flask/Jinja parking operations application for organizations. It
tracks vehicles, allocates compatible nearby bays, checks vehicles in and out,
quotes and settles configurable parking charges, accepts reservations, and
summarizes occupancy and parking history. The first release uses a simulated
advance-payment confirmation; it does not connect to a payment provider.

## Application architecture

The web layer is organized by role and responsibility while keeping Flask
blueprints, Jinja templates, and the existing public URLs:

```text
app/
├── __init__.py              # app factory, extensions, CLI commands
├── models.py                # users, employees, vehicles, bays, visits
├── services/parking.py      # allocation, reservations, policy, analytics
├── api/                     # JWT authenticated REST endpoints
├── routes/
│   ├── public.py            # landing page and role-aware dashboard entry
│   ├── customer.py          # customer vehicles, reservations, visit history
│   ├── admin.py             # facility operations and reporting
│   ├── common.py            # role authorization guards
│   ├── user_login.py        # customer sign-in module
│   ├── admin_login.py       # administrator sign-in module
│   ├── login_support.py     # shared credential and safe redirect helpers
│   ├── auth.py              # registration and session lifecycle
│   └── main.py              # assembles the main web blueprint
├── templates/               # role-specific screens with shared layout
└── static/                  # CSS and browser behavior
```

User registration always creates a customer account. Administrators are
provisioned through the `create-admin` command. The server-side route guards
enforce these roles independently of which navigation links are visible.

## Requirements

- Python 3.10+
- SQLite for local development (included with Python)
- MySQL 8+ is optional for shared/deployed environments

## Local setup

1. Create and activate a virtual environment, then install dependencies:

   ```powershell
   py -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Create your local environment file. The checked-in example defaults to
   SQLite, so no database server or credentials are required:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Apply schema migrations and add the documented 400 bays:

   ```powershell
   python -m flask --app run.py db upgrade
   python -m flask --app run.py seed-parking
   ```

   The seed command creates 200 2-wheeler bays, 50 3-wheeler bays, and 150
   4-wheeler bays. It is safe to run again and does not overwrite existing bays.

4. Provision an administrator from the command line. The password is entered
   interactively and is not part of shell history:

   ```powershell
   python -m flask --app run.py create-admin
   ```

   To reset an existing administrator's password without exposing it in shell
   history, run `python -m flask --app run.py set-admin-password USERNAME`.
   This promotes that existing account to administrator and stores only a
   Werkzeug password hash.

5. Start the web application:

   ```powershell
   python -m flask --app run.py run --debug
   ```

6. Open `http://127.0.0.1:5000`. The landing page keeps **User login** and
   **Administrator login** separate. Drivers can create customer accounts;
   administrator accounts can only be provisioned with the CLI. Existing
   accounts are migrated as administrators to preserve their operations access.

The SQLite database is stored at `instance/parksense.db` and is created by
Flask-SQLAlchemy. The app defaults to this SQLite database when neither
`DATABASE_URL` nor `MYSQL_HOST` is configured. For MySQL, remove `DATABASE_URL`
from `.env`, set the `MYSQL_*` values from `.env.example`, and create/grant the
database account before applying migrations. When Flask runs directly on
Windows, use `MYSQL_HOST=localhost`; `host.docker.internal` is for a Flask
container connecting to MySQL on the Windows host. A supplied `DATABASE_URL`
takes precedence over MySQL settings. Change both development secrets before
deploying. Tests use an isolated in-memory SQLite database.

## Exact parking workflow

1. **Administrator responsibilities:** sign in through Administrator login
   to register and activate/deactivate employees, manage bay inventory and
   maintenance, check vehicles in and out, handle reservations, and review
   facility analytics and visit reports. Employee records are managed from
   **Employees**; bay status is managed from **Parking bays**. The global
   employee exemption percentage is configurable; an employee-level percentage
   overrides it.
2. **Customer vehicle registration:** create a user account and register
   vehicles from **My parking**. Each customer sees and manages only vehicles
   assigned to their account.
3. **Vehicle classification:** the administrator normalizes and saves its
   registration number, chooses `2-WHEELER`, `3-WHEELER`, or `4-WHEELER`, and
   may attach a verified, active employee ID when registering a vehicle.
4. **Vehicle entry:** submit a registered number at the administrator dashboard or call
   `POST /api/entry`. ParkSense rejects duplicate active visits and selects the
   closest available bay for that vehicle type. Bays under maintenance, blocked,
   occupied, or protected by a reservation are not candidates. The bay is
   marked `OCCUPIED` and an active session records its entry time.
5. **Reservation (optional):** choose one of your own vehicles and a future start/end time. The
   application finds a compatible bay and checks the requested interval against
   other pending and confirmed reservations. It shows the estimated fare and
   records the reservation as `PENDING_PAYMENT`.
6. **Advance payment:** use **Record demo payment** on the account page or administrator dashboard or
   `POST /api/reservations/{id}/confirm-payment`. This explicitly simulates
   payment and changes the reservation to `CONFIRMED`; no actual payment is
   processed. A vehicle can check in against that reservation only after payment
   confirmation and during the reserved time window.
7. **Vehicle exit:** an administrator checks out by registration number or calls `POST /api/exit`.
   Duration is rounded up to the next billable hour (with a one-hour minimum).
   The configured vehicle rate is discounted for employee eligibility and
   completed-visit loyalty, then tax is applied to the remaining amount. The
   session, fare breakdown, and exit time are saved, and the bay is released.
   Reservations show the advance payment and final fare, making any overstay
   balance apparent; a payment/refund processor is intentionally not included.
8. **Operations and analytics:** review current occupancy, vehicle-type
   distribution, active sessions, revenue, average visit length, reservation
   demand for the upcoming week, per-bay 30-day utilization, peak entry
   hours/days, frequent vehicles, and historical fare breakdowns on the
   dashboard and visit-history page. The live bay map displays status and
   utilization. Filter visit history by vehicle, status, and entry date, then
   export matching records as CSV. Manage bay type, distance, and out-of-service
   status under **Parking bays**.

## Pricing and parking policy

Default hourly rates are 20, 30, and 50 currency units for 2-, 3-, and
4-wheelers respectively; the default tax is 18%. Employee exemption defaults
to 100%. Completed visits receive the highest configured loyalty tier at 10, 25,
and 50 visits (5%, 10%, and 15%). These values are configuration defaults in
`app/config.py` and may be overridden by an application config or environment-
specific config subclass. The server calculates and stores amounts to two
decimal places. Employee discount is applied first, loyalty discount to the
remaining base fare, and tax to the post-discount fare.

Reservation form times use the organization/browser local timezone configured
by `PARKING_TIMEZONE` (an IANA name such as `Asia/Kolkata`); stored timestamps
are UTC. Offset-aware API timestamps are converted to UTC, while naive API
timestamps are interpreted in the configured organization timezone. Session
timestamps in API responses include the `Z` UTC suffix.

## REST API

All management API endpoints require an administrator JWT bearer token. Obtain
one using:

```bash
curl -X POST http://127.0.0.1:5000/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"operator","password":"your-password"}'
```

Then send `Authorization: Bearer <access_token>`. Tokens expire after one hour
by default. The signed-in browser spot manager obtains a short-lived token
through `POST /api/auth/session-token`; that endpoint does not accept anonymous
requests. The interactive spot CRUD API documentation is at `/api/docs`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/token` | Exchange operator credentials for a JWT |
| `POST`, `GET` | `/api/vehicles` | Register vehicles; list the registry |
| `POST` | `/api/employees` | Register an employee and exemption policy |
| `POST` | `/api/entry` | Start a visit and allocate a compatible bay |
| `POST` | `/api/exit` | Complete a visit and calculate its fare |
| `GET`, `POST` | `/api/reservations` | List reservations or reserve a time window |
| `POST` | `/api/reservations/{id}/confirm-payment` | Record demo advance payment |
| `POST` | `/api/reservations/{id}/cancel` | Cancel a pending or confirmed reservation |
| `GET` | `/api/history` | Read up to 500 recent parking sessions |
| `GET` | `/api/analytics` | Read occupancy and history analytics |
| `GET`, `POST` | `/api/spots` | List bays or create a bay |
| `GET`, `PUT`, `DELETE` | `/api/spots/{id}` | Read, update, or delete an unused bay |
| `PATCH` | `/api/spots/{id}/status` | Set an available bay to available, maintenance, or blocked |

Example vehicle-entry request:

```bash
curl -X POST http://127.0.0.1:5000/api/entry \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"vehicle_number":"AB12CD3456"}'
```

## Checkpoints covered

- **Foundation:** Flask application factory, MySQL/SQLite configuration,
  migrations, session login, registration, and JWT API authentication.
- **Parking inventory:** 400-capacity seed, compatible vehicle classes, nearest-
  bay assignment, and available/occupied/reserved/maintenance/blocked status.
- **Vehicle lifecycle:** employee and vehicle registration, duplicate-entry
  prevention, active session creation, exit/fare calculation, and bay release.
- **Reservations and policy:** overlap checks, future time windows, advance-
  payment state, configurable employee exemptions and loyalty discounts.
- **Operations reporting:** authenticated dashboard, bay management, visit
  history with filters and CSV export, live bay map, occupancy, per-bay
  30-day utilization, upcoming reservation demand, revenue, duration,
  peak-hour/day, and frequent-vehicle summaries.

The initial scope deliberately excludes real payment processing, mobile apps,
IoT, computer vision, blockchain, microservices, and predictive AI. The schema
and service boundaries leave room for later additions without requiring those
systems for the core parking workflow.

## Run tests

```powershell
.\venv\Scripts\python.exe -m pytest
```
