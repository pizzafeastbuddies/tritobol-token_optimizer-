# Tritobol accounts

Accounts are rows in a SQLite database on this installation. There is no Supabase project, no external identity provider, and no email service.

The database file is `tritobol_app/data/tritobol.sqlite` unless `TRITOBOL_DB` points somewhere else. Tests set `TRITOBOL_DB` so they do not write the development database. The file is not served by Flask. It holds the account name, email, and password hash. It does not hold prompt text, uploaded documents, or browser history.

## What an account does

The dashboard, optimizer, results, analytics, history, and settings open after a sign-in. Home, features, about, contact, terms, and the account screens stay available without a session. The privacy page remains at `#/privacy` and is not part of the main navigation.

Registration saves the account and returns to Sign In with: "Your account has been created successfully. Please sign in." The email is filled in. The password is not, and the dashboard stays closed.

Sign-in checks the email and password hash. A successful sign-in replaces the anonymous session with a new signed cookie. The cookie is HttpOnly and SameSite=Lax. It lasts 12 hours and refreshes while the app is used. Set `TRITOBOL_COOKIE_SECURE=1` when the app is reached over HTTPS so the cookie is marked Secure. Loopback HTTP leaves that flag off, or the browser would not store the session.

Sign-out clears the session and the prompt held in memory. Browser history stays until the user erases it.

Change password is on the Settings page for a signed-in user. It asks for the current password. Email recovery is not configured. Tritobol does not send mail and does not create reset links. A lost password cannot be recovered from the app.

## Password storage

Passwords are hashed with Werkzeug's scrypt hasher before they are written. The database never stores the plaintext password, and the server does not log it. Queries use parameters.

Sign-in allows 8 failures in 15 minutes for an email address and for a client address, then it asks the person to wait. State-changing account requests need the page's `X-Tritobol-Token` and an `X-CSRF-Token` from `GET /api/auth/session`.

## Backup

Copy `tritobol.sqlite` while the app is stopped. Restoring that file restores the accounts. It does not restore browser history, which lives in the browser. Keep the copy as private as the installation itself, because it contains password hashes and email addresses.
