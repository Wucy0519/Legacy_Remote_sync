#!/usr/bin/env python3
"""Code-only SSH mirrors. Local Python >=3.9; remote POSIX sh + rsync >=2.6.9."""
import argparse
import glob
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile

META = ".remote-sync"
DEFAULT_EXCLUDES = Path(__file__).with_name("default-excludes.txt")


class SyncError(Exception):
    pass


def run(argv, capture=False):
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE if capture else None)
    if result.returncode:
        raise SyncError("命令失败（退出码 %s）：%s" % (result.returncode, shlex.join(argv)))
    return result.stdout.strip() if capture else None


def save_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def aliases(config):
    """Resolve Include files for discovery; OpenSSH remains authoritative for connection."""
    found, visited = set(), set()

    def read(path):
        path = Path(path).expanduser().resolve()
        if path in visited or not path.is_file():
            return
        visited.add(path)
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = shlex.split(line, comments=True)
            if not parts:
                continue
            # Both 'Host name' and 'Host=name' are valid SSH config syntax.
            if "=" in parts[0]:
                key, value = parts[0].split("=", 1)
                parts = [key, value] + parts[1:]
            key, values = parts[0].lower(), parts[1:]
            if values and values[0] == "=":
                values = values[1:]
            if key == "host":
                found.update(v for v in values if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", v))
            elif key == "include":
                for value in values:
                    value = os.path.expanduser(value)
                    if not os.path.isabs(value):
                        value = str(Path(config).expanduser().parent / value)
                    for included in glob.glob(value):
                        read(included)

    read(config)
    return sorted(found)


def ssh_args(cfg):
    args = ["ssh", "-o", "ConnectTimeout=15"]
    if cfg.get("ssh_config"):
        args += ["-F", cfg["ssh_config"]]
    return args


def remote_command(cfg, script):
    return run(ssh_args(cfg) + [cfg["host"], "sh -c " + shlex.quote(script)], capture=True)


def check_remote(cfg):
    root = shlex.quote(cfg["remote_path"])
    # 'pwd -P' resolves the selected project root; rsync operands use this canonical root.
    output = remote_command(cfg, "set -e; command -v rsync >/dev/null; cd " + root + "; pwd -P")
    lines = output.splitlines()
    if not lines or not lines[-1].startswith("/") or lines[-1] == "/":
        raise SyncError("远程项目必须是存在的非根目录；请检查 SSH 登录提示和项目路径。")
    canonical = lines[-1]
    if cfg.get("canonical_path") and canonical != cfg["canonical_path"]:
        raise SyncError("远程项目的实际路径发生变化，请重新建立映射。")
    return canonical


def remote_operand(cfg):
    return cfg["host"] + ":" + shlex.quote(cfg["canonical_path"] + "/")


def rsync_args(cfg, root):
    # No -l/-L: do not transfer or dereference symlinks. Never use --delete.
    return ["rsync", "-rtp", "--checksum", "--itemize-changes",
            "--exclude=" + META + "/", "--exclude-from=" + str(root / META / "exclude.txt"),
            "--max-size=" + str(cfg["max_size_bytes"]), "-e", shlex.join(ssh_args(cfg))]


def manifest(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        result[path.relative_to(directory).as_posix()] = {
            "sha256": digest.hexdigest(), "mode": stat.S_IMODE(path.stat().st_mode)}
    return result


def snapshot(cfg, root, destination, remote=False):
    source = remote_operand(cfg) if remote else str(root) + "/"
    run(rsync_args(cfg, root) + ["--", source, str(destination) + "/"])
    return manifest(destination)


def load(root):
    meta = root / META
    if not (meta / "config.json").is_file():
        raise SyncError("此目录还没有映射，请先运行 init。")
    cfg = json.loads((meta / "config.json").read_text(encoding="utf-8"))
    state = json.loads((meta / "baseline.json").read_text(encoding="utf-8"))
    if cfg["local_path"] != str(root):
        raise SyncError("本地映射目录已移动；请使用原目录，或在新空目录重新 init。")
    return cfg, state


class Lock:
    def __init__(self, root):
        self.path = root / META / "lock"

    def __enter__(self):
        try:
            self.path.mkdir()
        except FileExistsError:
            raise SyncError("有同步操作正在运行；若上次异常退出，确认进程已停止后移除 .remote-sync/lock。")

    def __exit__(self, *args):
        self.path.rmdir()


def changed(current, baseline):
    return sorted(p for p in current if current[p] != baseline.get(p))


def safe_local_target(root, relative):
    path = root / relative
    for parent in [path] + list(path.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise SyncError("本地目标含符号链接，不能覆盖：" + relative)
    if path.exists() and not path.is_file():
        raise SyncError("本地目标不是普通文件：" + relative)
    return path


def guard_remote_targets(cfg, paths):
    checks = ["set -e", "cd " + shlex.quote(cfg["canonical_path"])]
    for name in paths:
        parts = PurePosixPath(name).parts
        for i in range(1, len(parts) + 1):
            target = shlex.quote("./" + "/".join(parts[:i]))
            checks.append("if [ -L " + target + " ]; then printf '%s\\n' '符号链接阻止上传'; exit 43; fi")
            if i < len(parts):
                checks.append("if [ -e " + target + " ] && [ ! -d " + target + " ]; then exit 44; fi")
            else:
                checks.append("if [ -e " + target + " ] && [ ! -f " + target + " ]; then exit 44; fi")
    # Chunk callers to stay below OS command length limits.
    remote_command(cfg, "; ".join(checks))


def report(current, baseline):
    edits = changed(current, baseline)
    removed = sorted(set(baseline) - set(current))
    for path in edits:
        print(("修改 " if path in baseline else "新增 ") + path)
    for path in removed:
        print("本地缺失/已排除（不会删除远程） " + path)
    if not edits and not removed:
        print("没有待同步的本地代码变更。")
    return edits


def init(args):
    root = Path(args.local).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise SyncError("首次同步请选择空目录，避免覆盖已有项目。")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", args.host):
        raise SyncError("请使用 SSH 配置中的 Host 别名，不要使用 user@host 或命令选项。")
    if not args.remote.startswith("/") or any(c in args.remote for c in "\r\n\0"):
        raise SyncError("请填写远程项目的绝对路径，例如 /home/user/project。")
    if args.max_size_mib <= 0:
        raise SyncError("文件大小上限必须大于 0。")
    cfg = {"host": args.host, "remote_path": args.remote, "local_path": str(root),
           "ssh_config": str(Path(args.ssh_config).expanduser().resolve()) if args.ssh_config else None,
           "max_size_bytes": int(args.max_size_mib * 1024 * 1024)}
    cfg["canonical_path"] = check_remote(cfg)
    root.mkdir(parents=True, exist_ok=True)
    meta = root / META
    meta.mkdir()
    shutil.copyfile(DEFAULT_EXCLUDES, meta / "exclude.txt")
    save_json(meta / "config.json", cfg)
    save_json(meta / "baseline.json", {"established": False, "files": {}})
    print("已建立映射：%s:%s → %s" % (cfg["host"], cfg["canonical_path"], root))
    print("下一步运行 pull 下载代码。排除规则：" + str(meta / "exclude.txt"))


def sync(args):
    root = Path(args.local).expanduser().resolve()
    cfg, state = load(root)
    with Lock(root), tempfile.TemporaryDirectory(prefix="remote-sync-") as temporary:
        # Load state only while holding the lock.
        cfg, state = load(root)
        work = Path(temporary)
        local = work / "local"
        local.mkdir()
        current = snapshot(cfg, root, local)
        baseline = state["files"]
        if args.command == "status":
            report(current, baseline)
            return
        if args.command == "pull":
            if current != baseline:
                report(current, baseline)
                raise SyncError("本地有修改、缺失文件或排除规则变化；先上传/保存修改，再拉取，避免覆盖。")
        elif not state["established"]:
            raise SyncError("必须先成功 pull，再修改和 push。")
        check_remote(cfg)
        remote = work / "remote"
        remote.mkdir()
        remote_files = snapshot(cfg, root, remote, remote=True)
        if args.command == "pull":
            removed = sorted(set(baseline) - set(remote_files))
            if removed:
                print("远程缺失/已排除，本地将保留：" + ", ".join(removed))
                raise SyncError("拉取暂停：请手动处理这些本地文件或恢复排除规则后重试。")
            for name in remote_files:
                safe_local_target(root, name)
            if manifest(local) != current:
                raise SyncError("本地快照发生变化，请重试。")
            # Check the live tree immediately before copying; snapshots never overwrite edits silently.
            verify_local = work / "verify-local"
            verify_local.mkdir()
            if snapshot(cfg, root, verify_local) != current:
                raise SyncError("拉取期间本地文件发生变化，请重试。")
            run(rsync_args(cfg, root) + ["--", str(remote) + "/", str(root) + "/"])
            save_json(root / META / "baseline.json", {"established": True, "files": remote_files})
            print("已下载 %s 个代码文件。请在 Cursor 打开：%s" % (len(remote_files), root))
            return
        edits = report(current, baseline)
        if not edits:
            return
        conflicts = [p for p in edits if remote_files.get(p) != baseline.get(p)
                     and remote_files.get(p) != current[p]]
        if conflicts:
            raise SyncError("服务器文件已改变或消失，停止上传；先合并：\n" + "\n".join(conflicts))
        for offset in range(0, len(edits), 40):
            guard_remote_targets(cfg, edits[offset:offset + 40])
        paths = work / "files"
        paths.write_bytes(b"".join(p.encode("utf-8") + b"\0" for p in edits))
        command = rsync_args(cfg, root) + ["--from0", "--files-from=" + str(paths)]
        if not args.apply:
            command += ["--dry-run"]
        run(command + ["--", str(local) + "/", remote_operand(cfg)])
        if not args.apply:
            print("预览完成；上述变更尚未上传。执行 push --apply 才会上传。")
            return
        verified = work / "verified"
        verified.mkdir()
        verified_files = snapshot(cfg, root, verified, remote=True)
        bad = [p for p in edits if verified_files.get(p) != current[p]]
        if bad:
            raise SyncError("上传后的文件核对失败，基线未更新；检查后重试：\n" + "\n".join(bad))
        # Update only the uploaded entries: remote-only edits still require a later pull.
        baseline.update({p: current[p] for p in edits})
        save_json(root / META / "baseline.json", {"established": True, "files": baseline})
        print("已上传并核对 %s 个代码文件；远程未执行删除。" % len(edits))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    hosts = commands.add_parser("hosts", help="列出 SSH 配置中的连接别名")
    hosts.add_argument("--ssh-config", default=str(Path.home() / ".ssh/config"))
    create = commands.add_parser("init", help="在空目录建立映射，不下载代码")
    create.add_argument("--host", default="my-sever")
    create.add_argument("--remote", required=True)
    create.add_argument("--local", required=True)
    create.add_argument("--ssh-config")
    create.add_argument("--max-size-mib", type=float, default=20)
    for name in ("pull", "status", "push"):
        command = commands.add_parser(name)
        command.add_argument("--local", required=True)
        if name == "push":
            command.add_argument("--apply", action="store_true", help="实际上传；默认仅预览")
    args = parser.parse_args()
    try:
        if args.command == "hosts":
            names = aliases(args.ssh_config)
            print("\n".join(names) if names else "未发现具体 Host 别名；默认候选为 my-sever，请向用户确认。")
        else:
            if not all(shutil.which(name) for name in ("ssh", "rsync")):
                raise SyncError("本地需要 ssh 和 rsync。")
            if args.command == "init":
                init(args)
            else:
                sync(args)
    except (SyncError, OSError, ValueError) as error:
        print("错误：" + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
