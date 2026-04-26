from k8s_diagnose.k8s_client.permissions import (
    PermissionMode,
    ALLOWED_KUBECTL_COMMANDS,
    BLACKLIST_KEYWORDS,
)


class TestPermissionModes:
    def test_read_only_has_get(self):
        assert "get" in ALLOWED_KUBECTL_COMMANDS[PermissionMode.READ_ONLY]

    def test_read_only_has_describe(self):
        assert "describe" in ALLOWED_KUBECTL_COMMANDS[PermissionMode.READ_ONLY]

    def test_read_only_no_delete(self):
        assert "delete" not in ALLOWED_KUBECTL_COMMANDS[PermissionMode.READ_ONLY]

    def test_read_only_no_logs(self):
        assert "logs" not in ALLOWED_KUBECTL_COMMANDS[PermissionMode.READ_ONLY]

    def test_diagnostic_has_logs(self):
        assert "logs" in ALLOWED_KUBECTL_COMMANDS[PermissionMode.DIAGNOSTIC]

    def test_diagnostic_no_delete(self):
        assert "delete" not in ALLOWED_KUBECTL_COMMANDS[PermissionMode.DIAGNOSTIC]

    def test_read_write_has_all(self):
        rw = ALLOWED_KUBECTL_COMMANDS[PermissionMode.READ_WRITE]
        for mode in PermissionMode:
            for cmd in ALLOWED_KUBECTL_COMMANDS[mode]:
                assert cmd in rw


class TestBlacklistKeywords:
    def test_delete_in_blacklist(self):
        keywords = [k for k, _ in BLACKLIST_KEYWORDS]
        assert "delete" in keywords

    def test_force_in_blacklist(self):
        keywords = [k for k, _ in BLACKLIST_KEYWORDS]
        assert "--force" in keywords

    def test_blacklist_has_reasons(self):
        for keyword, reason in BLACKLIST_KEYWORDS:
            assert len(keyword) > 0
            assert len(reason) > 0
