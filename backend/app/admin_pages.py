"""Static HTML for small admin-panel pages (kept out of admin.py: long template lines)."""

# ruff: noqa: E501
from __future__ import annotations

PW_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Choose your password</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f4f5f3;margin:0;padding:24px;color:#23302a}
.card{max-width:440px;margin:40px auto;background:#fff;border:1px solid #e8e6e1;border-radius:14px;padding:24px}
h1{font-size:20px;margin:0 0 6px}p{color:#6b726c;font-size:13px}label{display:block;font-weight:600;font-size:13px;margin:12px 0 4px}
input{width:100%;box-sizing:border-box;padding:9px 10px;border:1px solid #d9dcd8;border-radius:8px;font-size:14px}
.help{color:#6b726c;font-size:12px;margin-top:3px}button{margin-top:16px;padding:9px 14px;border:0;border-radius:8px;background:#198653;color:#fff;font-weight:600;cursor:pointer}
.err{background:#fdeaea;border:1px solid #f2c2c2;color:#b00;padding:10px 12px;border-radius:8px;margin:10px 0}
</style></head><body><form class="card" method="post" autocomplete="off">
<h1>Choose your own password</h1>
<p>__LEAD__</p>__ERR__
<label for="cur">Current password <span style="color:#b00">*</span></label>
<input id="cur" type="password" name="current_password" required autocomplete="current-password">
<div class="help">The password you signed in with just now.</div>
<label for="new">New password <span style="color:#b00">*</span></label>
<input id="new" type="password" name="new_password" required minlength="12" autocomplete="new-password">
<div class="help">At least 12 characters, with at least one letter and one digit. Example: a short sentence only you know.</div>
<label for="rep">Repeat new password <span style="color:#b00">*</span></label>
<input id="rep" type="password" name="confirm_password" required minlength="12" autocomplete="new-password">
<button type="submit">Save password</button> <a href="/admin/logout" style="margin-left:10px;font-size:13px">Log out</a>
</form></body></html>"""


TWO_FACTOR_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Two-factor sign-in</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f4f5f3;margin:0;padding:24px;color:#23302a}
.card{max-width:440px;margin:40px auto;background:#fff;border:1px solid #e8e6e1;border-radius:14px;padding:24px}
h1{font-size:20px;margin:0 0 6px}p{color:#6b726c;font-size:13px}label{display:block;font-weight:600;font-size:13px;margin:12px 0 4px}
input{width:100%;box-sizing:border-box;padding:9px 10px;border:1px solid #d9dcd8;border-radius:8px;font-size:18px;letter-spacing:2px}
.help{color:#6b726c;font-size:12px;margin-top:3px}button{margin-top:16px;padding:9px 14px;border:0;border-radius:8px;background:#198653;color:#fff;font-weight:600;cursor:pointer}
.err{background:#fdeaea;border:1px solid #f2c2c2;color:#b00;padding:10px 12px;border-radius:8px;margin:10px 0}
</style></head><body><form class="card" method="post" autocomplete="off">
<h1>Two-factor sign-in</h1>
<p>Your password was correct. Enter the 6-digit code from your authenticator app to open the admin panel.</p>__ERR__
<label for="code">Code <span style="color:#b00">*</span></label>
<input id="code" name="code" required autofocus inputmode="numeric" autocomplete="one-time-code" maxlength="24" placeholder="123456">
<div class="help">Lost your phone? Enter one of your recovery codes instead, such as ABCD-EFGH-JKLM-NPQR.</div>
<button type="submit">Continue</button> <a href="/admin/logout" style="margin-left:10px;font-size:13px">Log out</a>
</form></body></html>"""

