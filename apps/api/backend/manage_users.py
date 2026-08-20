"""Account administration from the shell.

    python -m backend.manage_users list
    python -m backend.manage_users add alice@example.com --name Alice --role reviewer
    python -m backend.manage_users role alice@example.com admin
    python -m backend.manage_users password alice@example.com
    python -m backend.manage_users disable alice@example.com
    python -m backend.manage_users enable alice@example.com

A password is read from CRX_PASSWORD when set, otherwise prompted for, so it never
lands in shell history.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from backend.database import database_connection
from backend.services import auth


def _password(confirm: bool = True) -> str:
    from_env = os.environ.get("CRX_PASSWORD")
    if from_env:
        return from_env
    password = getpass.getpass("password: ")
    if confirm and password != getpass.getpass("again: "):
        raise SystemExit("passwords did not match")
    return password


async def _run(args) -> int:
    async with database_connection() as db:
        if args.command == "list":
            async with db.execute(
                "SELECT email, display_name, role, is_active, last_login_at "
                "FROM users ORDER BY email"
            ) as cursor:
                rows = [dict(row) for row in await cursor.fetchall()]
            if not rows:
                print("no accounts yet")
                return 0
            width = max(len(row["email"]) for row in rows)
            for row in rows:
                state = "active" if row["is_active"] else "disabled"
                seen = row["last_login_at"] or "never"
                print(f"{row['email']:<{width}}  {row['role']:<8}  {state:<8}  last login {seen}")
            return 0

        email = auth.normalize_email(args.email)
        if args.command == "add":
            user = await auth.create_user(
                db,
                email=email,
                display_name=args.name or email,
                password=_password(),
                role=args.role,
            )
            await db.commit()
            print(f"created {user['email']} as {user['role']}")
            return 0

        async with db.execute("SELECT id, role FROM users WHERE email = ?", (email,)) as cursor:
            existing = await cursor.fetchone()
        if not existing:
            print(f"no such account: {email}", file=sys.stderr)
            return 1

        if args.command == "role":
            if args.role not in auth.ROLES:
                print(f"role must be one of {', '.join(auth.ROLES)}", file=sys.stderr)
                return 1
            await db.execute("UPDATE users SET role = ? WHERE id = ?", (args.role, existing["id"]))
            print(f"{email}: {existing['role']} -> {args.role}")
        elif args.command == "password":
            password_hash, salt = auth.hash_password(_password())
            await db.execute(
                "UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?",
                (password_hash, salt, existing["id"]),
            )
            # A password change ends every session, which is the point of changing it.
            await auth.revoke_all_sessions(db, existing["id"])
            print(f"{email}: password changed, sessions revoked")
        elif args.command in {"disable", "enable"}:
            active = args.command == "enable"
            await db.execute(
                "UPDATE users SET is_active = ? WHERE id = ?", (active, existing["id"])
            )
            if not active:
                await auth.revoke_all_sessions(db, existing["id"])
            print(f"{email}: {'enabled' if active else 'disabled'}")
        await db.commit()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    add = sub.add_parser("add")
    add.add_argument("email")
    add.add_argument("--name", default=None)
    add.add_argument("--role", default="reader", choices=auth.ROLES)
    role = sub.add_parser("role")
    role.add_argument("email")
    role.add_argument("role")
    for name in ("password", "disable", "enable"):
        command = sub.add_parser(name)
        command.add_argument("email")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
