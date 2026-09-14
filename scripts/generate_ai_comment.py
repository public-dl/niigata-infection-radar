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

SCHEMA_VERSION = 2

REQUIRED_FIELDS = [
    "headline",
    "summary",
    "trend",
    "regional",
    "age_group",
    "year_on_year",
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
    },
    "required": REQUIRED_FIELDS,
    "additionalProperties": False,
}

SYSTEM_INSTRUCTIONS = """
あなたは「インフルエンザレーダー（新潟県）」の週次データ分析担当です。
入力される新潟県のインフルエンザ公表データだけを根拠に、
一般向けの短い日本語コメントを作成してください。

厳守事項:
- 入力データにない事実を作らない。
- 原因推測をしない。
- 医療診断、受診勧奨、薬の推奨など個別の医療助言をしない。
- 「注意報」「警報」が実際に発令されたと断定しない。
- 10 人/定点、30 人/定点は「従来の注意報基準相当」「従来の警報基準相当」と表現する。
- 1 人/定点は「流行期入りの目安」と表現する。
- 定点当たり報告数には原則として毎回「 人/定点」を付ける。
- 数値と単位の間には半角スペースを1つ入れ、半角スラッシュの「人/定点」を使う。
- 前週からの変化は割合（％）ではなく、人/定点の絶対差で表現する。
- 前年同週がある場合は、今年との違いを簡潔に示す。
- 地域差は上位地域を中心に、数値を伴って説明する。
- 年代別データがある場合は必ず「age_group」で触れる。
- 年代別分析は age_per_sentinel（人/定点）を主指標とし、age_counts（実数）は必要な場合だけ補足する。
- 年代別では、最新週の特徴だけでなく直近の推移も確認し、増加が目立つ年代を簡潔に述べる。
- 年代間の因果関係を断定しない。「子どもから大人へ感染した」などの表現は禁止。
- 時間差が見えても「先行して増加する傾向がみられる」「今後の推移を注視」といった慎重な表現にする。
- 過剰に不安をあおらない。
- 文章はニュース・行政資料のように簡潔で落ち着いた文体にする。
- 出力はJSONオブジェクトのみ。Markdownやコードフェンスは禁止。

出力JSON:
{
  "headline": "20〜35文字程度の見出し",
  "summary": "全県の最新値と前週からの動きを1〜2文",
  "trend": "直近の推移を1〜2文",
  "regional": "地域別の特徴を1〜2文",
  "age_group": "年代別の特徴を1〜2文。年代別データがある場合は必ず具体的な年代と人/定点を含める",
  "year_on_year": "前年同週との比較を1〜2文。比較不能ならその旨を簡潔に"
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
        {"region": k, "value": num(v)}
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
    return {k: obj[k].strip() for k in REQUIRED_FIELDS}


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
                max_output_tokens=2000,
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
