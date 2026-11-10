# Emby 批量加演员 / 类型 / 标签 / 工作室 / 年份（4.10.2.0）

可以做。结论先说：**插件能实现“多选电影 → 一次加一个/多个演员”，但入口不在 Emby 原生电影列表的多选里**——Emby 插件加不进原生列表菜单，只能在自己的插件页里选片。用法就是：打开插件页 → 勾选多部电影 → 填演员 → 应用。同一套逻辑也支持批量加类型（Genres）、标签（Tags）、工作室（Studios）、年份（ProductionYear + PremiereDate），只填要改的字段，没填的不动。

### 使用

控制台 → 插件 → Batch Actors，或直接打开：

```
http://127.0.0.1:8096/web/index.html#!/configurationpage?name=BatchActors
```

1. 点「加载电影」，用筛选框找片（如 `AAA`），勾选多部；「全选无演员的」可一次挑出没演员的片。
2. 演员每行一个，可写 `名字|角色`，如 `刘亦菲|主演`；类型、标签、工作室各填一行，用英文逗号分隔；年份填 4 位数字，上映日期可选（有它为准）。
3. 先点「预览」核对，再点「应用到选中电影」。默认追加（去重）+ 锁定本次改动的字段。

## 关键实现点（别踩的坑）

- `POST /Items/{Id}` 不是增量更新：只发部分字段会把没发的字段清空。所以插件页和脚本都是 **先 GET 全量 → 合并改动字段 → 全量 POST**。
- `ProviderIds` 为空也要发 `{}`，否则 400。
- `People` 里演员的格式是 `{"Name": "…", "Type": "Actor"}`，`Role` 可选；库里已有的人物会复用其 Id（照片跟着走），没有的按名字新建人物。
- 类型 / 标签必须成对发：`Genres` + `GenreItems`、`Tags` + `TagItems`。Emby 更新时读的是 `GenreItems` / `TagItems`，忽略 `Genres` / `Tags` 字符串数组（2026-11-11 实测：只发字符串数组时 POST 返回 200、实际没写上；演员、年份、工作室不受影响）。旧条目原样保留（含服务端给的 Id），新类型/标签只发 `{"Name": "…"}`，服务端按名字新建。
- 工作室 `Studios` 是 `NameLongIdPair[]`，只发 `{"Name": "…"}`，让服务端按名字关联/新建，不要把 `GET /Studios` 返回的 GUID 当 Id 发。
- 脚本写完会重读核对：`[OK]` 只代表 POST 接受，`[核对]` 才代表字段和锁定真写上了；核对不上会显示 `[核对失败]` 并计入失败数。另外列表里看到的“未锁定”不可信（列表接口不返回 `LockedFields`），以 `[核对]` 为准。
- 核对读数时注意：读回的 `Tags` 常为 `None`，真实标签在 `TagItems` 里；脚本的显示、合并、核对都以 `Genres`+`GenreItems`、`Tags`+`TagItems` 的并集为准（2026-11-11 修正：之前核对只读 `Tags`，导致标签明明写上了还报 `[核对失败]`）。
- 锁定名按字段：演员 `Cast`、类型 `Genres`、标签 `Tags`、工作室 `Studios`。
- 年份：`ProductionYear`（int）+ `PremiereDate`（ISO 8601）一起写，只发 `"2006"` 会被静默丢弃；只给年份时上映日取该年 1 月 1 日。**年份锁不住**：`LockedFields` 里没有 `ProductionYear` / `PremiereDate`；认不出的片没有刮削数据可覆盖，一般能留住，但刷新后如有新数据可能被改。
- 锁定是往 `LockedFields` 里加 `Cast`（2026-11-11 修正：之前误写成 `People`，Emby 会静默丢弃，看起来写入成功、实际没锁上；可锁的枚举值是 `AlbumArtists, Artists, Cast, Genres, Name, Overview, …`，没有 `People`）。以后想让 TMDB 再填演员，要先去该电影的元数据编辑里解锁。已加过演员但没锁上的电影，用脚本 `--lock-only` 只补锁定，不改演员。

## 验证清单

- [ ] 脚本 `--dry-run` 列出的电影和演员都对
- [ ] `--limit 1` 写入后，Emby 里那部电影演员已加上，其他字段（标题/简介/海报）没变
- [ ] 插件页能打开、能加载电影列表、预览与写入结果一致
- [ ] 刷新一次该电影的元数据，演员还在（锁定生效）

## 文件

```
plugin/Emby.BatchActors.csproj        # netstandard2.0，C# 8
plugin/Plugin.cs                      # 注册插件页，GUID d45e648c-656d-4382-ab7b-8a919dc4aeed
plugin/PluginConfiguration.cs         # 默认锁定改动字段 / 默认追加
plugin/Configuration/batchactors.html # 插件页（自包含 HTML+JS）
script/batch_add_actors.py            # 免编译脚本，同一逻辑
```
