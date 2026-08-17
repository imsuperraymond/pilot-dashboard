#!/bin/bash
# Raymond 全球物流工作台 - GitHub Pages 部署脚本 v2（安全版）
# =====================================================================
# 重要变更说明（2026-08-17）：
#   旧版脚本会把【本地 data/ 文件】复制覆盖到远程仓库再 push。
#   这导致：本地 data/ 一旦是旧版（如 8/14），就会把云端刚更新的
#   8/16/8/17 数据【回退】成旧版 —— 这是数据"不更新"的根因！
#
#   新版原则：
#   1. data/*.json 是【云端唯一权威】，一律从云端拉取，绝不反向推送。
#      （数据由 GitHub Actions 每天自动更新：行情/汇率/新闻/日期）
#   2. 本脚本只负责推送【静态文件】：index.html / sw.js / manifest /
#      icons / scripts / workflow —— 这些才需要从本地部署。
#   3. 推送前先 git pull --rebase，避免覆盖任何云端新提交。
# =====================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="/tmp/pilot-deploy"

# GitHub Token 从 ~/.workbuddy/gh_token 读取（不硬编码，避免 secret 泄露/被拒推）
TOKEN=""
if [ -f "$HOME/.workbuddy/gh_token" ]; then
  TOKEN=$(cat "$HOME/.workbuddy/gh_token")
fi
if [ -z "$TOKEN" ]; then
  echo "✗ 未找到 GitHub Token：请写入 ~/.workbuddy/gh_token"
  exit 1
fi
REPO_URL="https://x-access-token:${TOKEN}@github.com/imsuperraymond/pilot-dashboard.git"

echo "=== Raymond 工作台部署 v2（data/ 只拉不推）==="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"

# 1. 清理旧目录，克隆远程仓库
rm -rf "$DEPLOY_DIR"
git clone "$REPO_URL" "$DEPLOY_DIR" --depth=3 2>/dev/null || git clone "$REPO_URL" "$DEPLOY_DIR"
echo "✓ 仓库克隆完成"

# 2. 把云端最新 data/ 同步到【本地】（本地永远不落后于云端）
echo "→ 同步云端最新 data/ 到本地（防止本地旧数据）..."
mkdir -p "$SCRIPT_DIR/data"
for f in briefing logistics portfolio cognition; do
  if [ -f "$DEPLOY_DIR/data/$f.json" ]; then
    cp "$DEPLOY_DIR/data/$f.json" "$SCRIPT_DIR/data/$f.json"
    echo "  $f.json 已从云端同步到本地"
  fi
done

# 3. 只复制静态文件（绝不复制 data/ 到远程！）
cp "$SCRIPT_DIR/index.html" "$DEPLOY_DIR/"
cp "$SCRIPT_DIR/manifest.json" "$DEPLOY_DIR/"
cp "$SCRIPT_DIR/sw.js" "$DEPLOY_DIR/"
cp "$SCRIPT_DIR/icon.svg" "$DEPLOY_DIR/"
cp "$SCRIPT_DIR"/icon-*.png "$DEPLOY_DIR/" 2>/dev/null || true
mkdir -p "$DEPLOY_DIR/scripts" "$DEPLOY_DIR/.github/workflows"
cp "$SCRIPT_DIR/scripts/update_dashboard.py" "$DEPLOY_DIR/scripts/" 2>/dev/null || true
cp "$SCRIPT_DIR/.github/workflows/daily-update.yml" "$DEPLOY_DIR/.github/workflows/" 2>/dev/null || true
# 内容类静态文件：每日精读 + 海运简报（同样只推不覆盖 data/）
if [ -d "$SCRIPT_DIR/daily-reading" ]; then
  cp -r "$SCRIPT_DIR/daily-reading" "$DEPLOY_DIR/"
  echo "✓ daily-reading/ 已复制（精读内容）"
fi
cp "$SCRIPT_DIR"/海运简报_*.html "$DEPLOY_DIR/" 2>/dev/null && echo "✓ 海运简报已复制" || true
echo "✓ 静态文件复制完成（data/ 未复制，保持云端权威）"

# 4. 提交并推送（先 rebase 远程最新，避免覆盖云端新提交）
cd "$DEPLOY_DIR"
git add -A
git diff --cached --quiet && echo "无静态文件变更，跳过提交" && exit 0
git commit -m "Static update $(date '+%Y-%m-%d %H:%M')"
git pull --rebase origin main 2>&1 || echo "(rebase 跳过，继续推送)"
git push origin main 2>&1

echo ""
echo "✓ 部署完成 → https://imsuperraymond.github.io/pilot-dashboard/"
echo "  data/ 已保持云端最新版本（本地同步）"
