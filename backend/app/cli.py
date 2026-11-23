"""Admin commands for a local Autopilot.

    .venv/bin/python -m app.cli delete-user someone@example.com

Deletes a person's account so the same email can sign up from scratch. If they were the only
member of their organization, the organization and everything in it (departments, AI
employees, goals, work logs) is deleted too. Otherwise the organization keeps its goals and,
if they were its last owner, someone else becomes owner. Pending invitations for the email
are removed, so a fresh sign-up goes through onboarding instead of joining automatically.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import delete, func, select, update

from app.db import session_scope
from app.models import (
    Campaign,
    ExclusionRule,
    Invitation,
    Membership,
    Organization,
    PermissionGrant,
    Role,
    User,
)


async def plan_delete(email: str) -> dict | None:
    async with session_scope() as s:
        user = (await s.execute(select(User).where(func.lower(User.email) == email.lower()))).scalar_one_or_none()
        invites = (await s.execute(select(func.count()).select_from(Invitation).where(
            func.lower(Invitation.email) == email.lower(), Invitation.accepted_at.is_(None)))).scalar_one()
        if not user:
            return {"user": None, "invites": invites}
        m = (await s.execute(select(Membership).where(Membership.user_id == user.id))).scalar_one_or_none()
        info = {"user": user.id, "name": user.name, "invites": invites, "org": None}
        if m:
            org = await s.get(Organization, m.org_id)
            others = (await s.execute(select(func.count()).select_from(Membership).where(
                Membership.org_id == m.org_id, Membership.user_id != user.id))).scalar_one()
            goals = (await s.execute(select(func.count()).select_from(Campaign).where(Campaign.org_id == m.org_id))).scalar_one()
            info["org"] = {"id": org.id, "name": org.name, "role": m.role, "others": others, "goals": goals}
        return info


async def delete_user(email: str) -> list[str]:
    done: list[str] = []
    async with session_scope() as s:
        user = (await s.execute(select(User).where(func.lower(User.email) == email.lower()))).scalar_one_or_none()
        n = (await s.execute(delete(Invitation).where(func.lower(Invitation.email) == email.lower(),
                                                       Invitation.accepted_at.is_(None)))).rowcount
        if n:
            done.append(f"Removed {n} pending invitation(s) for {email}.")
        if not user:
            return done
        m = (await s.execute(select(Membership).where(Membership.user_id == user.id))).scalar_one_or_none()
        if m:
            org = await s.get(Organization, m.org_id)
            others = (await s.execute(select(Membership).where(
                Membership.org_id == m.org_id, Membership.user_id != user.id).order_by(Membership.created_at))).scalars().all()
            if not others:
                await s.delete(org)  # departments, AI employees, goals, logs... go with it
                done.append(f'Deleted the organization "{org.name}" and everything in it (they were its only member).')
            else:
                # Keep the organization's goals and rules: they belonged to the team, not just this person.
                for model in (Campaign, ExclusionRule, PermissionGrant):
                    await s.execute(update(model).where(model.owner_id == user.id, model.org_id == org.id)
                                    .values(owner_id=None))
                if m.role == Role.owner.value and not any(o.role == Role.owner.value for o in others):
                    heir = next((o for o in others if o.role == Role.admin.value), others[0])
                    heir.role = Role.owner.value
                    heir_user = await s.get(User, heir.user_id)
                    done.append(f"Made {heir_user.email} an owner of {org.name}, since {email} was its last owner.")
                done.append(f'Kept the organization "{org.name}" ({len(others)} other member(s)).')
        await s.delete(user)
        done.append(f"Deleted the account {email}.")
    return done


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("delete-user", help="Delete an account so the email can sign up again")
    d.add_argument("email")
    d.add_argument("--yes", action="store_true", help="Don't ask for confirmation")
    args = parser.parse_args()

    if args.command == "delete-user":
        info = asyncio.run(plan_delete(args.email))
        if not info["user"] and not info["invites"]:
            print(f"No account or invitation for {args.email}. Nothing to do.")
            return
        print(f"About to delete {args.email}:")
        if info["user"]:
            org = info["org"]
            if org and org["others"] == 0:
                print(f'  - their account, and the organization "{org["name"]}" with its {org["goals"]} goal(s), '
                      "departments, AI employees and work logs (they're its only member)")
            elif org:
                print(f'  - their account. "{org["name"]}" stays, with its goals, for its {org["others"]} other member(s)')
            else:
                print("  - their account")
        if info["invites"]:
            print(f"  - {info['invites']} pending invitation(s) to this email")
        if not args.yes and input("Type the email again to confirm: ").strip().lower() != args.email.lower():
            print("Not confirmed. Nothing was deleted.")
            sys.exit(1)
        for line in asyncio.run(delete_user(args.email)):
            print(line)
        print("Done. That email can now sign up again and go through onboarding.")


if __name__ == "__main__":
    main()
