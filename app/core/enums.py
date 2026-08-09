from enum import Enum


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    DEVELOPER = "developer"


class UserStatus(str, Enum):
    ACTIVE = "active"           # normal, fully operational account
    INACTIVE = "inactive"       # self-deactivated or admin-disabled
    SUSPENDED = "suspended"     # temporarily locked (e.g. too many failed logins)
    BANNED = "banned"           # permanently blocked

