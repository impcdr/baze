"""The quarantine watcher records secret opens, and the review treats them as harm."""

import os
import subprocess
from pathlib import Path

from baze_api.boxes import _review, access_library, call_attempts, given_files, plain_report, program_commands, secret_touches


def _clear(messages):
    return '{"verdict": "clear", "report": "Nothing stood out."}'


def test_given_files_lists_each_box(tmp_path):
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "menu.txt").write_text("soup")
    (tmp_path / "specimen").mkdir()
    (tmp_path / "specimen" / "grab.py").write_text("x")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "invoices.json").write_text("[]")
    (tmp_path / "app" / "index.html").write_text("<p>hi</p>")
    assert given_files(str(tmp_path), "web") == [{"name": "menu.txt", "size": 4, "where": "uploads"}]
    data = given_files(str(tmp_path), "data")
    assert [item["name"] for item in data] == ["menu.txt", "invoices.json"]
    assert data[1]["where"] == "record"
    quarantine = given_files(str(tmp_path), "quarantine")
    assert [item["name"] for item in quarantine] == ["grab.py", "menu.txt"]
    assert quarantine[0]["where"] == "specimen"


def test_a_suspicious_check_names_the_reason_and_a_clear_check_does_not():
    from baze_api.product import _public_check

    shown = _public_check(
        {
            "_id": "b" * 32,
            "name": "Payroll Glance",
            "verdict": "suspicious",
            "specimen": "hours.txt (74 bytes)",
            "report": "The item opened the password file.",
            "reason": "Opened the password file and called 203.0.113.40 on port 443.",
        }
    )
    assert shown["verdict"] == "suspicious"
    assert shown["reason"] == "Opened the password file and called 203.0.113.40 on port 443."
    quiet = _public_check(
        {
            "_id": "c" * 32,
            "name": "Pickup Note",
            "verdict": "clear",
            "specimen": "note.txt (69 bytes)",
            "report": "The item did not read a private file and did not contact another computer.",
        }
    )
    assert quiet["verdict"] == "clear"
    assert quiet["reason"] == ""


def test_a_check_record_keeps_its_own_opens_and_drops_another_boxs_calls(settings):
    from baze_api.db import apps

    from baze_api.boxes import record_check_findings

    app_id = "a" * 32
    apps(settings).insert_one(
        {
            "_id": app_id,
            "slug": "payroll-record",
            "chart": {
                "record": [
                    {"id": "1", "kind": "created", "summary": "Payroll Glance was created.", "at": 1},
                    {
                        "id": "2",
                        "kind": "containment",
                        "summary": "A call was stopped.",
                        "detail": "TCP to 203.0.113.10 port 80.",
                        "at": 2,
                    },
                    {
                        "id": "3",
                        "kind": "containment",
                        "summary": "A call was stopped.",
                        "detail": "TCP to 203.0.113.40 port 443.",
                        "at": 3,
                    },
                    {
                        "id": "4",
                        "kind": "containment",
                        "summary": "A private file was opened.",
                        "detail": "/etc/passwd",
                        "at": 4,
                    },
                ]
            },
        }
    )
    record_check_findings(
        settings,
        app_id,
        ["/etc/shadow", "/etc/gshadow"],
        ["TCP to 203.0.113.40 port 443."],
    )
    record = apps(settings).find_one({"_id": app_id})["chart"]["record"]
    assert [entry["summary"] for entry in record] == [
        "Payroll Glance was created.",
        "A call was stopped.",
        "A private file was opened.",
        "A private file was opened.",
    ]
    assert record[1]["detail"] == "TCP to 203.0.113.40 port 443."
    assert [entry["detail"] for entry in record[2:]] == ["/etc/shadow", "/etc/gshadow"]


def test_the_watcher_records_secret_opens_and_ignores_ordinary_files(tmp_path):
    library = access_library()
    assert library is not None and library.is_file()
    log_path = tmp_path / "access.log"
    env = os.environ.copy()
    env["LD_PRELOAD"] = str(library)
    env["BAZE_ACCESS_LOG"] = str(log_path)
    script = r"""
import os
paths = [
    "/etc/shadow",
    "/etc/hostname",
    os.path.expanduser("~/.ssh/id_rsa"),
    os.path.expanduser("~/.aws/credentials"),
    "/var/run/docker.sock",
    "/proc/self/environ",
    "/tmp/ordinary.txt",
    "/root/.netrc",
    "/etc/hermes/.env",
]
for path in paths:
    try:
        open(path, "rb").close()
    except OSError:
        pass
import socket
sock = socket.socket()
sock.settimeout(0.2)
try:
    sock.connect(("203.0.113.10", 80))
except OSError:
    pass
sock.close()
local = socket.socket()
local.settimeout(0.2)
try:
    local.connect(("127.0.0.1", 9))
except OSError:
    pass
local.close()
"""
    subprocess.run(["/home/agent/baze/backend/.venv/bin/python3", "-c", script], env=env, check=True)
    text = log_path.read_text()
    assert "/etc/shadow" in text
    assert "/.ssh/id_rsa" in text or ".ssh/id_rsa" in text
    assert "/.aws/credentials" in text
    assert "docker.sock" in text
    assert "/proc/self/environ" in text
    assert "/.netrc" in text
    assert "/etc/hostname" not in text
    assert "/etc/hermes/.env" not in text
    assert "/tmp/ordinary.txt" not in text
    assert "connect TCP 203.0.113.10 port 80" in text
    assert "127.0.0.1" not in text
    folder = tmp_path / "box"
    (folder / "specimen").mkdir(parents=True)
    (folder / "specimen" / "steal.py").write_text("print('x')\n")
    (folder / "specimen" / "note.txt").write_text("hello\n")
    (folder / "specimen" / "run.sh").write_text("true\n")
    assert program_commands(str(folder)) == [
        ["timeout", "8", "sh", "/specimen/run.sh"],
        ["timeout", "8", "python3", "/specimen/steal.py"],
    ]


def test_secret_paths_and_phone_homes_force_a_suspicious_verdict(tmp_path):
    cases = [
        (["TCP to 203.0.113.10 port 80."], ["/etc/shadow", "/home/hermes/.ssh/id_rsa"], True),
        ([], ["/home/hermes/.aws/credentials"], True),
        ([], ["/var/run/docker.sock"], True),
        ([], ["/proc/self/environ"], True),
        ([], ["/root/.netrc"], True),
        ([], ["/home/hermes/.gnupg/secring.gpg"], True),
        (["TCP to 203.0.113.11 port 443."], [], True),
        (["UDP to 108.61.10.10 port 53."], [], False),
        ([], [], False),
    ]
    verdict, _report = _review(None, _clear, "", [], [], ["TCP to 203.0.113.10 port 80."])
    assert verdict == "suspicious"
    for denies, touched, suspicious in cases:
        verdict, report = _review(None, _clear, "", denies, touched)
        assert verdict == ("suspicious" if suspicious else "clear"), (denies, touched, verdict)
        assert report == "Nothing stood out."

    root = tmp_path / "app"
    root.mkdir()
    (root / "access.log").write_text(
        "open /etc/shadow\nopen /etc/shadow\nopen /home/hermes/.ssh/id_rsa\n"
        "connect TCP 203.0.113.10 port 80\nnoise\n"
    )
    assert secret_touches(str(tmp_path)) == ["/etc/shadow", "/home/hermes/.ssh/id_rsa"]
    assert call_attempts(str(tmp_path)) == ["TCP to 203.0.113.10 port 80."]

    seen = []

    def infer(messages):
        seen.append(messages)
        return _clear(messages)

    verdict, _report = _review(
        None,
        infer,
        "BAZE-DENY TCP to 203.0.113.10 port 443.",
        ["TCP to 203.0.113.10 port 80."],
        ["/etc/shadow"],
    )
    assert verdict == "suspicious"
    assert "Secret paths opened:\n/etc/shadow" in seen[0][1]["content"]
    assert "TCP to 203.0.113.10 port 80." in seen[0][1]["content"]
    assert "likely intent" in seen[0][0]["content"]
    assert 'starts with "Details."' in seen[0][0]["content"]

    def unavailable(messages):
        raise RuntimeError("budget")

    verdict, report = _review(None, unavailable, "", [], ["/etc/shadow", "/opt/data/.ssh/id_rsa"], ["TCP to 203.0.113.10 port 80."])
    assert verdict == "suspicious"
    assert "password file" in report
    assert "private key" in report
    assert "203.0.113.10" in report
    verdict, report = plain_report([], [], [])
    assert verdict == "clear"
    assert "did not read a private file" in report
