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


class ProjectRole(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"


class ProjectStatus(str, Enum):
    NOT_STARTED = "Not Started"
    IN_PROGRESS = "In Progress"
    ON_HOLD = "On Hold"
    BLOCKED = "Blocked"
    IN_REVIEW = "In Review"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class InvitationStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class OwnershipTransferStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"



class NotificationType(str, Enum):
    # Collaboration & Team
    PROJECT_INVITATION = "PROJECT_INVITATION"
    PROJECT_INVITATION_ACCEPTED = "PROJECT_INVITATION_ACCEPTED"
    PROJECT_INVITATION_DECLINED = "PROJECT_INVITATION_DECLINED"
    MEMBER_ROLE_CHANGED = "MEMBER_ROLE_CHANGED"
    MEMBER_REMOVED = "MEMBER_REMOVED"
    # Ownership Transfer (2-Step Handshake)
    OWNERSHIP_TRANSFER_REQUEST = "OWNERSHIP_TRANSFER_REQUEST"
    OWNERSHIP_TRANSFER_ACCEPTED = "OWNERSHIP_TRANSFER_ACCEPTED"
    OWNERSHIP_TRANSFER_REJECTED = "OWNERSHIP_TRANSFER_REJECTED"
    OWNERSHIP_TRANSFER_EXPIRED = "OWNERSHIP_TRANSFER_EXPIRED"
    # Backups & Snapshots
    BACKUP_COMPLETED = "BACKUP_COMPLETED"
    BACKUP_FAILED = "BACKUP_FAILED"
    # AI & Architecture
    AI_PROPOSAL_READY = "AI_PROPOSAL_READY"
    # Security & System
    SECURITY_ALERT = "SECURITY_ALERT"
    SYSTEM_ANNOUNCEMENT = "SYSTEM_ANNOUNCEMENT"


class NotificationCategory(str, Enum):
    COLLABORATION = "COLLABORATION"
    OWNERSHIP = "OWNERSHIP"
    BACKUP = "BACKUP"
    AI = "AI"
    SECURITY = "SECURITY"
    SYSTEM = "SYSTEM"


class NotificationActionStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    DISMISSED = "DISMISSED"


