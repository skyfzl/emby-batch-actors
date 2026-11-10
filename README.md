# Emby 批量加演员 / 类型 / 标签 / 工作室 / 年份（4.10.2.0）

可以做。结论先说：**插件能实现“多选电影 → 一次加一个/多个演员”，但入口不在 Emby 原生电影列表的多选里**——Emby 插件加不进原生列表菜单，只能在自己的插件页里选片。用法就是：打开插件页 → 勾选多部电影 → 填演员 → 应用。同一套逻辑也支持批量加类型（Genres）、标签（Tags）、工作室（Studios）、年份（ProductionYear + PremiereDate），只填要改的字段，没填的不动。

## 先说清一个边界

这解决不了“识别不出来、刮削不到元数据”本身。TMDB 里没有的片（如 JAV/LTX），刮削永远认不出来，演员只能这样手填。手填后锁定对应字段（演员=Cast，类型=Genres，标签=Tags，工作室=Studios），以后刷新元数据才不会把手填的清掉；海报、简介仍需手动改。

## 两条路（建议先走脚本验证，再装插件）

| | 脚本 `script/batch_add_actors.py` | 插件 `plugin/` |
|---|---|---|
| 优点 | 免编译，今晚就能用；逻辑与插件页完全相同 | 在 Emby 网页里点一点就行，不用敲命令 |
| 缺点 | 每次要敲命令、要 API Key | 要在 Windows 上用 .NET 8 SDK 编译出 DLL，再重启 Emby |

## 路 1：脚本（先用 1 部电影验证）

在 VPS 或 Windows 上，Python 3.8+ 即可，零依赖（只用自带 urllib，不用装 requests；Debian 12/13 默认拦系统级 pip，`pip install requests` 会报 externally-managed-environment，别用 `--break-system-packages`，也别为这个脚本装——如坚持用 requests 版，装 Debian 包 `apt install python3-requests` 即可）。

```bash
export EMBY_URL="http://10.10.10.4:8096"   # 内网直连，别走公网域名
export EMBY_API_KEY="你的 API Key"            # 控制台 > 高级 > API Keys 新建，别发到聊天里

# 1. 只预览，不写入
python3 script/batch_add_actors.py --search SHKD --actors "小凑四叶" --dry-run

# 2. 先拿 1 部验证写入
python3 script/batch_add_actors.py --search SHKD --actors "小凑四叶" --limit 1 --yes

# 3. 去 Emby 里看那部电影的演员对不对，对了再全量；多个演员用英文逗号
python3 script/batch_add_actors.py --search SHKD --actors "小凑四叶,希志爱野" --yes

# 一次加演员 + 类型 + 标签 + 工作室（先预览，再拿 1 部验证）
python3 script/batch_add_actors.py --search SHKD --actors "小凑四叶" \
    --genres "剧情,爱情" --tags "LTX,破解" --studios "S1" --dry-run
python3 script/batch_add_actors.py --search SHKD --actors "小凑四叶" \
    --genres "剧情" --tags "LTX" --studios "S1" --limit 1 --yes

# 只加其中一项也行，不填的字段不动
python3 script/batch_add_actors.py --search SHKD --tags "收藏" --yes

# 加年份：只给年份时上映日取该年 1 月 1 日；知道准确日期就给 --premiere-date
python3 script/batch_add_actors.py --search SHKD --year 2024 --dry-run
python3 script/batch_add_actors.py --search SHKD --year 2024 --limit 1 --yes
python3 script/batch_add_actors.py --search SHKD --premiere-date 2024-05-01 --limit 1 --yes

# 替换模式（只替换填了的字段；演员只删旧演员，导演/编剧不动）：--mode replace
# 不锁定改动字段：--no-lock
# 只补锁定不改内容：--lock-only（不给字段锁 Cast+Genres+Tags+Studios，给了字段只锁给的）
```

## 路 2：插件

### 编译（GitHub Actions 自动编，不用本地装 SDK）

工作流在 `.github/workflows/build-plugin.yml`：推到 `main`（改了 `plugin/` 时）或在 Actions 页手动 Run，都会用 .NET 8 编出 DLL，产物名 `Emby.BatchActors`。

1. 在 GitHub 上新建空仓库（例如 `skyfzl/emby-batch-actors`，不要勾 README），把本目录推上去：

   ```bash
   git init -b main
   git add .
   git commit -m "Batch Actors plugin + script"
   git remote add origin git@github.com:skyfzl/emby-batch-actors.git
   git push -u origin main
   ```

2. 到仓库的 Actions 页打开 `Build plugin DLL` 那次运行，底部 Artifacts 里下载 `Emby.BatchActors`，解压得到 `Emby.BatchActors.dll`（插件页 HTML 已嵌进 DLL，只需这一个文件）。注意：Artifacts 只在 Actions 运行页面里，不会出现在 Releases。
3. 以后改了 `plugin/` 再推一次，Actions 会重新编，下载新 DLL 覆盖即可。

### 发版到 Releases（打 tag 才发）

工作流在 `.github/workflows/release-plugin.yml`：推送 `v*` 格式的 tag 时自动编好 DLL 并发到 Releases：

```bash
git tag v1.0.0
git push origin v1.0.0
```

随后在仓库的 Releases 里就能直接下载 `Emby.BatchActors.dll`。不打 tag 只推代码时，只会在 Actions 里留 Artifacts，不会产生 Release。

### 编译（本地，Windows 上做；这台 VM 没有 dotnet，所以 DLL 没在这里编译）

```powershell
# 装 .NET 8 SDK 后，在 plugin 目录：
dotnet build -c Release
# 产物：plugin\bin\Release\netstandard2.0\Emby.BatchActors.dll
```

引用说明：NuGet 上 `MediaBrowser.Common` 最新稳定版是 4.9.1.90，没有 4.10.2.0 的稳定包；插件只用到 4.9→4.10 未变的 `BasePlugin` / `IHasWebPages`，用 4.9.1.90 编出的 `netstandard2.0` DLL 可在 4.10.2.0 上加载。批量写入逻辑在配置页 JS 里直接调 Emby 自带 REST API，不依赖易变的内部 API。

页面结构（Emby 4.10 要求，2026-11-11 修正）：Emby 把插件页 HTML 注入控制台时行内 `<script>` 不执行，老写法（`data-role="page"` + 行内脚本）会整页空白、页面元素根本不进 DOM。正确写法是 CloudDrive 插件同款：HTML 根元素用 `data-controller="__plugin/batchactorsjs"` 声明控制器，逻辑放在独立的 AMD 模块 `Configuration/batchactors.js` 里，`Plugin.cs` 的 `GetPages` 把 HTML 和 JS 注册成两个页面（JS 那个不进菜单）。改页面只改这两个文件即可，`Plugin.cs` / `csproj` 不用再动。

### 安装（Docker，媒体 VPS）

```bash
# 你的 compose 是 /opt/emby/config:/config，所以宿主机插件目录就是：
cp Emby.BatchActors.dll /opt/emby/config/plugins/
docker restart emby
```

### 使用

控制台 → 插件 → Batch Actors，或直接打开：

```
https://emby.tofzl.com/web/index.html#!/configurationpage?name=BatchActors
```

1. 点「加载电影」，用筛选框找片（如 `SHKD`），勾选多部；「全选无演员的」可一次挑出没演员的片。
2. 演员每行一个，可写 `名字|角色`，如 `小凑四叶|主演`；类型、标签、工作室各填一行，用英文逗号分隔；年份填 4 位数字，上映日期可选（有它为准）。
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
