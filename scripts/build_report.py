#!/usr/bin/env python3
"""Inject an analysis JSON into the HTML template -> a standalone report.

Usage:
    build_report.py <analysis.json> [output.html]

The analysis JSON is produced by Claude after interpreting scan.py output.
Schema (system and source_scan required for verified cleanup buttons):
All tier items may also carry findings:[{name,path,size,content,decision}],
evidence (string), impact (string), recovery (string), process_status (string).
Residual cards additionally support ownership_evidence/install_state/last_activity/active_dependency/shared_dependency/decision_reason (strings), user_decision (keep|remove|undecided), cleanup_blockers (nonempty list disables cleanup for this path and overlaps).
Object-first presentation: object_decisions [{name,parent,path,size,space_label,category(clean|review|pending|keep),kind?,recommendation,reason,tradeoff,next_step,evidence,member_paths?,parts?}], object_observed_at. These read-only presentation objects never authorize cleanup; actions remain green/yellow allowlists. object_exclusions records measured objects not promoted and their reasons.
These fields are visible in the report; findings are evidence, not extra totals.

{
  "source_scan": {"path": "/absolute/scan.json", "sha256": "...", "scan_id": "..."},
  "generated_at": "2026-05-28 12:00:00",
  "scan_seconds": 42.1,
  "system": {os, build, arch, user, home, filesystem,
             disk_total, disk_used, disk_free, purgeable},
  "top5": [{rank, tier(green|yellow|red), size, type, name, path, note}],
  "green":  [{name, path, size_estimate, kill_processes:[], trash_paths:[...], commands:[{label,cmd}]}],
  "yellow": [{name, path, size, content_profile, why_manual, disposal, risk, trash_paths:[...]?, open_note?}],
  "red":    [{name, path, size, why_keep, indirect_release, auto_reclaim, app_paths:[...]?}],
  "denied": ["/path/one", ...],
  "summary": {overview, tier_stats:{green,yellow,red}, priority:[...], long_term:[...]}
}
"""
import json
import os
import sys
import hashlib
import time
import copy

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "report_template.html")


def prepare_report(data):
    """Bind report to a scan snapshot; never present it as a live inventory."""
    data = copy.deepcopy(data)
    errors = []
    source = data.get("source_scan", {})
    valid = True
    try:
        with open(source["path"], "rb") as f:
            raw = f.read()
        scan = json.loads(raw)
        if hashlib.sha256(raw).hexdigest() != source["sha256"] or scan["scan_id"] != source["scan_id"]:
            raise ValueError("扫描快照与分析不匹配")
        for key in ("system", "generated_at", "scan_seconds"):
            if key not in scan or data.get(key) != scan[key]:
                raise ValueError("分析与扫描元数据不一致：" + key)
        age = time.time() - scan["finished_at_epoch"]
        if age > 86400 or age < -300:
            raise ValueError("扫描已超过24小时或时间异常")
    except (OSError, ValueError, KeyError, TypeError) as e:
        valid = False
        errors.append("分析来源未验证、不一致或已过期，清理按钮及命令已禁用：" + str(e))
    if not valid:
        for tier in ("green", "yellow"):
            for item in data.get(tier, []):
                item.pop("trash_paths", None)
                item.pop("commands", None)
    # Keep decisions and unresolved core/shared dependencies must never leak into
    # service allowlists, including when a parent path contains a protected child.
    protected = []
    for tier in ("green", "yellow", "red"):
        for item in data.get(tier, []):
            if item.get("user_decision") == "keep" or item.get("cleanup_blockers"):
                if item.get("path"):
                    protected.append(os.path.realpath(item["path"]))
                item["cleanup_guard_note"] = "本轮保留或依赖未核清；不提供清理操作。"
                item.pop("trash_paths", None)
                item.pop("commands", None)
    for tier in ("green", "yellow"):
        for item in data.get(tier, []):
            allowed = []
            blocked = False
            for path in item.get("trash_paths", []):
                rp = os.path.realpath(path)
                if any(rp == q or rp.startswith(q + os.sep) or q.startswith(rp + os.sep) for q in protected):
                    blocked = True
                else:
                    allowed.append(path)
            if blocked:
                item["trash_paths"] = allowed
                item.pop("commands", None)
                item["cleanup_guard_note"] = "已排除与本轮保留/待核依赖重叠的路径；旧命令不再提供。"
    data["report_validation"] = {"status": "snapshot_verified" if valid else "invalid", "errors": errors,
                                 "note": "仅校验报告与扫描快照的对应关系；不是实时文件系统一致性或删除安全性证明。"}
    data.setdefault("summary", {}).setdefault("priority", []).insert(
        0, "扫描快照：" + str(data.get("generated_at", "未知")) +
        "。这是扫描时点的分析，不是当前实时状态；任何清理、安装或数据变化后须重新扫描并重建建议。")
    return data


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser(
        "~/Desktop/storage-report.html")

    with open(src, "r", encoding="utf-8") as f:
        data = prepare_report(json.load(f))
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        tpl = f.read()

    blob = json.dumps(data, ensure_ascii=False)
    # 静态报告不带删除能力（DELETE=null），删除按钮只在 server.py 服务时出现
    html = tpl.replace("__REPORT_DATA__", blob).replace("__DELETE_CONFIG__", "null")

    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"报告已生成: {out}")
    print(f"打开: open '{out}'")


if __name__ == "__main__":
    main()
