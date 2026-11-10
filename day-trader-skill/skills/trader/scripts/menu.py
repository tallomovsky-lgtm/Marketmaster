#!/usr/bin/env python3
"""/trader: the menu of the day-trader-skill pack.

  python3 menu.py
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradelib as T  # noqa: E402

SKILLS = [
    ("/trader-scanner", "סורק גרפים", "סורק את המניות הכי פעילות בארה״ב ומוצא פריצות, גאפים, מומנטום ומכירת יתר.",
     "/trader-scanner תמצא לי פריצות"),
    ("/trader-timemachine", "מכונת הזמן", "10,000 סימולציות של המחיר: מה הסיכוי שהעסקה תגיע ליעד לפני הסטופ.",
     "/trader-timemachine TSLA כניסה 364 יעד 370 סטופ 358"),
    ("/trader-pelosi", "מעקב קונגרס", "מה קנו ומכרו חברי הקונגרס, כמה זמן לקח להם לדווח, ואיך המניות זזו מאז.",
     "/trader-pelosi מה פלוסי קנתה לאחרונה?"),
    ("/trader-premarket", "לפני הפעמון", "סקירת בוקר: חוזים, VIX, אג״ח, דולר, נפט, גאפים ברשימת המעקב ואירועי היום.",
     "/trader-premarket"),
    ("/trader-news", "חדשות שוק", "כותרות על המניות שלך עם תרגום, תקציר בעברית וסימון חיובי/שלילי.",
     "/trader-news NVDA TSLA"),
    ("/trader-levels", "רמות מפתח", "תמיכות, התנגדויות, פיבוטים, VWAP, פרה-מרקט וממוצעים נעים על גרף נרות.",
     "/trader-levels AMD"),
    ("/trader-risk", "מחשבון פוזיציה", "כמה מניות לקנות כדי שהסטופ יעלה בדיוק כמה שתכננת, כולל יחס סיכוי/סיכון.",
     "/trader-risk חשבון 25 אלף, סיכון 1%, TSLA"),
    ("/trader-earnings", "דוחות", "איך המניה הגיבה לדוחות הקודמים, התנועה הטיפוסית, ולוח הדוחות של השבוע.",
     "/trader-earnings NVDA"),
    ("/trader-heatmap", "מפת חום", "לאן הכסף זורם היום: סקטורים, מדדים ומפת המניות הגדולות לפי שווי.",
     "/trader-heatmap"),
    ("/trader-journal", "יומן מסחר", "רושם עסקאות ומראה אחוז הצלחה, עקומת הון ואיזה סטאפ באמת עובד לך.",
     "/trader-journal סגרתי TSLA 50 מניות 364 → 370"),
    ("/trader", "התפריט הזה", "כל הסקילים במקום אחד. אפשר גם פשוט לכתוב מה אתה רוצה בעברית.",
     "/trader"),
]


def example(ex):
    cmd, _, rest = ex.partition(" ")
    return T.ltr(T.esc(cmd)) + (" " + T.esc(rest) if rest else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args()
    terminal = T.receipt("טרמינל מסחר מקצועי", "מנוי שנתי · משתמש אחד",
                         [("נתונים בזמן אמת", None), ("סורק מניות", None), ("חדשות שוק", None)],
                         "סה״כ לשנה, בערך", "$30,000", he_title=True)
    ours = T.receipt("day-trader-skill", f"{len(SKILLS)} סקילים · קוד פתוח",
                     [("סורק, סימולציות, קונגרס, רמות", None), ("חדשות, דוחות, מפת חום, יומן", None),
                      ("עובד בעברית, בתוך Claude", None)],
                     "סה״כ", '<span style="color:var(--orange)">0 ₪</span>',
                     extra='<div style="text-align:left;margin-top:-58px;padding-left:6px"><span class="stamp">חינם</span></div>')
    cards = "".join(
        f'<div class="sheet" style="margin:0;display:flex;flex-direction:column;gap:8px">'
        f'<div class="row" style="justify-content:space-between"><b style="font-size:20px">{t}</b><span class="pill" style="font-size:14px;padding:5px 13px 6px">{c}</span></div>'
        f'<div style="font-size:14.5px;line-height:1.6;color:#333">{d}</div>'
        f'<div style="font-size:13px;color:var(--muted);margin-top:auto">לדוגמה: <span style="color:var(--ink);font-weight:700">{example(ex)}</span></div></div>'
        for c, t, d, ex in SKILLS)
    head = ('<div class="headline">טרמינל של סוחר יומי, <span class="o">בחינם</span></div>'
            f'<div class="grid g2" style="align-items:start">{terminal}{ours}</div>')
    body = head + f'<h2 style="margin:8px 0 14px">{len(SKILLS)} הסקילים</h2><div class="grid g2">{cards}</div>'
    T.save(T.page("day-trader-skill", body, "/trader", "כל הכלים של סוחר יומי, בתוך Claude, בעברית"), "trader-menu", a.out)


if __name__ == "__main__":
    main()
