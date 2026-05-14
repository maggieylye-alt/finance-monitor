#!/usr/bin/env python3
"""
企微 Webhook 推送统一工具
解决 markdown 里 <font color="..."> 引号被截断的问题：
- 一律用 json.dumps 做安全序列化
- 一律用 requests.post(json=payload), 不要手拼 -d "..."
- 长内容自动分段, 单条≤4096字节(企微硬限)

用法:
    from wecom_push import push_markdown, push_template_card

    push_markdown("## 标题\\n<font color=\"warning\">+5%</font>")
    push_template_card({...})  # template_card payload
"""
import json
import sys
import urllib.request
import urllib.error

WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=ce9f8b0e-984a-4888-9f17-10935fcc6350"
MAX_BYTES = 4000  # 留点余量, 实际硬限4096

def _post(payload: dict) -> dict:
    """用 urllib 安全 POST, payload 用 json.dumps 序列化"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except urllib.error.HTTPError as e:
        return {"errcode": e.code, "errmsg": str(e)}
    except Exception as e:
        return {"errcode": -1, "errmsg": str(e)}


def push_markdown(content: str, mentioned_list=None) -> list:
    """
    推 markdown, 内容超过 4000 字节自动分段
    content 中可以放心使用 <font color="warning">+5%</font> 这种引号
    """
    encoded = content.encode("utf-8")
    if len(encoded) <= MAX_BYTES:
        chunks = [content]
    else:
        # 按行分段
        lines = content.split("\n")
        chunks = []
        cur = []
        cur_size = 0
        for line in lines:
            line_size = len(line.encode("utf-8")) + 1
            if cur_size + line_size > MAX_BYTES and cur:
                chunks.append("\n".join(cur))
                cur = [line]
                cur_size = line_size
            else:
                cur.append(line)
                cur_size += line_size
        if cur:
            chunks.append("\n".join(cur))

    results = []
    for i, chunk in enumerate(chunks):
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": chunk}
        }
        if mentioned_list and i == 0:
            payload["markdown"]["mentioned_list"] = mentioned_list
        results.append(_post(payload))
    return results


def push_template_card(card: dict) -> dict:
    """
    推 template_card
    card 是完整的 template_card 内容(不含外层 msgtype)
    """
    payload = {
        "msgtype": "template_card",
        "template_card": card,
    }
    return _post(payload)


def push_text(content: str, mentioned_list=None) -> dict:
    """简单文本"""
    payload = {"msgtype": "text", "text": {"content": content}}
    if mentioned_list:
        payload["text"]["mentioned_list"] = mentioned_list
    return _post(payload)


def fmt_color(value, mode="rise_red"):
    """
    返回 markdown 颜色字符串
    mode: rise_red(中国习惯, 涨红跌绿) | rise_green(美式, 涨绿跌红)
    """
    if isinstance(value, str):
        if value.startswith("+"):
            v = 1
        elif value.startswith("-"):
            v = -1
        else:
            v = 0
    else:
        v = float(value)
        v = 1 if v > 0 else (-1 if v < 0 else 0)

    if mode == "rise_red":
        if v > 0: return "warning"   # 橙红
        elif v < 0: return "info"    # 绿
        else: return "comment"       # 灰
    else:
        if v > 0: return "info"
        elif v < 0: return "warning"
        else: return "comment"


def fmt_money(amount: float, with_sign: bool = False) -> str:
    """
    格式化金额: 1234.56 -> ¥1,234
    with_sign=True: +¥1,234 / -¥1,234
    """
    a = abs(amount)
    if a >= 10000:
        s = f"¥{a/10000:.1f}万"
    elif a >= 1000:
        s = f"¥{a:,.0f}"
    else:
        s = f"¥{a:.0f}"

    if with_sign:
        if amount > 0: return "+" + s
        elif amount < 0: return "-" + s
    return s


# CLI 用法: python3 wecom_push.py markdown "## 标题\n内容"
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python3 wecom_push.py {markdown|text} <content>", file=sys.stderr)
        sys.exit(1)

    mode = sys.argv[1]
    content = sys.argv[2]

    if mode == "markdown":
        results = push_markdown(content)
        for r in results:
            print(json.dumps(r, ensure_ascii=False))
    elif mode == "text":
        r = push_text(content)
        print(json.dumps(r, ensure_ascii=False))
    elif mode == "template_card":
        # content 是 JSON string
        card = json.loads(content)
        r = push_template_card(card)
        print(json.dumps(r, ensure_ascii=False))
    else:
        print("不支持的 mode:", mode, file=sys.stderr)
        sys.exit(1)
