#!/bin/bash
# 双击即可:在真终端里登录 Garmin(密码只在这个窗口里输,AI 不经手)。
cd "$(dirname "$0")/.."
.venv/bin/python scripts/garmin_login.py
echo
read -p "看完上面的结果后,按回车关闭这个窗口..." _
