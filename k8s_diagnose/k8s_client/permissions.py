"""Permission policies: command whitelist and keyword blacklist."""
from enum import StrEnum


class PermissionMode(StrEnum):
    READ_ONLY = "read-only"
    DIAGNOSTIC = "diagnostic"
    READ_WRITE = "read-write"


# Subcommand whitelist per permission mode
ALLOWED_KUBECTL_COMMANDS: dict[PermissionMode, set[str]] = {
    PermissionMode.READ_ONLY: {
        "get", "describe", "top", "cluster-info", "version",
        "auth", "api-resources", "api-versions", "explain",
    },
    PermissionMode.DIAGNOSTIC: {
        "get", "describe", "top", "cluster-info", "version",
        "auth", "api-resources", "api-versions", "explain",
        "logs", "exec", "cp",
    },
    PermissionMode.READ_WRITE: {
        "get", "describe", "top", "cluster-info", "version",
        "auth", "api-resources", "api-versions", "explain",
        "logs", "exec", "cp",
        "delete", "patch", "scale", "cordon", "uncordon", "drain",
        "label", "annotate", "taint", "apply", "create",
    },
}

# Global blacklist — always denied, even in READ_WRITE mode
GLOBAL_BLACKLIST: list[tuple[str, str]] = [
    ("--force", "强制删除"),
    ("--grace-period=0", "立即终止"),
]

# Restricted keywords — denied in READ_ONLY and DIAGNOSTIC, allowed in READ_WRITE
RESTRICTED_KEYWORDS: list[tuple[str, str]] = [
    ("delete", "删除资源"),
    ("patch", "修改资源配置"),
    ("scale", "修改副本数"),
    ("cordon", "节点不可调度"),
    ("drain", "驱逐节点Pod"),
    ("taint", "节点加污点"),
]
