#!/usr/bin/env python3
"""Emby 批量加演员 / 类型 / 标签 / 工作室。

只用 Python 自带库（urllib），不用装 requests，也不用 pip。
Debian 12/13 默认会拦系统级 pip（PEP 668 externally-managed-environment），
这个版本直接绕过这个问题。

与插件页同一逻辑：GET 全量 -> 合并字段 -> POST /Items/{Id}。
POST 不是增量更新：只发部分字段会把没发的字段清空，所以必须全量回写，
且 ProviderIds 为空时也要发 {}，否则 400。

字段格式（BaseItemDto）：
  演员 People: [{"Name": "…", "Type": "Actor", "Role": "…"}]，锁定名 Cast
  类型 Genres: ["动作", "剧情"]（字符串数组），锁定名 Genres
  标签 Tags:   ["4K", "收藏"]（字符串数组），锁定名 Tags
  工作室 Studios: [{"Name": "…"}]（NameLongIdPair[]，只发 Name，让服务端
    按名字关联/新建；不要把 GET /Studios 返回的 GUID 当 Id 发，那是 Item Id，
    不是 NameLongIdPair 的 long Id），锁定名 Studios
  注意：LockedFields 里没有 "People"，发 People 会被静默丢弃（2026-11-11 已踩过）。
  年份 ProductionYear（int）+ 上映日 PremiereDate（ISO 8601）：
    只发 "2006" 会被静默丢弃，必须发完整日期；只给 --year 时脚本同时写
    ProductionYear=YYYY 和 PremiereDate=YYYY-01-01T00:00:00.0000000Z。
    给了 --premiere-date（YYYY-MM-DD）则以它为准，年份从它取。
    注意：LockedFields 里没有 ProductionYear / PremiereDate，年份锁不住；
    认不出的片没有刮削数据可覆盖，一般能留住，但刷新后如有新数据可能被改。

用法（Python 3.8+，零依赖）：
  export EMBY_URL="http://10.10.10.4:8096"
  export EMBY_API_KEY="你的 API Key"   # 控制台 > 高级 > API Keys 新建，别发到聊天里
  # 只加演员（老用法不变）
  python3 batch_add_actors.py --search SHKD --actors "小凑四叶" --dry-run
  # 一次加演员 + 类型 + 标签 + 工作室
  python3 batch_add_actors.py --search SHKD --actors "小凑四叶" \
      --genres "剧情,爱情" --tags "LTX,破解" --studios "S1" --dry-run
  python3 batch_add_actors.py --search SHKD --actors "小凑四叶" \
      --genres "剧情" --tags "LTX" --studios "S1" --limit 1 --yes
  # 只加标签 / 只加工作室也行，不填的字段不动
  python3 batch_add_actors.py --search SHKD --tags "收藏" --yes
  # 替换模式（只替换填了的字段，没填的字段不动；演员只删旧演员，导演等不动）
  python3 batch_add_actors.py --search SHKD --genres "剧情" --mode replace --yes
  # 只补锁定，不改内容；不给字段时锁 Cast+Genres+Tags+Studios 四个，给了字段只锁给的
  python3 batch_add_actors.py --search SHKD --lock-only --yes
  python3 batch_add_actors.py --search SHKD --genres "剧情" --lock-only --yes
actors.txt：每行一个演员，可写 名字|角色，如：小凑四叶|主演
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# 字段 -> LockedFields 枚举值（年份没有对应的锁定名，故不在此表）
LOCK_NAMES = {"actors": "Cast", "genres": "Genres", "tags": "Tags", "studios": "Studios"}

def resolve_year(year, premiere_date):
    """返回 (year:int, premiere_iso:str) 或 None。只给年份时日期取该年 1 月 1 日。"""
    from datetime import date
    if premiere_date:
        try:
            d = date.fromisoformat(premiere_date.strip()[:10])
        except ValueError:
            sys.exit(f"--premiere-date 格式不对：{premiere_date}，请用 YYYY-MM-DD，如 2024-05-01")
        if year is not None and year != d.year:
            sys.exit(f"--year {year} 与 --premiere-date {premiere_date} 的年份不一致")
        return (d.year, d.strftime("%Y-%m-%dT00:00:00.0000000Z"))
    if year is not None:
        if not (1900 <= year <= 2100):
            sys.exit(f"--year 超出范围：{year}")
        return (year, f"{year}-01-01T00:00:00.0000000Z")
    return None

def parse_list(value, file_path=None):
    raw = []
    if value:
        raw += [s.strip() for s in value.replace("，", ",").split(",") if s.strip()]
    if file_path:
        with open(file_path, encoding="utf-8") as f:
            raw += [line.strip() for line in f if line.strip()]
    out, seen = [], set()
    for name in raw:
        # 也接受换行 / 、分隔
        for part in name.replace("、", ",").replace("\n", ",").split(","):
            part = part.strip()
            if part and part.lower() not in seen:
                seen.add(part.lower())
                out.append(part)
    return out

def parse_actors(args):
    names = parse_list(args.actors, args.actors_file)
    out = []
    for raw in names:
        parts = raw.split("|", 1)
        name, role = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")
        if not name:
            continue
        person = {"Name": name, "Type": "Actor"}
        if role:
            person["Role"] = role
        out.append(person)
    return out

def merge_strings(old, new, mode):
    old = list(old or [])
    if mode == "replace":
        return list(new)
    have = {s.lower() for s in old}
    return old + [s for s in new if s.lower() not in have]

def merge_named(old, new, mode):
    """old/new 是 [{Name, ...}]，按 Name 去重；旧条目原样保留（含服务端给的 Id）。"""
    old = list(old or [])
    if mode == "replace":
        return list(new)
    have = {(d.get("Name") or "").lower() for d in old}
    return old + [d for d in new if (d.get("Name") or "").lower() not in have]

def names_of(item, list_key, items_key):
    """字符串数组与 *Items 并集去重保序。
    Emby 读回时 Tags 常为 None，真实值在 TagItems 里；Genres 同理防一手。"""
    out, seen = [], set()
    for n in (item.get(list_key) or []):
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    for d in (item.get(items_key) or []):
        n = d.get("Name")
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out

class Emby:
    def __init__(self, url, key):
        self.url = url.rstrip("/")
        self.key = key
        self.user_id = None
        self._person_cache = {}

    def _request(self, method, path, params=None, body=None):
        url = self.url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("X-Emby-Token", self.key)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"HTTP {e.code} {method} {path}：{detail}") from e

    def get(self, path, **params):
        return self._request("GET", path, params=params)

    def post(self, path, body):
        return self._request("POST", path, body=body)

    def admin_user_id(self):
        users = self.get("/Users")
        for u in users:
            if u.get("Policy", {}).get("IsAdministrator"):
                return u["Id"]
        return users[0]["Id"]

    def list_movies(self, search=None, limit=None):
        params = {"IncludeItemTypes": "Movie", "Recursive": "true",
                  "Fields": "People,ProviderIds,ProductionYear,PremiereDate,Path,Genres,Studios",
                  "SortBy": "SortName", "SortOrder": "Ascending"}
        if search:
            params["SearchTerm"] = search
        data = self.get(f"/Users/{self.user_id}/Items", **params)
        items = data.get("Items", [])
        return items[:limit] if limit else items

    def person_id(self, name):
        if name in self._person_cache:
            return self._person_cache[name]
        data = self.get(f"/Users/{self.user_id}/Items",
                        IncludeItemTypes="Person", SearchTerm=name,
                        Recursive="true", Limit=5)
        hit = next((i for i in data.get("Items", []) if i.get("Name") == name),
                   (data.get("Items") or [None])[0])
        pid = hit["Id"] if hit else None
        self._person_cache[name] = pid
        return pid

    def apply(self, movie, changes, mode, lock, dry_run):
        """changes: {"actors": [...], "genres": [...], "tags": [...], "studios": [{Name}]}，
        空列表 = 不动该字段。返回写后摘要字符串。"""
        name = movie.get("Name")
        if dry_run:
            parts = []
            if changes["actors"]:
                old = [p["Name"] for p in movie.get("People") or [] if p.get("Type") == "Actor"]
                merged = merge_named([{"Name": n} for n in old], changes["actors"], mode)
                parts.append("演员：" + ("、".join(p["Name"] for p in merged) or "（无）"))
            if changes["genres"]:
                parts.append("类型：" + ("、".join(merge_strings(names_of(movie, "Genres", "GenreItems"), changes["genres"], mode)) or "（无）"))
            if changes["tags"]:
                parts.append("标签：" + ("、".join(merge_strings(names_of(movie, "Tags", "TagItems"), changes["tags"], mode)) or "（无）"))
            if changes["studios"]:
                merged_s = merge_named(movie.get("Studios"), changes["studios"], mode)
                parts.append("工作室：" + ("、".join(s.get("Name") for s in merged_s) or "（无）"))
            if changes.get("year"):
                y, iso = changes["year"]
                parts.append(f"年份：{y}（上映日 {iso[:10]}，原值 {movie.get('ProductionYear') or '（无）'} / {str(movie.get('PremiereDate') or '')[:10] or '（无）'}）")
            print(f"[预览] {name} -> " + "；".join(parts))
            return True
        # 全量回写：先拿完整 DTO
        full = self.get(f"/Users/{self.user_id}/Items/{movie['Id']}")
        summary = []
        if changes["actors"]:
            keep = [p for p in full.get("People") or [] if p.get("Type") != "Actor"]
            merged = merge_named(
                [p for p in full.get("People") or [] if p.get("Type") == "Actor"],
                changes["actors"], mode)
            full["People"] = keep + merged
            summary.append("演员：" + "、".join(p["Name"] for p in merged))
        if changes["genres"]:
            full["Genres"] = merge_strings(names_of(full, "Genres", "GenreItems"), changes["genres"], mode)
            # 关键：Emby 更新时读 GenreItems，忽略 Genres 字符串数组，必须成对发。
            # 旧条目原样保留（含服务端给的 Id），新类型只发 {Name}，服务端按名字新建。
            full["GenreItems"] = merge_named(
                full.get("GenreItems"),
                [{"Name": n} for n in changes["genres"]], mode)
            summary.append("类型：" + "、".join(full["Genres"]))
        if changes["tags"]:
            full["Tags"] = merge_strings(names_of(full, "Tags", "TagItems"), changes["tags"], mode)
            # 同上：Tags 必须和 TagItems 成对发，否则服务端忽略。
            full["TagItems"] = merge_named(
                full.get("TagItems"),
                [{"Name": n} for n in changes["tags"]], mode)
            summary.append("标签：" + "、".join(full["Tags"]))
        if changes["studios"]:
            full["Studios"] = merge_named(full.get("Studios"), changes["studios"], mode)
            summary.append("工作室：" + "、".join(s.get("Name") for s in full["Studios"]))
        if changes.get("year"):
            y, iso = changes["year"]
            full["ProductionYear"] = y
            full["PremiereDate"] = iso
            summary.append(f"年份：{y}（上映日 {iso[:10]}）")
        if full.get("ProviderIds") is None:
            full["ProviderIds"] = {}
        if lock:
            locked = full.get("LockedFields") or []
            for key, ln in LOCK_NAMES.items():
                if changes.get(key):
                    if ln not in locked:
                        locked.append(ln)
            # 年份没有对应的 LockedFields 值，锁不住，此处不加任何东西
            full["LockedFields"] = locked
        self.post(f"/Items/{movie['Id']}", full)
        print(f"[OK] {name} -> " + "；".join(summary))
        # 写后重读核对：POST 返回 200 只代表接受，不代表字段真写上了
        # （Genres/Tags 只发字符串数组时就是 200 但没写上）。核对不上算失败。
        try:
            after = self.get(f"/Users/{self.user_id}/Items/{movie['Id']}")
        except Exception as e:
            print(f"[核对失败] {name}：写后重读失败：{e}")
            return False
        bad = []
        def _names(items):
            return {(d.get("Name") or "").lower() for d in (items or [])}
        if changes["actors"]:
            want = {p["Name"].lower() for p in full.get("People") or [] if p.get("Type") == "Actor"}
            got = {p["Name"].lower() for p in after.get("People") or [] if p.get("Type") == "Actor"}
            if not want <= got:
                bad.append(f"演员实际={[p['Name'] for p in after.get('People') or [] if p.get('Type') == 'Actor']}")
        if changes["genres"]:
            want = {s.lower() for s in full.get("Genres") or []}
            got = {s.lower() for s in names_of(after, "Genres", "GenreItems")}
            if not want <= got:
                bad.append(f"类型实际={names_of(after, 'Genres', 'GenreItems')}")
        if changes["tags"]:
            want = {s.lower() for s in full.get("Tags") or []}
            # 注意：读回的 Tags 常为 None，真实标签在 TagItems 里，以并集为准
            got = {s.lower() for s in names_of(after, "Tags", "TagItems")}
            if not want <= got:
                bad.append(f"标签实际={names_of(after, 'Tags', 'TagItems')}")
        if changes["studios"]:
            want = _names(full.get("Studios"))
            got = _names(after.get("Studios"))
            if not want <= got:
                bad.append(f"工作室实际={[s.get('Name') for s in after.get('Studios') or []]}")
        if changes.get("year"):
            if after.get("ProductionYear") != changes["year"][0]:
                bad.append(f"年份实际={after.get('ProductionYear')}")
        if lock:
            want_lock = [ln for k, ln in LOCK_NAMES.items() if changes.get(k)]
            got_lock = after.get("LockedFields") or []
            missing = [ln for ln in want_lock if ln not in got_lock]
            if missing:
                bad.append(f"锁定缺失={missing}，实际锁定={got_lock}")
        if bad:
            print(f"[核对失败] {name}：" + "；".join(bad))
            return False
        print(f"[核对] {name} 写入与锁定均已确认")
        return True

def main():
    ap = argparse.ArgumentParser(description="Emby 批量给电影加演员 / 类型 / 标签 / 工作室 / 年份")
    ap.add_argument("--url", default=os.environ.get("EMBY_URL", "http://127.0.0.1:8096"))
    ap.add_argument("--api-key", default=os.environ.get("EMBY_API_KEY", ""))
    ap.add_argument("--search", help="只处理片名/路径含此关键字的电影，如 SHKD")
    ap.add_argument("--actors", help="演员名，英文逗号分隔，可写 名字|角色")
    ap.add_argument("--actors-file", help="每行一个演员，可写 名字|角色")
    ap.add_argument("--genres", help="类型，英文逗号分隔，如 剧情,爱情")
    ap.add_argument("--tags", help="标签，英文逗号分隔，如 LTX,破解")
    ap.add_argument("--studios", help="工作室，英文逗号分隔，如 S1")
    ap.add_argument("--year", type=int, help="年份，如 2024；同时写 ProductionYear 和 PremiereDate（该年1月1日）")
    ap.add_argument("--premiere-date", help="上映日期 YYYY-MM-DD，如 2024-05-01；给了它则以它为准，年份从它取")
    ap.add_argument("--mode", choices=["append", "replace"], default="append",
                    help="append=追加去重（默认），replace=替换该字段旧值")
    ap.add_argument("--lock", dest="lock", action="store_true", default=True,
                    help="锁定本次改动的字段（演员=Cast，类型=Genres，标签=Tags，工作室=Studios，默认开）")
    ap.add_argument("--no-lock", dest="lock", action="store_false")
    ap.add_argument("--lock-only", action="store_true",
                    help="只补锁定，不改内容；不给字段时锁 Cast+Genres+Tags+Studios，给了字段只锁给的")
    ap.add_argument("--limit", type=int, help="最多处理 N 部，先拿 1 部验证时用 --limit 1")
    ap.add_argument("--dry-run", action="store_true", help="只预览不写入")
    ap.add_argument("--yes", action="store_true", help="不经确认直接写入（不加则先预览确认）")
    args = ap.parse_args()

    if not args.api_key:
        sys.exit("缺 API Key：设环境变量 EMBY_API_KEY，或 --api-key（别把 Key 发到聊天里）")
    changes = {
        "actors": parse_actors(args),
        "genres": parse_list(args.genres),
        "tags": parse_list(args.tags),
        "studios": [{"Name": n} for n in parse_list(args.studios)],
        "year": resolve_year(args.year, args.premiere_date),
    }
    if not any(changes.values()) and not args.lock_only:
        sys.exit("没给要加的内容：--actors / --genres / --tags / --studios / --year 至少给一个")
    if changes["year"] and not args.lock_only:
        print("注意：年份没有对应的 LockedFields 值，锁不住；认不出的片一般能留住，但刷新后如有新数据可能被改。")

    emby = Emby(args.url, args.api_key)
    emby.user_id = emby.admin_user_id()
    desc = []
    if changes["actors"]:
        desc.append("演员：" + "、".join(a["Name"] for a in changes["actors"]))
    if changes["genres"]:
        desc.append("类型：" + "、".join(changes["genres"]))
    if changes["tags"]:
        desc.append("标签：" + "、".join(changes["tags"]))
    if changes["studios"]:
        desc.append("工作室：" + "、".join(s["Name"] for s in changes["studios"]))
    if changes["year"]:
        desc.append(f"年份：{changes['year'][0]}（上映日 {changes['year'][1][:10]}）")
    print(f"Emby: {args.url}，模式：{args.mode}，锁定：{args.lock}" +
          (f"，{'；'.join(desc)}" if desc else "，只补锁定"))
    movies = emby.list_movies(args.search, args.limit)
    print(f"命中电影 {len(movies)} 部：")
    # 注意：列表接口不返回 LockedFields，这里看到的“未锁定”不可信；
    # 真正的锁定状态以写入后的 [核对] 为准（核对走全量 GET）。
    # 命中 ≤20 部时，这里先逐部全量取一次锁定状态，超过则跳过以免请求太多。
    lock_map = {}
    if len(movies) <= 20:
        for m in movies:
            try:
                lock_map[m["Id"]] = ",".join(
                    emby.get(f"/Users/{emby.user_id}/Items/{m['Id']}").get("LockedFields") or []) or "（未锁定）"
            except Exception:
                lock_map[m["Id"]] = "（查询失败）"
    for m in movies:
        old_a = [p["Name"] for p in m.get("People") or [] if p.get("Type") == "Actor"]
        old_s = [s.get("Name") for s in m.get("Studios") or []]
        locked = lock_map.get(m["Id"], "（未查询，见写入后核对）")
        print(f"  - {m.get('Name')} ({m.get('ProductionYear') or ''})"
              f" 演员：{'、'.join(old_a) or '（无）'}"
              f" 类型：{'、'.join(names_of(m, 'Genres', 'GenreItems')) or '（无）'}"
              f" 标签：{'、'.join(names_of(m, 'Tags', 'TagItems')) or '（无）'}"
              f" 工作室：{'、'.join(old_s) or '（无）'} 锁定：{locked}")
    if not movies:
        return
    if args.lock_only:
        lock_fields = [ln for k, ln in LOCK_NAMES.items() if changes.get(k)] or list(LOCK_NAMES.values())
        ok = fail = 0
        for m in movies:
            try:
                full = emby.get(f"/Users/{emby.user_id}/Items/{m['Id']}")
                if full.get("ProviderIds") is None:
                    full["ProviderIds"] = {}
                locked = full.get("LockedFields") or []
                for ln in lock_fields:
                    if ln not in locked:
                        locked.append(ln)
                full["LockedFields"] = locked
                emby.post(f"/Items/{m['Id']}", full)
                after = emby.get(f"/Users/{emby.user_id}/Items/{m['Id']}")
                got_lock = after.get("LockedFields") or []
                missing = [ln for ln in lock_fields if ln not in got_lock]
                if missing:
                    print(f"[核对失败] {m.get('Name')} 锁定缺失={missing}，实际锁定={got_lock}")
                    fail += 1
                else:
                    print(f"[OK] {m.get('Name')} 已锁定 {','.join(lock_fields)}（已核对）")
                    ok += 1
            except Exception as e:
                fail += 1
                print(f"[失败] {m.get('Name')}：{e}")
        print(f"完成：成功 {ok}，失败 {fail}")
        return
    if not args.dry_run and not args.yes:
        if input("确认写入吗？[y/N] ").strip().lower() != "y":
            print("已取消，未写入。")
            return
    for a in changes["actors"]:
        pid = emby.person_id(a["Name"])
        if pid:
            a["Id"] = pid
            print(f"演员 {a['Name']} 复用已有 Person Id（照片跟着走）")
        else:
            print(f"演员 {a['Name']} 库里没有，写入时按名字新建人物")
    ok = fail = 0
    for m in movies:
        try:
            # apply() 内部写后会重读核对，核对不上返回 False，计为失败
            if emby.apply(m, changes, args.mode, args.lock, args.dry_run):
                ok += 1
            else:
                fail += 1
        except Exception as e:
            fail += 1
            print(f"[失败] {m.get('Name')}：{e}")
    print(f"完成：成功 {ok}，失败 {fail}" + ("（预览，未写入）" if args.dry_run else ""))

if __name__ == "__main__":
    main()
