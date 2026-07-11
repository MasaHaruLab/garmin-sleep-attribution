#!/usr/bin/env python3
"""
One-time Garmin Connect login. RUN THIS YOURSELF in a real Terminal window —
it asks for your Garmin email + password, which Claude must never see or handle.

    # International (garmin.com):
    .venv/bin/python scripts/garmin_login.py
    # China (佳明 / connect.garmin.cn):
    .venv/bin/python scripts/garmin_login.py --cn

Your password is typed hidden (getpass) and is used only to fetch a login token,
which is saved to .garmin_tokens/ (gitignored, valid ~1 year). After this, the
puller reuses the token and you never log in again.
"""
import getpass
import sys
import traceback
from pathlib import Path

import garminconnect

ROOT = Path(__file__).resolve().parent.parent
TOKENSTORE = ROOT / ".garmin_tokens"
LOGFILE = ROOT / "data" / "last_login_result.txt"  # Claude reads this to diagnose


def log(msg: str) -> None:
    LOGFILE.parent.mkdir(parents=True, exist_ok=True)
    LOGFILE.write_text(msg, encoding="utf-8")


def main() -> int:
    # Account confirmed international via browser — default to garmin.com.
    is_cn = "--cn" in sys.argv
    region = "China (connect.garmin.cn)" if is_cn else "International (garmin.com)"
    print(f"Garmin login — {region}\n")
    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password (hidden while typing, this is normal): ")

    def prompt_mfa() -> str:
        print("\n📧 Garmin 正在给你的邮箱发验证码——**可能要等几分钟才到**,这个窗口会一直等你,别急。")
        print("   (Garmin is emailing you a one-time code; it can take several minutes.)")
        print("   码到了再输数字按回车;邮件没到之前不要按回车(空码=登录失败)。")
        return input("Verification code (6 digits) / 验证码: ").strip()

    garmin = garminconnect.Garmin(
        email=email, password=password, is_cn=is_cn, prompt_mfa=prompt_mfa
    )
    try:
        garmin.login()
    except Exception as e:  # noqa: BLE001 — surface + log the real cause
        log(f"FAIL region={'cn' if is_cn else 'intl'} "
            f"error={type(e).__name__}: {e}\n\n{traceback.format_exc()}")
        print(f"\n✗ Login failed: {type(e).__name__}: {e}")
        print(f"  Full error written to {LOGFILE} — paste it to your AI assistant to debug.")
        return 1

    TOKENSTORE.mkdir(parents=True, exist_ok=True)
    garmin.client.dump(str(TOKENSTORE))
    name = garmin.get_full_name() if hasattr(garmin, "get_full_name") else email
    log(f"OK region={'cn' if is_cn else 'intl'} user={name}")
    print(f"\n✓ Logged in: {name}. Token saved to {TOKENSTORE} (valid ~1 year).")
    print("  You never need to log in again — the puller reuses this token.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001 — every run must leave a trace in LOGFILE
        log(f"CRASH {type(e).__name__}: {e}\n\n{traceback.format_exc()}")
        print(f"\n✗ Exited early: {type(e).__name__}: {e}")
        print(f"  Details written to {LOGFILE}")
        raise SystemExit(1)
