#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "data" / "influenza_history.json"
OUTPUT_PATH = ROOT / "data" / "ai_comment.json"

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
FORCE = os.getenv("FORCE_AI_COMMENT", "").lower() in {"1", "true", "yes"}

SCHEMA_VERSION = 7

REGION_DISPLAY_NAMES = {"新潟市": "新潟"}

REQUIRED_FIELDS = [
    "headline",
    "summary",
    "trend",
    "regional",
    "age_group",
    "year_on_year",
    "kids_headline",
    "kids_summary",
    "kids_trend",
    "kids_regional",
    "kids_age_group",
    "kids_year_on_year",
]


AI_COMMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "trend": {"type": "string"},
        "regional": {"type": "string"},
        "age_group": {"type": "string"},
        "year_on_year": {"type": "string"},
        "kids_headline": {"type": "string"},
        "kids_summary": {"type": "string"},
        "kids_trend": {"type": "string"},
        "kids_regional": {"type": "string"},
        "kids_age_group": {"type": "string"},
        "kids_year_on_year": {"type": "string"},
        "emphasis": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "audience": {"type": "string", "enum": ["general", "kids"]},
                    "field": {
                        "type": "string",
                        "enum": ["headline", "summary", "trend", "regional", "age_group", "year_on_year"],
                    },
                    "style": {"type": "string", "enum": ["marker", "underline"]},
                    "text": {"type": "string"},
                },
                "required": ["audience", "field", "style", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": [*REQUIRED_FIELDS, "emphasis"],
    "additionalProperties": False,
}

SYSTEM_INSTRUCTIONS = """
あなたは「インフルエンザレーダー（新潟県）」の週次データ分析担当です。
入力される新潟県のインフルエンザ公表データだけを根拠に、
一般向けコメントと、小学生向けコメントをそれぞれ独立して作成してください。

【共通の厳守事項】
- 入力データにない事実を作らない。
- 原因推測をしない。
- 医療診断、受診勧奨、薬の推奨など個別の医療助言をしない。
- 「注意報」「警報」が実際に発令されたと断定しない。
- 過剰に不安をあおらない。
- 年代間の因果関係を断定しない。「子どもから大人へ感染した」などの表現は禁止。
- 数値や地域名などの事実関係を一般向けとこども向けで変えない。
- 出力はJSONオブジェクトのみ。Markdownやコードフェンスは禁止。

【一般向けコメント】
- ニュース・行政資料のように簡潔で落ち着いた文体にする。
- 10 人/定点、30 人/定点は「従来の注意報基準相当」「従来の警報基準相当」と表現する。
- 1 人/定点は「流行期入りの目安」と表現する。
- 定点当たり報告数には原則として「 人/定点」を付ける。
- 数値と単位の間には半角スペースを1つ入れ、半角スラッシュの「人/定点」を使う。
- 前週からの変化は割合（％）ではなく、人/定点の絶対差で表現する。
- 前年同週がある場合は、今年との違いを簡潔に示す。
- 地域差は上位地域を中心に、数値を伴って説明する。
- 年代別データがある場合は必ず「age_group」で触れる。
- 年代別分析は age_per_sentinel（人/定点）を主指標とし、age_counts（実数）は必要な場合だけ補足する。
- 年代別では最新週だけでなく直近の推移も確認し、増加が目立つ年代を簡潔に述べる。
- 時間差が見えても「先行して増加する傾向がみられる」「今後の推移を注視」など慎重に表現する。

【こども向けコメント：最重要】
こども向けは、一般向けコメントの言葉を少しやさしくした文章ではありません。
小学校4～6年生が、先生や保護者の説明がなくても、
「いま新潟県でインフルエンザがどうなっているのか」を読んで分かるように、
一般向けとは別の文章として一から組み立ててください。

文章の作り方:
- 小学生にやさしく話しかけるような、自然で親しみやすい日本語にする。
- 行政資料・ニュース原稿のような硬い言い回しを避ける。
- まず「何が起きているか」を伝え、そのあと必要な数字を示す。
- 一文は短めにする。1項目は原則1～2文。
- 数字を並べすぎない。意味を伝えるために必要な数字だけ使う。
- 「人/定点」を何度も繰り返さない。こども向け全体で原則1回までにする。
- 「定点」という語を使う必要がある場合は、最初に「1つの医療機関（いりょうきかん）から報告（ほうこく）された人数」のように意味を説明する。
- 「前年同期」「絶対差」「流行期入りの目安」「従来の注意報基準相当」などの行政・統計用語を、そのまま使わない。
- 「去年の同じころ」「前の週より増えた」「いま増えている」のような日常語に置き換える。
- 小学校4～6年生には読みづらそうな漢字に（ ）で読みがなを付ける。ただし、読みがなだらけにしない。
- 地域名には必ず読みがなを付ける。
  新潟（にいがた）、新発田（しばた）、新津（にいつ）、三条（さんじょう）、長岡（ながおか）、
  魚沼（うおぬま）、南魚沼（みなみうおぬま）、十日町（とおかまち）、柏崎（かしわざき）、
  糸魚川（いといがわ）、村上（むらかみ）、佐渡（さど）、上越（じょうえつ）。
- 地域コメントは上位の地域名を2～3か所示すことを優先し、各地域の細かな数値は原則書かない。
- 年代コメントは「5～9歳」など具体的な年代を示すが、人/定点の細かな数値は原則書かない。
- 去年との比較では、差分値を計算して並べず、「去年の同じころよりかなり多い」「去年はまだ少なかった」など意味を伝える。
- 見出しは、こどもが内容を一目で分かる短い表現にし、絵文字を1つ付ける。
- 怖がらせる表現、命令口調、必要以上に不安をあおる表現は使わない。
- 予防や行動のアドバイスは生成しない。サイト側で「😷 じぶんでできること」を固定表示するため、内容を重複させない。

こども向けで避ける文章の例:
- 「9月7日〜13日は9.44 人/定点でした。前の週より3.31 人/定点増え、1 人/定点の流行期入りの目安を上回っています。」
- 「地域では糸魚川が21.5 人/定点で最も高く、村上15.5 人/定点、新潟13.06 人/定点が続きました。」
- 「去年の同じ週は0.09 人/定点で、今年は9.44 人/定点でした。今年のほうが9.35 人/定点高くなっています。」
これらは数字と専門表現が多く、一般向け文章に近すぎるため、こども向けでは使わないでください。

目指すこども向けの例（数字は入力データに合わせて変えること）:
- kids_headline: 「🤒 インフルエンザが3週つづけて増えています」
- kids_summary: 「新潟県（にいがたけん）では、インフルエンザにかかった人の報告（ほうこく）が3週つづけて増えています。今週は、1つの医療機関（いりょうきかん）から平均（へいきん）で9.44人の報告がありました。」
- kids_trend: 「3週間前は3.58人、その次の週は6.13人、今週は9.44人でした。少しずつではなく、はっきり増えてきています。」
- kids_regional: 「今週は、糸魚川（いといがわ）・村上（むらかみ）・新潟（にいがた）などで多くなっています。住んでいる地域（ちいき）によって、流行（りゅうこう）のようすにはちがいがあります。」
- kids_age_group: 「いちばん多いのは5～9歳です。10～14歳や1～4歳の子どもたちでも多く報告されています。」
- kids_year_on_year: 「去年の同じころは、インフルエンザの報告はまだとても少ない時期でした。今年は去年より早い時期から増えています。」

【強調表示 metadata】
本文とは別に emphasis 配列を作ってください。サイト側で黄色マーカーと朱書き下線として表示します。
- audience は general または kids。
- field は headline / summary / trend / regional / age_group / year_on_year のいずれか。
- style="marker" は「数字・傾向など、ひと目で拾ってほしい核心情報」に使う。
- style="underline" は「流行水準への接近・基準超え・前年との大きな違いなど、意味として注意してほしい一文や短い句」に使う。
- text は、対応する本文中に実際に存在する文字列を一字一句そのまま抜き出す。言い換え・省略・記号変更は禁止。
- 1項目につき強調は原則0～2か所。全文を強調しない。
- marker と underline を同じ文字列に重ねない。
- 一般向けは全体で6～10か所程度、こども向けは全体で4～7か所程度を目安にする。
- 重要な情報がない箇所では無理に強調しない。

強調の例:
- headline の「3週連続で増加」→ marker
- summary の「9.44 人/定点」→ marker
- summary の「1 人/定点の流行期入りの目安を上回っています」→ underline
- regional の「糸魚川が21.5 人/定点」→ marker
- kids_headline 相当の field=headline では「3週つづけて増えています」→ marker

【こども向け出力前の自己チェック】
JSONを返す前に、kids_* の5本文と見出しを頭の中で確認してください。
- 一般向け文章をほぼコピーしていないか。
- 「人/定点」を何度も使っていないか。
- 細かな差分値や地域別数値を並べていないか。
- 地域名に読みがなが付いているか。
- 小学校4～6年生が一人で読んで意味をつかめるか。
1つでも満たさなければ、kids_* だけを書き直してからJSONを出力してください。

出力JSON:
{
  "headline": "20〜35文字程度の一般向け見出し",
  "summary": "全県の最新値と前週からの動きを1〜2文",
  "trend": "直近の推移を1〜2文",
  "regional": "地域別の特徴を1〜2文",
  "age_group": "年代別の特徴を1〜2文。年代別データがある場合は必ず具体的な年代と人/定点を含める",
  "year_on_year": "前年同週との比較を1〜2文。比較不能ならその旨を簡潔に",
  "kids_headline": "絵文字1つから始める、小学校4～6年生向けの短い見出し",
  "kids_summary": "『いまのようす』として、まず意味を伝え、必要な数字だけ使う1～2文",
  "kids_trend": "『増えているの？』に答える、やさしく短い1～2文。必要なら直近3週の数字を使う",
  "kids_regional": "『どこで多い？』に答える、読みがな付きの地域名を使った短い1～2文。地域別の細かな数値は原則書かない",
  "kids_age_group": "『どの年代で多い？』に答える、具体的な年代を使った短い1～2文。細かな人/定点は原則書かない",
  "kids_year_on_year": "『去年とくらべると？』に答える、意味優先の短い1～2文。差分値は原則書かない",
  "emphasis": [
    {"audience": "general", "field": "headline", "style": "marker", "text": "本文中の重要な短い文字列"},
    {"audience": "general", "field": "summary", "style": "underline", "text": "本文中の注意してほしい短い文字列"},
    {"audience": "kids", "field": "headline", "style": "marker", "text": "こども向け本文中の重要な短い文字列"}
  ]
}
""".strip()


def num(v):
    if v is None:
        return None
    return round(float(v), 2)


def load_history():
    if not HISTORY_PATH.exists():
        raise FileNotFoundError(f"{HISTORY_PATH} が見つかりません。")
    data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    weeks = sorted(
        data.get("weeks", []),
        key=lambda w: (int(w["year"]), int(w["week"]))
    )
    if not weeks:
        raise ValueError("weeks が空です。")
    return weeks


def build_payload(weeks):
    latest = weeks[-1]
    prev = weeks[-2] if len(weeks) >= 2 else None
    prev2 = weeks[-3] if len(weeks) >= 3 else None

    latest_value = num(latest.get("prefecture"))
    prev_value = num(prev.get("prefecture")) if prev else None
    week_diff = None
    if latest_value is not None and prev_value is not None:
        week_diff = round(latest_value - prev_value, 2)

    same_week_last_year = next(
        (
            w for w in weeks
            if int(w["year"]) == int(latest["year"]) - 1
            and int(w["week"]) == int(latest["week"])
        ),
        None,
    )

    regions = [
        {"region": REGION_DISPLAY_NAMES.get(k, k), "value": num(v)}
        for k, v in (latest.get("regions") or {}).items()
    ]
    regions.sort(key=lambda x: x["value"] if x["value"] is not None else -1, reverse=True)

    recent = [
        {
            "year": int(w["year"]),
            "week": int(w["week"]),
            "label": w.get("label", ""),
            "prefecture": num(w.get("prefecture")),
        }
        for w in weeks[-13:]
    ]

    age_groups = ["0歳","1～4歳","5～9歳","10～14歳","15～19歳","20～59歳","60歳以上"]

    latest_age = {
        g: {
            "per_sentinel": num((latest.get("age_per_sentinel") or {}).get(g)),
            "count": num((latest.get("age_counts") or {}).get(g)),
        }
        for g in age_groups
    }

    recent_age = [
        {
            "year": int(w["year"]),
            "week": int(w["week"]),
            "label": w.get("label", ""),
            "age_per_sentinel": {
                g: num((w.get("age_per_sentinel") or {}).get(g))
                for g in age_groups
            },
            "age_counts": {
                g: num((w.get("age_counts") or {}).get(g))
                for g in age_groups
            },
        }
        for w in weeks[-8:]
    ]

    payload = {
        "latest": {
            "year": int(latest["year"]),
            "week": int(latest["week"]),
            "label": latest.get("label", ""),
            "prefecture": latest_value,
        },
        "previous_week": None if not prev else {
            "year": int(prev["year"]),
            "week": int(prev["week"]),
            "label": prev.get("label", ""),
            "prefecture": prev_value,
        },
        "two_weeks_ago": None if not prev2 else {
            "year": int(prev2["year"]),
            "week": int(prev2["week"]),
            "label": prev2.get("label", ""),
            "prefecture": num(prev2.get("prefecture")),
        },
        "week_over_week_difference_per_sentinel": week_diff,
        "same_week_last_year": None if not same_week_last_year else {
            "year": int(same_week_last_year["year"]),
            "week": int(same_week_last_year["week"]),
            "label": same_week_last_year.get("label", ""),
            "prefecture": num(same_week_last_year.get("prefecture")),
        },
        "regions_ranked": regions,
        "recent_13_weeks": recent,
        "age_groups_latest": latest_age,
        "age_groups_recent_8_weeks": recent_age,
        "reference_levels": {
            "epidemic_entry_guide": 1,
            "legacy_advisory_equivalent": 10,
            "legacy_warning_equivalent": 30,
        },
    }
    return latest, payload


def same_source_week(existing, latest):
    try:
        src = existing.get("source_week", {})
        return (
            int(existing.get("schema_version", 0)) == SCHEMA_VERSION
            and int(src.get("year")) == int(latest["year"])
            and int(src.get("week")) == int(latest["week"])
        )
    except Exception:
        return False


def parse_json_object(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("API応答からJSONオブジェクトを検出できません。")
    obj = json.loads(text[start:end + 1])
    for key in REQUIRED_FIELDS:
        if not isinstance(obj.get(key), str) or not obj[key].strip():
            raise ValueError(f"必須フィールド {key} がありません。")

    result = {k: obj[k].strip() for k in REQUIRED_FIELDS}
    emphasis = obj.get("emphasis") or []
    valid_emphasis = []
    for item in emphasis:
        if not isinstance(item, dict):
            continue
        audience = item.get("audience")
        field = item.get("field")
        style = item.get("style")
        text = item.get("text")
        if audience not in {"general", "kids"}:
            continue
        if field not in {"headline", "summary", "trend", "regional", "age_group", "year_on_year"}:
            continue
        if style not in {"marker", "underline"}:
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        source_key = f"kids_{field}" if audience == "kids" else field
        clean_text = text.strip()
        if clean_text not in result[source_key]:
            continue
        valid_emphasis.append({
            "audience": audience,
            "field": field,
            "style": style,
            "text": clean_text,
        })
    result["emphasis"] = valid_emphasis
    return result


def generate_comment(payload):
    client = OpenAI()
    user_input = (
        "以下のJSONデータだけを根拠に、指定形式の週次分析コメントを作成してください。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )

    last_error = None
    for attempt in range(2):
        extra = ""
        if attempt == 1:
            extra = "\n前回の生成に失敗しました。短く簡潔に、指定されたJSONスキーマに従って出力してください。"

        try:
            response = client.responses.create(
                model=MODEL,
                reasoning={"effort": "low"},
                instructions=SYSTEM_INSTRUCTIONS + extra,
                input=user_input,
                max_output_tokens=2400,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "weekly_influenza_insight",
                        "schema": AI_COMMENT_SCHEMA,
                        "strict": True,
                    }
                },
            )

            raw = (getattr(response, "output_text", None) or "").strip()

            if not raw:
                # GitHub Actions 上で原因を追えるよう、空応答時だけ診断情報を残す
                status = getattr(response, "status", None)
                incomplete = getattr(response, "incomplete_details", None)
                raise ValueError(
                    f"API応答本文が空です。status={status}, incomplete_details={incomplete}"
                )

            return parse_json_object(raw)

        except Exception as exc:
            last_error = exc
            print(
                f"WARN: AIコメント生成 attempt {attempt + 1}/2 失敗: {exc}",
                file=sys.stderr,
            )

    raise RuntimeError(f"AIコメント生成に失敗しました: {last_error}")


def main():
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY が設定されていません。", file=sys.stderr)
        sys.exit(2)

    weeks = load_history()
    latest, payload = build_payload(weeks)

    if OUTPUT_PATH.exists() and not FORCE:
        try:
            existing = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            if same_source_week(existing, latest):
                print(
                    f"SKIP: {latest['year']} 第{latest['week']}週のAIコメントは既にあります。"
                )
                return
        except Exception:
            pass

    generated = generate_comment(payload)

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "source_week": {
            "year": int(latest["year"]),
            "week": int(latest["week"]),
            "label": latest.get("label", ""),
            "prefecture": num(latest.get("prefecture")),
        },
        **generated,
        "disclaimer": "新潟県公表データをもとにAIが自動生成した分析コメントです。実際の注意報・警報の発令を示すものではありません。",
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"OK: data/ai_comment.json を更新しました "
        f"({latest['year']} 第{latest['week']}週 / {MODEL})"
    )


if __name__ == "__main__":
    main()
