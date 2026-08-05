import unittest
from copy import deepcopy
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def read_json(relative_path: str) -> dict:
    return json.loads(read_text(relative_path))


def assert_public_safe_text(testcase: unittest.TestCase, text: str) -> None:
    forbidden_patterns = [
        r"WEFLOW_TOKEN\s*=",
        r"WEFLOW_DB_KEY\s*=",
        r"ghp_[A-Za-z0-9]{36}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"wxid_[A-Za-z0-9_-]{8,}",
        r"\d+@chatroom",
        r"(?<![A-Za-z])[A-Za-z]:[\\/][^\s\"']+",
    ]
    for pattern in forbidden_patterns:
        with testcase.subTest(pattern=pattern):
            testcase.assertIsNone(re.search(pattern, text))


class ProjectContractTests(unittest.TestCase):
    def test_readme_targets_chinese_wechat_history_ai_users(self):
        readme = read_text("README.md")

        required_terms = [
            "微信聊天记录 AI 本地桥（WeChat History AI Bridge）",
            "想让 AI 安全读取、检索和总结本地微信聊天记录",
            "微信聊天记录怎么导出",
            "微信群聊天记录怎么总结",
            "WeFlow 负责本地读取微信数据",
            "WeFlowBridge 负责把它整理成 AI 友好的安全接口",
            "English: Local-first WeChat chat history bridge for AI agents, powered by WeFlow.",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, readme)

        first_screen = readme[:1800]
        self.assertIn("微信聊天记录", first_screen)
        self.assertIn("AI", first_screen)
        self.assertIn("WeFlow", first_screen)
        self.assertNotIn("Local-first WeChat API bridge for AI agents", first_screen)
        self.assertNotIn("私有，供 AI 集成", first_screen)
        self.assertNotIn("给我（主脑）", first_screen)

    def test_project_manifest_exists_and_defines_ai_safe_boundaries(self):
        manifest = read_json("project_manifest.json")

        self.assertEqual(manifest["project"], "WeFlowBridge")
        self.assertEqual(
            manifest["display_name"],
            "微信聊天记录 AI 本地桥（WeChat History AI Bridge）",
        )
        self.assertEqual(manifest["repository"], "wlyaaaaa/wechat-history-ai-bridge")
        self.assertEqual(manifest["visibility"], "public")
        self.assertEqual(manifest["role"], "provider_facing_adapter")
        self.assertEqual(manifest["closeout_status"], "ready_for_normal_maintenance")
        self.assertEqual(manifest["closeout_audit"], "docs/closeout_audit.md")
        self.assertTrue(manifest["no_raw_wechat_data"])
        self.assertEqual(
            manifest["ai_calling_layer"],
            r"E:\.agents\plugins\weflow-toolkit",
        )

        required_fields = set(manifest["required_output_envelope"])
        self.assertGreaterEqual(
            required_fields,
            {
                "current_library",
                "target_conversation",
                "talker",
                "time_window",
                "retry_count",
                "message_count",
                "lastTimestamp_matches_newest",
            },
        )

        forbidden = set(manifest["privacy_forbidden"])
        self.assertIn("raw_messages", forbidden)
        self.assertIn("database_files", forbidden)
        self.assertIn("conversation_screenshots", forbidden)
        handoff = manifest["private_snapshot_handoff"]
        self.assertEqual(
            handoff["status"],
            "allowed_for_explicitly_authorized_private_consumer",
        )
        self.assertEqual(
            handoff["allowed_consumer"],
            "PersonalOS private late-bound runtime",
        )
        self.assertIn(
            "no source write-back and no second writable WeFlow state",
            handoff["requirements"],
        )

    def test_closeout_audit_exists_and_records_final_gate(self):
        text = read_text("docs/closeout_audit.md")

        required_terms = [
            "Closeout Audit",
            "ready_for_normal_maintenance",
            "No Raw WeChat Data",
            "Public Repository Boundary",
            "AI Consumer Boundary",
            "Non-Goals",
            "Reopen Triggers",
            "Verification Evidence",
            "Residual Risks",
            "2026-07-07",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_ai_consumer_contract_exists_and_defines_required_fields(self):
        text = read_text("docs/ai_consumer_contract.md")

        required_terms = [
            "AI Consumer Contract",
            "current_library",
            "target_conversation",
            "talker",
            "time_window",
            "retry_count",
            "message_count",
            "lastTimestamp_matches_newest",
            "PersonalOS",
            "Private immutable snapshot handoff",
            "private, non-repository destination",
            "no second writable database",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_weflow_2673_ai_contract_is_documented(self):
        manifest = read_json("project_manifest.json")
        readme = read_text("README.md")
        agents = read_text("AGENTS.md")
        contract = read_text("docs/ai_consumer_contract.md")

        self.assertEqual(manifest["weflow_baseline"]["version"], "26.7.3")
        self.assertEqual(manifest["weflow_baseline"]["verified_on"], "2026-07-09")
        self.assertIn("ai_contract_version", manifest)
        self.assertEqual(manifest["ai_contract_version"], "v2")

        for text in (readme, agents):
            with self.subTest(document="entrypoint"):
                self.assertIn("26.7.3", text)
                self.assertIn("ChatLab Pull", text)
                self.assertIn("POST", text)

        required_contract_terms = [
            "AI Consumer Contract v2",
            "ChatLab Pull",
            "/api/v1/sessions/{id}/messages",
            "request_method",
            "endpoint_family",
            "sync_watermark",
            "replyToMessageId",
            "quote",
            "media_manifest",
        ]
        for term in required_contract_terms:
            with self.subTest(term=term):
                self.assertIn(term, contract)

    def test_machine_contract_files_exist_and_are_indexed(self):
        manifest = read_json("project_manifest.json")

        self.assertEqual(manifest["integration_readiness"]["status"], "ai_integration_1_0_ready")
        self.assertEqual(manifest["integration_readiness"]["release_tag"], "v0.1.0")

        machine_contracts = manifest["machine_contracts"]
        expected_paths = {
            "openapi": "docs/openapi.yaml",
            "ai_consumer_envelope_schema": "schemas/ai-consumer-envelope.v2.schema.json",
            "project_manifest_schema": "schemas/project-manifest.v1.schema.json",
            "ai_consumer_envelope_example": "docs/examples/ai_consumer_envelope.example.json",
        }
        self.assertEqual(machine_contracts, expected_paths)

        for relative_path in expected_paths.values():
            with self.subTest(path=relative_path):
                self.assertTrue((ROOT / relative_path).is_file())

    def test_openapi_covers_ai_safe_weflow_surface(self):
        openapi = read_text("docs/openapi.yaml")

        required_terms = [
            "openapi: 3.1.0",
            "WeFlowBridge AI Integration API",
            "/health:",
            "/api/v1/sessions:",
            "/api/v1/contacts:",
            "/api/v1/messages:",
            "/api/v1/sessions/{id}/messages:",
            "/api/v1/group-members:",
            "/api/v1/sns/timeline:",
            "/api/v1/sns/export/stats:",
            "/api/v1/push/messages:",
            "bearerAuth:",
            "x-weflowbridge-ai-preferred: true",
            "x-weflowbridge-risk: write-operation",
            "sync_watermark",
            "media_manifest",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, openapi)

        assert_public_safe_text(self, openapi)
        self.assertNotIn("mediaPath", openapi)

    def test_ai_envelope_schema_and_example_are_public_safe(self):
        schema = read_json("schemas/ai-consumer-envelope.v2.schema.json")
        example = read_json("docs/examples/ai_consumer_envelope.example.json")

        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(
            schema["$id"],
            "https://github.com/wlyaaaaa/wechat-history-ai-bridge/schemas/ai-consumer-envelope.v2.schema.json",
        )
        self.assertEqual(schema["title"], "WeFlowBridge AI Consumer Envelope v2")
        self.assertFalse(schema["additionalProperties"])
        required = set(schema["required"])
        self.assertGreaterEqual(
            required,
            {
                "current_library",
                "schema_version",
                "library_evidence",
                "target_account",
                "target_conversation",
                "talker",
                "time_window",
                "retry_count",
                "message_count",
                "lastTimestamp_matches_newest",
                "content_scope",
                "request_method",
                "endpoint_family",
                "sync_watermark",
                "media_manifest",
                "message_content_included",
                "privacy",
            },
        )
        for forbidden_key in ("raw_messages", "message_text", "mediaPath", "local_path"):
            with self.subTest(forbidden_key=forbidden_key):
                self.assertNotIn(forbidden_key, schema["properties"])
        self.assertFalse(schema["properties"]["privacy"]["additionalProperties"])
        self.assertFalse(schema["properties"]["reply_metadata"]["items"]["additionalProperties"])
        self.assertEqual(example["schema_version"], "ai-consumer-envelope.v2")
        self.assertEqual(example["talker"], "<redacted:chatroom>")
        self.assertFalse(example["message_content_included"])
        self.assertTrue(example["privacy"]["redacted"])
        assert_public_safe_text(self, json.dumps(example, ensure_ascii=False))

    def test_project_manifest_schema_tracks_current_manifest(self):
        schema = read_json("schemas/project-manifest.v1.schema.json")
        manifest = read_json("project_manifest.json")

        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(
            schema["$id"],
            "https://github.com/wlyaaaaa/wechat-history-ai-bridge/schemas/project-manifest.v1.schema.json",
        )
        self.assertEqual(schema["title"], "WeFlowBridge Project Manifest v1")
        self.assertIn("display_name", schema["required"])
        self.assertEqual(
            schema["properties"]["display_name"]["const"],
            "微信聊天记录 AI 本地桥（WeChat History AI Bridge）",
        )
        self.assertEqual(
            schema["properties"]["repository"]["const"],
            "wlyaaaaa/wechat-history-ai-bridge",
        )
        self.assertIn("machine_contracts", schema["required"])
        self.assertIn("integration_readiness", schema["required"])
        for key in manifest["machine_contracts"]:
            with self.subTest(contract_key=key):
                self.assertIn(key, schema["properties"]["machine_contracts"]["required"])

    def test_project_manifest_schema_rejects_missing_or_malformed_private_handoff(self):
        schema = read_json("schemas/project-manifest.v1.schema.json")
        manifest = read_json("project_manifest.json")
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(manifest)

        missing = deepcopy(manifest)
        del missing["private_snapshot_handoff"]
        with self.assertRaises(ValidationError):
            validator.validate(missing)

        malformed_cases = []
        malformed = deepcopy(manifest)
        malformed["private_snapshot_handoff"]["owner_boundary"] = "ambiguous"
        malformed_cases.append(malformed)
        malformed = deepcopy(manifest)
        malformed["private_snapshot_handoff"]["requirements"] = [
            "explicit user source authorization"
        ]
        malformed_cases.append(malformed)
        malformed = deepcopy(manifest)
        malformed["private_snapshot_handoff"]["forbidden"] = []
        malformed_cases.append(malformed)
        malformed = deepcopy(manifest)
        malformed["private_snapshot_handoff"]["unexpected"] = True
        malformed_cases.append(malformed)

        for malformed in malformed_cases:
            with self.subTest(handoff=malformed["private_snapshot_handoff"]):
                with self.assertRaises(ValidationError):
                    validator.validate(malformed)

    def test_private_snapshot_owner_boundary_is_consistent_across_contracts(self):
        manifest = read_json("project_manifest.json")
        schema = read_json("schemas/project-manifest.v1.schema.json")
        canonical_owner_boundary = (
            "WeFlow/WeLive owns source data, decryption, and export implementation; "
            "WeFlowBridge owns version-bound adaptation, handoff, and verification "
            "contracts; PersonalOS owns the authorized private immutable package and "
            "derived representations"
        )

        self.assertEqual(
            manifest["private_snapshot_handoff"]["owner_boundary"],
            canonical_owner_boundary,
        )
        self.assertEqual(
            schema["properties"]["private_snapshot_handoff"]["properties"]
            ["owner_boundary"]["const"],
            canonical_owner_boundary,
        )

        agents = read_text("AGENTS.md")
        for term in (
            "WeFlow/WeLive 拥有源数据、解密与导出实现",
            "WeFlowBridge 只拥有版本绑定的适配、交接及验证合同",
            "PersonalOS 拥有该私密包及其可替换派生表示",
        ):
            with self.subTest(document="AGENTS.md", term=term):
                self.assertIn(term, agents)

        for relative_path in (
            "docs/ai_consumer_contract.md",
            "docs/privacy_boundary.md",
        ):
            text = re.sub(r"\s+", " ", read_text(relative_path))
            for term in (
                "WeFlow/WeLive owns source data, decryption and export implementation",
                "WeFlowBridge owns",
                "version-bound adaptation, handoff and verification contract",
                "PersonalOS owns",
            ):
                with self.subTest(document=relative_path, term=term):
                    self.assertIn(term, text)

    def test_public_boundary_scripts_exist_and_cover_ci_checks(self):
        public_boundary = read_text("tools/test-public-boundary.ps1")
        ci_local = read_text("tools/test-ci-local.ps1")

        required_public_boundary_terms = [
            "git ls-files",
            "git check-ignore",
            "probe-weflow.ps1",
            "weflow_heartbeat.ps1",
            "weflow_boot_guardian.ps1",
            "enable-autologin.ps1",
            "System.Management.Automation.Language.Parser",
            "WEFLOW_TOKEN",
            "WEFLOW_DB_KEY",
            "PRIVATE KEY",
            "pdftotext",
            "api-media/",
            "exports/",
            "dump/",
            "*.sqlite",
            "*.png",
            "*.jpg",
            "*.webp",
            "*.mp4",
            "*.m4a",
            "chatlab*.json",
            "messages*.json",
            "README.pdf",
            "AGENTS.pdf",
            "WATCHDOG.pdf",
        ]
        for term in required_public_boundary_terms:
            with self.subTest(term=term):
                self.assertIn(term, public_boundary)

        required_ci_terms = [
            "python -m unittest tests/test_project_contracts.py",
            "tools/test-public-boundary.ps1",
        ]
        for term in required_ci_terms:
            with self.subTest(term=term):
                self.assertIn(term, ci_local)

        self.assertNotIn("Register-ScheduledTask", public_boundary)
        self.assertNotIn("Set-ItemProperty", public_boundary)
        self.assertNotIn("Start-Process", public_boundary)

    def test_boot_guardian_preserves_pcconfig_owned_wechat_autostart(self):
        script = read_text("weflow_boot_guardian.ps1")
        watchdog = read_text("WATCHDOG.md")
        owner_marker = "owner=pcconfig.wechat-dual-autostart.v1"
        task_lookup = (
            "Get-ScheduledTask -TaskName 'WeChat AutoStart' "
            "-ErrorAction SilentlyContinue"
        )
        owner_check = (
            "Where-Object { "
            "([string]$_.Description).Contains($wechatTaskOwnerMarker) }"
        )
        register_call = "Register-ScheduledTask -TaskName 'WeChat AutoStart'"

        self.assertIn(owner_marker, script)
        self.assertIn(task_lookup, script)
        self.assertIn(owner_check, script)
        self.assertEqual(script.count(register_call), 1)

        lookup_index = script.index(task_lookup)
        guard_index = script.index("if ($pcConfigOwnedWeChatTask)", lookup_index)
        fallback_index = script.index("} else {", guard_index)
        register_index = script.index(register_call)
        self.assertLess(lookup_index, guard_index)
        self.assertLess(guard_index, fallback_index)
        self.assertLess(fallback_index, register_index)
        self.assertNotIn(register_call, script[guard_index:fallback_index])
        legacy_fallback = script[register_index:]
        self.assertIn(
            "-Description '登录时自动启动微信(稳定，无重启看门狗)' -Force",
            legacy_fallback,
        )

        self.assertIn(owner_marker, watchdog)
        self.assertIn("保留 PCConfig 管理的双开任务", watchdog)
        self.assertIn("仍按原行为注册单次启动任务", watchdog)

    def test_heartbeat_supports_bounded_multi_profile_startup(self):
        script = read_text("weflow_heartbeat.ps1")
        vbs = read_text("weflow_heartbeat.vbs")
        watchdog = read_text("WATCHDOG.md")

        required_script_terms = [
            "[ValidateRange(1, 65535)]",
            "[int]$Port = 5031",
            "[string]$UserDataDir",
            "[string]$InstanceName",
            "[string]$LogPath",
            "[switch]$NoProxyServer",
            "[switch]$HiddenLaunch",
            "function Test-WeFlowHealth",
            "Invoke-WebRequest",
            "-TimeoutSec $HttpTimeoutSeconds",
            "ConnectAsync('127.0.0.1', $Port)",
            ".Wait($TcpTimeoutMilliseconds)",
            "function Get-TargetWeFlowProcess",
            "Get-CimInstance -ClassName Win32_Process",
            "([string]$process.CommandLine)",
            "--user-data-dir",
            "required profile directory is missing",
            "Test-Path -LiteralPath $effectiveUserDataDir -PathType Container",
            "$profileMatch = [regex]::Match($commandLine, $userDataPattern)",
            "if (-not $targetProfilePath)",
            "if (-not $profileMatch.Success) { return $process }",
            "OrdinalIgnoreCase.Equals($normalizedProcessProfilePath, $targetProfilePath)",
            "$targetProfileProcess = Get-TargetWeFlowProcess",
            "WorkingDirectory = $workingDirectory",
            "$startParameters['ArgumentList']",
            "--user-data-dir=`\"$effectiveUserDataDir`\"",
            "--no-proxy-server",
            "$startParameters['WindowStyle'] = 'Hidden'",
            "Start-Process @startParameters",
            "$StartupWaitSeconds = 30",
            "$startupDeadline = (Get-Date).AddSeconds($StartupWaitSeconds)",
            "while ((Get-Date) -lt $startupDeadline)",
        ]
        for term in required_script_terms:
            with self.subTest(term=term):
                self.assertIn(term, script)

        self.assertNotIn("Get-Process WeFlow", script)
        self.assertNotIn("while ($true)", script)
        self.assertEqual(script.count("Start-Process @startParameters"), 1)
        target_lookup_index = script.index(
            "$targetProfileProcess = Get-TargetWeFlowProcess"
        )
        target_guard_index = script.index(
            "if ($targetProfileProcess)", target_lookup_index
        )
        start_index = script.index("Start-Process @startParameters")
        self.assertLess(target_lookup_index, target_guard_index)
        self.assertLess(target_guard_index, start_index)

        self.assertIn('QuoteCommandLineArgument(here & "\\weflow_heartbeat.ps1")', vbs)
        self.assertIn("For Each argument In WScript.Arguments", vbs)
        self.assertIn("QuoteCommandLineArgument", vbs)

        required_doc_terms = [
            "零参数调用保持兼容",
            "`-Port`",
            "`-UserDataDir`",
            "`-InstanceName`",
            "`-LogPath`",
            "`-NoProxyServer`",
            "`-HiddenLaunch`",
            "16000",
            "只匹配目标 profile",
            "profile 目录不存在时失败关闭",
            "有界等待",
        ]
        for term in required_doc_terms:
            with self.subTest(term=term):
                self.assertIn(term, watchdog)

    def test_probe_weflow_supports_metadata_only_json_mode(self):
        script = read_text("probe-weflow.ps1")

        required_terms = [
            "[switch]$Json",
            "[ValidateSet('MetadataOnly','FullProbe')]",
            "[switch]$NoMessages",
            "schema_version",
            "weflow-probe.v1",
            "weflow_baseline",
            "base_url_redacted",
            "token_present",
            "endpoint_results",
            "$effectiveNoMessages = $NoMessages -or $Mode -eq 'MetadataOnly'",
            "message_text_printed",
            "raw_media_paths_included",
            "token_printed",
            "ConvertTo-Json",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, script)

        self.assertNotIn("Register-ScheduledTask", script)
        self.assertNotIn("Set-ItemProperty", script)
        self.assertNotIn("DefaultPassword", script)

    def test_openapi_write_operations_are_not_ai_callable(self):
        openapi = read_text("docs/openapi.yaml")

        self.assertIn("x-weflowbridge-ai-allowed: false", openapi)
        self.assertIn("deprecated: true", openapi)
        write_operation_count = openapi.count("x-weflowbridge-risk: write-operation")
        not_allowed_count = openapi.count("x-weflowbridge-ai-allowed: false")
        self.assertEqual(write_operation_count + 1, not_allowed_count)

    def test_openapi_push_stream_is_not_default_ai_callable(self):
        openapi = read_text("docs/openapi.yaml")
        push_section = openapi.split("/api/v1/push/messages:", 1)[1]
        push_section = push_section.split("components:", 1)[0]

        self.assertIn("access_token", push_section)
        self.assertIn("text/event-stream", push_section)
        self.assertIn("x-weflowbridge-ai-allowed: false", push_section)
        self.assertIn("x-weflowbridge-risk: live-raw-stream", push_section)
        self.assertIn("deprecated: true", push_section)

    def test_ci_workflow_and_docs_link_machine_contracts(self):
        workflow = read_text(".github/workflows/contract.yml")
        readme = read_text("README.md")
        agents = read_text("AGENTS.md")
        contract = read_text("docs/ai_consumer_contract.md")
        closeout = read_text("docs/closeout_audit.md")
        manifest = read_json("project_manifest.json")

        workflow_terms = [
            "windows-latest",
            "choco install poppler",
            "python -m unittest tests/test_project_contracts.py",
            "tools/test-ci-local.ps1",
            "pull_request",
            "push",
        ]
        for term in workflow_terms:
            with self.subTest(term=term):
                self.assertIn(term, workflow)

        linked_docs = (readme, agents, contract)
        for text in linked_docs:
            with self.subTest(document="machine_contract_links"):
                self.assertIn("docs/openapi.yaml", text)
                self.assertIn("schemas/ai-consumer-envelope.v2.schema.json", text)

        self.assertIn("schemas/project-manifest.v1.schema.json", readme)
        self.assertIn("documented but not an AI envelope endpoint", contract)
        self.assertIn("AI Integration 1.0", closeout)
        public_boundary_command = manifest["safe_verification"]["public_boundary"].replace("\\", "/")
        local_ci_command = manifest["safe_verification"]["local_ci"].replace("\\", "/")
        self.assertIn("tools/test-public-boundary.ps1", public_boundary_command)
        self.assertIn("tools/test-ci-local.ps1", local_ci_command)

    def test_ai_docs_prefer_v2_toolkit_and_chatlab_history(self):
        readme = read_text("README.md")
        agents = read_text("AGENTS.md")
        contract = read_text("docs/ai_consumer_contract.md")

        for text in (readme, agents):
            with self.subTest(document="entrypoint"):
                self.assertIn("weflow-toolkit v0.2+", text)
                self.assertIn("/api/v1/sessions/{id}/messages", text)
                self.assertIn("ChatLab Pull", text)
                self.assertIn("最新消息：不带 start/end", text)

        forbidden_preferred_examples = [
            "历史区间：显式 start/end",
            "历史区间显式 `start/end`",
            "chatlab=1&limit=20",
            "chatlab=1, \"limit\": 100",
            "safe local path hints",
            "api-media",
            "wxid_xxx/images",
            "mediaPath",
        ]
        for term in forbidden_preferred_examples:
            with self.subTest(term=term):
                self.assertNotIn(term, readme)
                self.assertNotIn(term, agents)
                self.assertNotIn(term, contract)

        self.assertIn("raw media paths", contract)
        self.assertIn("non-path", contract)

    def test_privacy_boundary_exists_and_blocks_private_material(self):
        text = read_text("docs/privacy_boundary.md")

        required_terms = [
            "Privacy Boundary",
            "public repository",
            ".env",
            "WEFLOW_TOKEN",
            "raw messages",
            "screenshots",
            "database",
            "exports/",
            "private late-bound runtime",
            "not a second writable WeFlow",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_entry_docs_link_to_contracts(self):
        readme = read_text("README.md")
        agents = read_text("AGENTS.md")

        self.assertIn("project_manifest.json", readme)
        self.assertIn("project_manifest.json", agents)
        self.assertIn("docs/closeout_audit.md", readme)
        self.assertIn("docs/closeout_audit.md", agents)
        self.assertIn("docs/ai_consumer_contract.md", readme)
        self.assertIn("docs/privacy_boundary.md", readme)
        self.assertIn("docs/ai_consumer_contract.md", agents)
        self.assertIn("docs/privacy_boundary.md", agents)

    def test_gitignore_blocks_weflow_private_outputs(self):
        text = read_text(".gitignore")

        required_patterns = [
            ".env",
            ".env.*",
            "api-media/",
            "exports/",
            "dump/",
            "*.db",
            "*.sqlite",
            "*.sqlite3",
            "*.db-wal",
            "*.db-shm",
            "*.sqlite-wal",
            "*.sqlite-shm",
            "logs/",
        ]
        for pattern in required_patterns:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, text)


if __name__ == "__main__":
    unittest.main()
