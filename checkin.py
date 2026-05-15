import os
import json
import time
import random
import requests
from pypushdeer import PushDeer

# ---------- 配置 ----------
CHECKIN_URL = "https://glados.cloud/api/user/checkin"
STATUS_URL = "https://glados.cloud/api/user/status"
POINTS_URL = "https://glados.cloud/api/user/points"

HEADERS = {
    "origin": "https://glados.cloud",
    "referer": "https://glados.cloud/console/checkin",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "content-type": "application/json;charset=UTF-8",
}

PAYLOAD = {"token": "glados.cloud"}
TIMEOUT = 10


# ---------- 推送 ----------
def push_deer(key, title, text):
    """推送到 PushDeer"""
    if not key:
        return
    try:
        PushDeer(pushkey=key).send_text(title, desp=text)
    except Exception as e:
        print(f"PushDeer 推送异常: {e}")


def push_serverchan(key, title, content):
    """推送到 Server酱 (Turbo 版)"""
    if not key:
        return
    try:
        r = requests.post(
            f"https://sctapi.ftqq.com/{key}.send",
            data={"title": title, "desp": content},
            timeout=TIMEOUT,
        )
        if r.ok and r.json().get("code") == 0:
            print("Server酱推送成功")
        else:
            print(f"Server酱推送失败: {r.text}")
    except Exception as e:
        print(f"Server酱推送异常: {e}")


def push_all(deer_key, sc_key, title, content):
    """推送到所有已配置的服务"""
    if not deer_key and not sc_key:
        print("未配置推送服务，请在 Secrets 中设置 SENDKEY 或 SERVERCHAN_KEY")
        return
    if deer_key:
        push_deer(deer_key, title, content)
    if sc_key:
        push_serverchan(sc_key, title, content)


# ---------- 工具 ----------
def safe_json(resp):
    """安全解析 JSON"""
    try:
        return resp.json()
    except Exception:
        return {}


def classify_checkin(code, message):
    """
    判断签到结果: 优先根据 code 字段，兜底用 message 关键词。
    GLaDOS API 返回: code=0 成功, code=1 重复, 其他失败。
    """
    if code == 0:
        return "ok"
    if code == 1:
        return "repeat"
    # 兜底：部分旧接口或域名可能只返回 message
    msg = message.lower()
    if "got" in msg:
        return "ok"
    if any(kw in msg for kw in ("repeat", "already", "重复", "已签到", "签到过", "请勿")):
        return "repeat"
    return "fail"


# ---------- 主流程 ----------
def main():
    deer_key = os.getenv("SENDKEY", "")
    sc_key = os.getenv("SERVERCHAN_KEY", "")
    cookies = [c.strip() for c in os.getenv("COOKIES", "").split("&") if c.strip()]

    if not cookies:
        push_all(deer_key, sc_key, "GLaDOS 签到", "未检测到 COOKIES")
        return

    session = requests.Session()
    ok = fail = repeat = 0
    lines = []

    for idx, cookie in enumerate(cookies, 1):
        headers = {**HEADERS, "cookie": cookie}
        email, days, total_points = "unknown", "-", "-"

        try:
            # 1. 签到
            r = session.post(
                CHECKIN_URL,
                headers=headers,
                data=json.dumps(PAYLOAD),
                timeout=TIMEOUT,
            )
            j = safe_json(r)
            code = j.get("code", -2)
            message = j.get("message", "")
            earned = j.get("points", 0)

            result = classify_checkin(code, message)
            if result == "ok":
                ok += 1
                status = f"✅ 成功 (+{earned}积分)"
            elif result == "repeat":
                repeat += 1
                status = "🔄 已签到"
            else:
                fail += 1
                status = f"❌ 失败({message})"

            # 2. 查询账号状态 (剩余天数、邮箱)
            s = session.get(STATUS_URL, headers=headers, timeout=TIMEOUT)
            data = safe_json(s).get("data") or {}
            email = data.get("email", email)
            if data.get("leftDays") is not None:
                days = f"{int(float(data['leftDays']))} 天"

            # 3. 查询总积分
            p = session.get(POINTS_URL, headers=headers, timeout=TIMEOUT)
            pj = safe_json(p)
            if pj.get("points") is not None:
                total_points = f"{int(float(pj['points']))} 积分"

        except Exception as e:
            fail += 1
            status = f"❌ 异常({e})"

        lines.append(f"{idx}. {email} | {status} | 总积分:{total_points} | 剩余:{days}")

        if idx < len(cookies):
            time.sleep(random.uniform(1, 2))

    title = f"GLaDOS 签到完成 ✅{ok} ❌{fail} 🔄{repeat}"
    content = "\n".join(lines)
    print(content)
    push_all(deer_key, sc_key, title, content)


if __name__ == "__main__":
    main()
