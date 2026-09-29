"""Process-level fake for the Word supervisor tests."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil


def _word(folder: Path, name: str) -> dict[str, float | int]:
    launcher = (
        "import json,subprocess,sys,time,psutil; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)',"
        "'/Automation'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL); "
        "open(sys.argv[1],'w',encoding='utf-8').write(json.dumps({'pid':p.pid,'create_time':"
        "psutil.Process(p.pid).create_time()}))"
    )
    subprocess.run([sys.executable, "-c", launcher, str(folder / name)], check=True, timeout=5)
    identity = json.loads((folder / name).read_text(encoding="utf-8"))
    process = psutil.Process(identity["pid"])
    deadline = time.monotonic() + 10
    while True:
        if process.name() == psutil.Process().name() and "/Automation" in process.cmdline():
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("fake Word did not become identifiable")
        time.sleep(0.01)
    with (folder.parent / ".word_pids").open("a", encoding="utf-8") as handle:
        handle.write(f"{identity['pid']}\n")
    return identity


def main() -> int:  # noqa: C901
    request = Path(sys.argv[1])
    folder = request.parent
    data = json.loads(request.read_text(encoding="utf-8"))
    mode = os.environ.get("EMA_FAKE_WORD_MODE", "ok")
    if mode == "hang_once":
        marker = folder.parent / ".hang_once"
        if marker.exists():
            mode = "ok"
        else:
            marker.touch()
            mode = "hang"
    if mode in {"hang_launch", "hang_launch_two"}:
        (folder / "launch.json").write_text(
            json.dumps({"before": [], "started_at": time.time() - 0.1}), encoding="utf-8"
        )
        _word(folder, "dummy.json")
        if mode == "hang_launch_two":
            _word(folder, "dummy2.json")
        (folder / "ready").write_text("ready", encoding="utf-8")
        time.sleep(60)
    if mode in {"hang", "crash_word"}:
        (folder / "word.json").write_text(json.dumps(_word(folder, "dummy.json")), encoding="utf-8")
    if mode == "hang":
        time.sleep(60)
    if mode in {"crash", "crash_word"}:
        print("fake crash marker", flush=True)
        return 7
    if mode == "fail":
        (folder / "result.json").write_text(
            json.dumps({"ok": False, "code": "word_launch", "detail": "fake failure"}),
            encoding="utf-8",
        )
        return 1
    output = data["output"]
    if data["action"] == "toc":
        (folder / data["input"]).write_bytes(b"updated toc")
    elif output is not None and mode != "missing":
        (folder / output).write_bytes(
            "text with accent".encode("utf-16") if data["action"] == "text" else b"result"
        )
    (folder / "result.json").write_text(json.dumps({"ok": True, "tables": 2}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
