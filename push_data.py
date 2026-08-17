#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push_data.py — 将本地文件用 GitHub API 安全推送到云端 main 分支
=====================================================================
用法:
  python3 push_data.py briefing.json logistics.json ...        # 推 data/ 下文件
  python3 push_data.py daily-reading/2026-08-08.html          # 推仓库根相对路径文件
  python3 push_data.py --pull briefing.json ...               # 从云端拉取覆盖本地

路径规则:
  - 纯文件名（不含 /）→ 仓库内 data/<name>，本地 data/<name>（兼容旧调用）
  - 含目录（如 daily-reading/x.html）→ 仓库根相对路径，本地同路径

为什么需要它：
  内容类自动化（晨间速报/持仓复盘/精读/简报）在本地生成内容后，
  必须直接推送到云端（GitHub Pages 数据源），否则页面看不到新内容。
  它只更新指定的文件，绝不触碰其他文件 —— 不会像旧 deploy.sh 那样
  用本地旧文件覆盖云端新数据。
"""
import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
REPO = "imsuperraymond/pilot-dashboard"
BRANCH = "main"


def get_token():
    """从 deploy.sh 中读取 GitHub Token（唯一落盘位置）。"""
    deploy = os.path.join(SCRIPT_DIR, "deploy.sh")
    with open(deploy, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"ghp_[A-Za-z0-9]+", text)
    if not m:
        m = re.search(r"github_pat_[A-Za-z0-9_]+", text)
    if not m:
        raise RuntimeError("deploy.sh 中未找到 GitHub Token")
    return m.group(0)


def repo_path(name):
    """仓库内相对路径：纯文件名 → data/<name>；含 / → 原样（仓库根相对）。"""
    if os.path.isabs(name) or "/" in name:
        return name
    return "data/" + name


def local_path(name):
    """本地绝对路径：绝对路径原样；纯文件名 → data/<name>；含目录 → 项目根/<name>。"""
    if os.path.isabs(name):
        return name
    if "/" in name:
        return os.path.join(SCRIPT_DIR, name)
    return os.path.join(DATA_DIR, name)


def api(url, method="GET", body=None, token=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "pilot-push",
    }
    if token:
        headers["Authorization"] = "token " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def push_file(name, token, rp_override=None):
    path = local_path(name)
    if not os.path.exists(path):
        print("  [跳过] 文件不存在:", path)
        return False
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    rp = rp_override or repo_path(name)
    # 获取当前 sha（用于安全更新，防止覆盖他人新提交）
    url = "https://api.github.com/repos/%s/contents/%s?ref=%s" % (REPO, urllib.parse.quote(rp, safe="/"), BRANCH)
    code, meta = api(url, token=token)
    sha = meta.get("sha", "")
    body = {
        "message": "Content update %s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
        "content": b64,
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha
    code2, meta2 = api(url, method="PUT", body=body, token=token)
    if code2 in (200, 201):
        print("  ✓ 已推送", rp, "->", REPO)
        return True
    else:
        print("  ✗ 推送失败", rp, "HTTP", code2, meta2.get("message", ""))
        return False


def pull_file(name, token, rp_override=None):
    """从云端拉取最新版本覆盖本地（保证修改基于最新数据，不回退数字）。"""
    path = local_path(name)
    rp = rp_override or repo_path(name)
    url = "https://api.github.com/repos/%s/contents/%s?ref=%s" % (REPO, urllib.parse.quote(rp, safe="/"), BRANCH)
    code, meta = api(url, token=token)
    if code != 200:
        print("  ✗ 拉取失败", rp, "HTTP", code, meta.get("message", ""))
        return False
    content = base64.b64decode(meta["content"])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)
    print("  ✓ 已拉取云端最新", rp, "-> 本地")
    return True


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    token = get_token()
    ok = True
    pull = args[0] == "--pull"
    if pull:
        args = args[1:]
    root = args and args[0] == "--root"  # --root 后面文件按仓库根路径处理
    if root:
        args = args[1:]
    for name in args:
        if root:
            rp = name.lstrip("/")  # 仓库根相对路径
            arg = rp if "/" in rp else "./" + rp  # 保证 local_path 解析到项目根
            if pull:
                ok = pull_file(arg, token, rp_override=rp) and ok
            else:
                ok = push_file(arg, token, rp_override=rp) and ok
        elif pull:
            ok = pull_file(name, token) and ok
        else:
            ok = push_file(name, token) and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
