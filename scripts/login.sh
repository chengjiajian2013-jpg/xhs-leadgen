#!/usr/bin/env bash
# 初始化登录小红书账号
# 使用方式: bash scripts/login.sh [profile名称]
# 默认使用 accounts.json 中的第一个账号

set -e

PROFILE="${1:-ucffv3fv}"

echo "========================================="
echo "  小红书登录助手"
echo "  使用 profile: $PROFILE"
echo "========================================="
echo ""
echo "即将打开小红书登录页面，请在浏览器中完成登录。"
echo "登录完成后等待自动检测..."
echo ""

opencli --profile "$PROFILE" xiaohongshu login --site-session persistent

echo ""
echo "登录状态检查:"
opencli --profile "$PROFILE" xiaohongshu whoami -f yaml
echo ""
echo "✅ 登录完成！"
