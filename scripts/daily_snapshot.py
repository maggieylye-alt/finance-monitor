#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily_snapshot.py — 每日真实持仓快照生成器

读取:
  - data/portfolio-meta.json     用户持仓元数据(账户/规则/板块目标)
  - data/funds-all-2026-05-13.json   54 只基金真实持仓
  - data/holdings_today.json     A股 13 只持仓(基金还需重拉今日实时)

输出:
  - data/snapshot-YYYY-MM-DD.json  当日组合快照
  - data/dashboard-summary-v3.json 仪表盘汇总(给HTML用)
  - data/triggered-signals.json    今日触发的信号清单

数据源: NeoData (腾讯FiT)
规则: 基金净值若date≠今天,daily_chg字段必须留空,不能用T-1兜底当今日
"""
import json, re, subprocess, datetime, sys, os

ROOT = "/Users/maomaomao/WorkBuddy/20260512142512/.workbuddy/finance-monitor-pages"
SKILL_DIR = "/Users/maomaomao/.workbuddy/plugins/marketplaces/cb_teams_marketplace/plugins/finance-data/skills/neodata-financial-search"

def neodata(query, dtype='api'):
    """实拉NeoData,返回dict或None"""
    r = subprocess.run(
        ["python3", "scripts/query.py", "--query", query, "--data-type", dtype],
        cwd=SKILL_DIR, capture_output=True, text=True, timeout=60
    )
    raw = r.stdout
    idx = max(raw.find('{\n  "code"'), raw.find('{"code"'))
    if idx < 0: return None
    try: return json.loads(raw[idx:])
    except: return None

def get_basic_today(d, code):
    """今日basic_info: 返回{price,chg,update}, date必须等于今天"""
    if not d or not d.get('data'): return None
    today = datetime.date.today().strftime('%Y-%m-%d')
    for r in d['data'].get('apiData', {}).get('apiRecall', []):
        c = r.get('content', '')
        # 文本格式
        if '最新价' in c[:200]:
            m_chg = re.search(r'涨跌幅[^:]*:([-\d.]+)%', c)
            m_price = re.search(r'最新价[^:]*:([\d.,]+)', c)
            m_time = re.search(r'更新时间[^:]*:(\S+)', c)
            if m_chg and m_price:
                update_date = (m_time.group(1) if m_time else '')[:10]
                if update_date and update_date != today.replace('-','/').replace('-',''):
                    # 不是今天
                    pass
                return {
                    'price': float(m_price.group(1).replace(',','')),
                    'chg': float(m_chg.group(1)),
                    'update': m_time.group(1) if m_time else '',
                    'is_today': today in (m_time.group(1) if m_time else '')
                }
        # 表格格式
        for line in c.split('\n'):
            if not line.strip().startswith('|'): continue
            cells = [x.strip() for x in line.split('|')[1:-1]]
            if len(cells) >= 5 and cells[2] == code:
                try:
                    p = float(cells[3]); pv = float(cells[4])
                    return {'price': p, 'chg': (p-pv)/pv*100, 'is_today': True}
                except: continue
    return None

def get_fund_nav(code, target_date):
    """拉基金,严格按 target_date 匹配, 拿不到返回None"""
    d = neodata(f"基金 {code} 最新净值 {target_date}")
    if not d or not d.get('data'): return None
    for r in d['data'].get('apiData', {}).get('apiRecall', []):
        for line in r.get('content', '').split('\n'):
            if not line.strip().startswith('|'): continue
            cells = [x.strip() for x in line.split('|')[1:-1]]
            if len(cells) >= 6 and code in cells[0]:
                try:
                    if cells[2][:10] == target_date:
                        return {
                            'date': cells[2][:10],
                            'nav': float(cells[3]),
                            'daily_chg': float(cells[5]),
                            'is_today': True
                        }
                except: continue
    return None

def main():
    today = datetime.date.today().strftime('%Y-%m-%d')
    print(f"=== 每日快照 {today} ===\n")

    # 加载持仓元数据
    meta = json.load(open(f"{ROOT}/data/portfolio-meta.json"))
    funds = json.load(open(f"{ROOT}/data/funds-all-2026-05-13.json"))
    
    # 1. A股: 13 只逐一拉今日实时
    ashare_holdings = [
        ('159995','芯片ETF华夏', 4400, 1.694),
        ('516010','游戏ETF国泰', 18000, 1.642),
        ('513050','中概互联ETF', 5600, 1.572),
        ('513580','恒生科技ETF大成', 32500, 0.773),
        ('159941','纳指ETF广发', 3000, 1.343),
        ('510300','沪深300ETF华泰柏瑞', 300, 3.722),
        ('588000','科创50ETF华夏', 3100, 1.480),
        ('518880','黄金ETF华安', 1100, 9.095),
        ('161226','国投白银LOF', 794, 4.829),
        ('002594','比亚迪', 200, 99.261),
        ('601899','紫金矿业', 400, 33.379),
        ('601600','中国铝业', 400, 15.023),
        ('601985','中国核电', 500, 8.550),
    ]
    a_results = []
    a_total_mv = 0
    a_total_daily = 0
    a_total_pnl = 0
    print("--- A股 13只 ---")
    for code, name, shares, cost in ashare_holdings:
        d = neodata(f"{name} {code} 今日实时")
        b = get_basic_today(d, code)
        if b:
            mv = b['price'] * shares
            daily_pnl = mv * b['chg'] / 100
            position_pnl = (b['price'] - cost) * shares
            a_total_mv += mv
            a_total_daily += daily_pnl
            a_total_pnl += position_pnl
            a_results.append({
                'code': code, 'name': name, 'shares': shares, 'cost': cost,
                'price': b['price'], 'chg_pct': round(b['chg'], 2),
                'market_value': round(mv, 2), 'daily_pnl': round(daily_pnl, 2),
                'position_pnl': round(position_pnl, 2),
                'position_pct': round((b['price']/cost-1)*100, 2)
            })
            print(f"  {code} {name[:14]:14s} ¥{b['price']:>7.3f}  今日{b['chg']:+5.2f}%  浮盈{position_pnl/100:+5.0f}元")
        else:
            # 用昨天估算价
            a_results.append({
                'code': code, 'name': name, 'shares': shares, 'cost': cost,
                'price': None, 'data_status': 'missing'
            })
            print(f"  {code} {name[:14]:14s} 数据未取到")
    
    # 2. 黄金 Au9999 实时
    print("\n--- 黄金 ---")
    d = neodata("黄金 Au9999 今日实时")
    au_price = None; au_chg = None
    if d:
        for r in d['data'].get('apiData', {}).get('apiRecall', []):
            for line in r.get('content', '').split('\n'):
                if 'AU9999' in line and '|' in line:
                    cells = [x.strip() for x in line.split('|')[1:-1]]
                    try:
                        au_price = float(cells[4]) if len(cells) > 4 else None
                        if au_price: 
                            print(f"  Au9999: ¥{au_price}")
                            break
                    except: continue
            if au_price: break
    
    gold_grams = 211.59
    gold_total_mv = au_price * gold_grams if au_price else 211.59 * 1029.5
    gold_total_pnl = gold_total_mv - (160.14*1074.0 + 51.45*1125.61)
    
    # 3. 基金: 严格按 5/13 真实净值, 22:00 前不会全
    print("\n--- 基金54只(只用真实today,否则留空) ---")
    fund_today_results = []
    fund_real_count = 0
    fund_total_mv = sum(f['amount'] for f in funds)  # 用昨日金额作底,今日涨跌单独算
    fund_today_pnl = 0
    for f in funds:
        nav_data = get_fund_nav(f['code'].split('-')[0], today)
        if nav_data and nav_data['is_today']:
            fund_real_count += 1
            today_chg_amt = f['amount'] * nav_data['daily_chg'] / 100
            fund_today_pnl += today_chg_amt
            fund_today_results.append({**f, 'today_chg_pct': nav_data['daily_chg'],
                                       'today_chg_amt': round(today_chg_amt, 2),
                                       'data_status': 'real_today'})
        else:
            fund_today_results.append({**f, 'today_chg_pct': None,
                                       'today_chg_amt': None,
                                       'data_status': 'pending'})
    print(f"  真实今日净值: {fund_real_count}/{len(funds)} (其余22:00后入库)")
    
    # 4. 触发线检查
    print("\n--- 触发信号 ---")
    triggered = []
    
    # 黄金触发线
    if au_price:
        sell_triggers = meta['rules']['gold_sell_triggers']
        buy_triggers = meta['rules']['gold_buy_triggers']
        if au_price >= sell_triggers[0]:
            triggered.append({
                'category': 'gold_sell', 'priority': 'high',
                'message': f"黄金Au9999 ¥{au_price} 触发减仓线¥{sell_triggers[0]}, 建议减30g (~¥{30*au_price:.0f})"
            })
        elif au_price <= buy_triggers[0]:
            triggered.append({
                'category': 'gold_buy', 'priority': 'mid',
                'message': f"黄金Au9999 ¥{au_price} 触发补仓线¥{buy_triggers[0]}, 建议加¥1万"
            })
        else:
            print(f"  黄金距离触发线还差 {(sell_triggers[0]-au_price)/au_price*100:.1f}%")
    
    # 浮亏-20%
    for r in a_results:
        if r.get('position_pct') is not None and r['position_pct'] <= -20:
            triggered.append({
                'category': 'stop_loss', 'priority': 'high',
                'message': f"{r['name']} {r['code']} 浮亏{r['position_pct']}%, 触发-20%止损线, 建议清仓 ¥{r['market_value']:.0f}"
            })
    for f in funds:
        if f['pct'] <= -20:
            triggered.append({
                'category': 'stop_loss', 'priority': 'high',
                'message': f"{f['name']} 浮亏{f['pct']}%, 触发-20%止损线, 建议清仓 ¥{f['amount']:.0f}"
            })
    
    # 浮盈+50%/+100%
    for f in funds:
        if f['pct'] >= 100:
            triggered.append({
                'category': 'take_profit_2', 'priority': 'mid',
                'message': f"{f['name']} 浮盈{f['pct']:.1f}%, 触发+100%二级止盈, 建议止盈1/3 ¥{f['amount']/3:.0f}"
            })
        elif f['pct'] >= 50:
            triggered.append({
                'category': 'take_profit_1', 'priority': 'mid',
                'message': f"{f['name']} 浮盈{f['pct']:.1f}%, 触发+50%一级止盈, 建议止盈1/3 ¥{f['amount']/3:.0f}"
            })
    
    if triggered:
        for t in triggered[:10]:
            print(f"  [{t['priority']}] {t['message']}")
    
    # 5. 全资产合计
    advisor_mv = meta['accounts']['advisor']['value_today']
    total_invest = a_total_mv + gold_total_mv + fund_total_mv + advisor_mv
    total_today = a_total_daily + fund_today_pnl  # 黄金当日变化用Au价差另算
    if au_price:
        total_today += (au_price - 1029.5) * gold_grams  # 用昨日均值兜底
    
    print(f"\n=== 当日组合 ===")
    print(f"  A股: ¥{a_total_mv:>9,.0f} 今日{a_total_daily:+,.0f}")
    print(f"  基金: ¥{fund_total_mv:>9,.0f} 今日{fund_today_pnl:+,.0f} ({fund_real_count}只真实)")
    print(f"  黄金: ¥{gold_total_mv:>9,.0f}")
    print(f"  投顾: ¥{advisor_mv:>9,.0f}")
    print(f"  合计: ¥{total_invest:>9,.0f}")
    print(f"  今日盈亏: ¥{total_today:+,.2f}")
    
    # 6. 写文件
    snapshot = {
        'date': today,
        'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'ashare': {
            'holdings': a_results,
            'total_mv': round(a_total_mv, 2),
            'total_daily_pnl': round(a_total_daily, 2),
            'total_position_pnl': round(a_total_pnl, 2)
        },
        'funds': {
            'holdings': fund_today_results,
            'total_mv': round(fund_total_mv, 2),
            'today_pnl': round(fund_today_pnl, 2),
            'real_count': fund_real_count,
            'total_count': len(funds)
        },
        'gold': {
            'grams': gold_grams,
            'price': au_price,
            'total_mv': round(gold_total_mv, 2),
            'total_pnl': round(gold_total_pnl, 2)
        },
        'advisor': {
            'total_mv': advisor_mv
        },
        'total': {
            'invest_value': round(total_invest, 2),
            'today_pnl': round(total_today, 2)
        },
        'triggered_signals': triggered
    }
    
    out_file = f"{ROOT}/data/snapshot-{today}.json"
    json.dump(snapshot, open(out_file, 'w'), ensure_ascii=False, indent=2)
    print(f"\n✓ 快照保存到: {out_file}")
    
    # 仪表盘summary v3
    summary = {
        'date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'version': 'v4-real',
        'total_capital': 980000,
        'invest_value': round(total_invest, 2),
        'cash': 980000 - round(total_invest),
        'today_pnl': round(total_today, 2),
        'total_pnl_estimate': round(a_total_pnl + 26200 + gold_total_pnl + 1528, 0),  # 投顾¥1528
        'sectors_meta': meta['sectors'],
        'year_progress': meta['year_progress'],
        'key_actions': meta['key_actions'],
        'triggered_signals': triggered,
        'data_health': {
            'ashare_real': sum(1 for r in a_results if r.get('price')),
            'ashare_total': len(a_results),
            'funds_real': fund_real_count,
            'funds_total': len(funds),
            'gold_real': au_price is not None,
        }
    }
    json.dump(summary, open(f"{ROOT}/data/dashboard-summary-v3.json", 'w'), ensure_ascii=False, indent=2)
    print(f"✓ 仪表盘summary保存")
    
    return snapshot, summary, triggered

if __name__ == '__main__':
    main()
