"""Who the signed-in user is and what they may do -- read by the frontend on
load to decide which pages and nav items to show (app.libs.roles)."""
from fastapi import APIRouter

from app.auth import AuthorizedUser
from app.libs import roles, schedule_board

router = APIRouter(prefix="/me", tags=["me"])

#: Every signed-in user, crew included, needs to learn their own role.
MIN_ROLE = "crew"


@router.get("")
async def get_me(user: AuthorizedUser) -> dict:
    role = await roles.resolve_role(user.email)
    person = None
    try:
        board = await schedule_board.load_board()
        person = board.person_for_email(user.email or "") if board else None
    except Exception as exc:  # noqa: BLE001 - the role is what matters here
        print(f"/me roster lookup skipped: {exc}")
    return {
        "email": user.email,
        "role": role,
        "isAdmin": roles.at_least(role, "admin"),
        "isSuperAdmin": role == "super_admin",
        "fieldOnly": role in ("crew", "lead"),
        # The warehouse display: the install schedule, read-only, nothing else.
        "viewOnly": role == "viewer",
        "person": person,
    }
