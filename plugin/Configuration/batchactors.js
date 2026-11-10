/*
* Batch Actors 配置页控制器（Emby 4.10 AMD 模式）。
*
* Emby 把插件页的 HTML 注入控制台时，行内 <script> 根本不会执行，所以逻辑
* 必须放在这个独立的 AMD 模块里：页面 HTML 用 data-controller="__plugin/batchactorsjs"
* 声明它，Plugin.cs 再把这个 JS 注册成第二个（不进菜单的）页面。
* 老写法（data-role="page" + 行内脚本）在 4.10 里页面根本挂不起来、整页空白。
* （对照：CloudDrive 插件的 embyConfigPage.html / embyConfigPage.js，同一写法。）
*/
define(['baseView', 'loading', 'emby-input', 'emby-button', 'emby-select', 'emby-checkbox', 'emby-scroller'], function (BaseView, loading) {
'use strict';

var pluginId = 'd45e648c-656d-4382-ab7b-8a919dc4aeed';

function View(view) {
BaseView.apply(this, arguments);

var movies = []; // {Id, Name, ProductionYear, Path, People:[{Name,Type}]}
var personCache = {};

function log(msg) {
var el = view.querySelector('#baLog');
el.textContent += '\n' + msg;
el.scrollTop = el.scrollHeight;
}
function $(id) { return view.querySelector('#' + id);}
function esc(s) { return String(s == null? '': s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');}
function actorNames(m) {
return (m.People || []).filter(function (p) { return p.Type === 'Actor';}).map(function (p) { return p.Name;});
}
function filtered() {
var q = ($('baFilter').value || '').trim().toLowerCase();
if (!q) return movies;
return movies.filter(function (m) {
return (m.Name || '').toLowerCase().indexOf(q) >= 0 || (m.Path || '').toLowerCase().indexOf(q) >= 0;
});
}
function posterHtml(m) {
if (m.ImageTags && m.ImageTags.Primary) {
var url = ApiClient.getImageUrl(m, { type: 'Primary', maxWidth: 96 });
return '<img src="' + esc(url) + '" style="width:64px;height:96px;object-fit:cover;border-radius:4px;flex-shrink:0" alt="" />';
}
return '<span style="width:64px;height:96px;background:#2a2a2a;border-radius:4px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:26px">🎬</span>';
}
// 代码里改 checked 不会触发 change，emby-checkbox 的外观就不同步；统一走这里
function setChecked(c, v) {
if (c.checked !== v) {
c.checked = v;
c.dispatchEvent(new Event('change', { bubbles: true }));
}
}
function render() {
var list = filtered();
var html = list.map(function (m) {
return '<label class="ba-item" style="display:flex;gap:10px;align-items:flex-start;padding:8px 6px;border-bottom:1px solid #333;cursor:pointer;border-radius:4px">' +
'<input is="emby-checkbox" type="checkbox" class="ba-check" value="' + esc(m.Id) + '" style="margin-top:6px;flex-shrink:0" /> ' +
posterHtml(m) +
'<span style="flex:1;min-width:0">' +
'<span style="font-weight:600">' + esc(m.Name) + '</span> <span style="color:#888">' + (m.ProductionYear || '') + '</span><br/>' +
'<span style="color:#aaa;font-size:13px">演员：' + esc(actorNames(m).join('、') || '（无）') +
'　类型：' + esc(namesOf(m, 'Genres', 'GenreItems').join('、') || '（无）') +
'　标签：' + esc(namesOf(m, 'Tags', 'TagItems').join('、') || '（无）') +
'　工作室：' + esc((m.Studios || []).map(function (s) { return s.Name; }).join('、') || '（无）') + '</span><br/>' +
'<span style="color:#666;font-size:12px;word-break:break-all">' + esc(m.Path || '') + '</span></span></label>';
}).join('');
$('baList').innerHTML = html || '没有匹配的电影。';
$('baCount').textContent = '共 ' + movies.length + ' 部，当前显示 ' + list.length + ' 部';
}

function parseActors() {
var raw = $('baActors').value || '';
var out = [], seen = {};
raw.split(/[\n,，、；;]+/).forEach(function (part) {
var t = part.trim();
if (!t) return;
var seg = t.split('|'), name = seg[0].trim(), role = (seg[1] || '').trim();
if (!name || seen[name.toLowerCase()]) return;
seen[name.toLowerCase()] = true;
out.push({ Name: name, Type: 'Actor', Role: role || undefined});
});
return out;
}

function parseList(id) {
var raw = $(id).value || '';
var out = [], seen = {};
raw.split(/[\n,，、；;]+/).forEach(function (part) {
var t = part.trim();
if (!t || seen[t.toLowerCase()]) return;
seen[t.toLowerCase()] = true;
out.push(t);
});
return out;
}
function mergeStrings(oldArr, add, mode) {
if (mode === 'replace') return add.slice();
var out = (oldArr || []).slice(), have = {};
out.forEach(function (s) { have[s.toLowerCase()] = true;});
add.forEach(function (s) { if (!have[s.toLowerCase()]) { out.push(s); have[s.toLowerCase()] = true;}});
return out;
}
function namesOf(item, listKey, itemsKey) {
// 字符串数组与 *Items 并集去重保序：读回的 Tags 常为 None，真实值在 TagItems 里
var out = [], seen = {};
(item[listKey] || []).forEach(function (n) { if (n &&!seen[n.toLowerCase()]) { seen[n.toLowerCase()] = true; out.push(n);}});
(item[itemsKey] || []).forEach(function (d) { var n = d.Name; if (n &&!seen[n.toLowerCase()]) { seen[n.toLowerCase()] = true; out.push(n);}});
return out;
}
function mergeNamed(oldArr, add, mode) {
if (mode === 'replace') return add.slice();
var out = (oldArr || []).slice(), have = {};
out.forEach(function (d) { have[(d.Name || '').toLowerCase()] = true;});
add.forEach(function (d) { if (!have[(d.Name || '').toLowerCase()]) { out.push(d); have[(d.Name || '').toLowerCase()] = true;}});
return out;
}

// 已存在的人物复用其 Id（照片/详情跟着走）；不存在则不带 Id，Emby 会按名字新建人物。
function resolvePersonId(name) {
if (personCache[name]) return Promise.resolve(personCache[name]);
var userId = ApiClient.getCurrentUserId();
return ApiClient.getItems(userId, {
IncludeItemTypes: 'Person', SearchTerm: name, Recursive: true, Limit: 5
}).then(function (res) {
var hit = (res.Items || []).filter(function (it) { return it.Name === name;})[0] ||
(res.Items || [])[0] || null;
personCache[name] = hit? hit.Id: null;
return personCache[name];
}).catch(function () { return null;});
}

// 媒体库下拉框：打开页面时拉一次用户媒体库；切库后自动按新库重新加载
var librariesLoaded = false;
function loadLibraries() {
if (librariesLoaded) return;
librariesLoaded = true;
var userId = ApiClient.getCurrentUserId();
ApiClient.getUserViews(userId).then(function (res) {
var sel = $('baLibrary');
var cur = sel.value;
sel.innerHTML = '<option value="">全部媒体库</option>' + (res.Items || []).map(function (v) {
return '<option value="' + esc(v.Id) + '">' + esc(v.Name) + '</option>';
}).join('');
if (cur) sel.value = cur;
}).catch(function () { /* 拉不到就只留“全部媒体库” */ });
}

// 文件夹下拉框：选了媒体库后，拉它下面所有文件夹（含子文件夹）
// 显示用“父 / 子”全路径，避免重名文件夹分不清
function loadFolders(libraryId) {
var sel = $('baFolder');
sel.innerHTML = '<option value="">全部文件夹</option>';
sel.disabled = !libraryId;
if (!libraryId) return;
var userId = ApiClient.getCurrentUserId();
ApiClient.getItems(userId, {
ParentId: libraryId, IncludeItemTypes: 'Folder', Recursive: true,
Fields: 'Path', SortBy: 'SortName', SortOrder: 'Ascending', Limit: 1000
}).then(function (res) {
var items = res.Items || [];
var byId = {};
items.forEach(function (f) { byId[f.Id] = f; });
function displayPath(f) {
var parts = [f.Name], cur = f, guard = 0;
while (cur.ParentId && byId[cur.ParentId] && guard++ < 10) {
cur = byId[cur.ParentId];
parts.unshift(cur.Name);
}
return parts.join(' / ');
}
sel.innerHTML = '<option value="">全部文件夹</option>' + items.map(function (f) {
return '<option value="' + esc(f.Id) + '">' + esc(displayPath(f)) + '</option>';
}).join('');
}).catch(function () { /* 拉不到就只留“全部文件夹” */ });
}

function loadMovies() {
var userId = ApiClient.getCurrentUserId();
var libId = $('baLibrary').value;
var folderId = $('baFolder').value;
var scopeName = folderId ? ($('baFolder').selectedOptions[0] || {}).textContent :
libId ? ($('baLibrary').selectedOptions[0] || {}).textContent : '';
movies = [];
log('开始加载电影…' + (scopeName ? '（' + scopeName + '）' : '（全部媒体库）'));
loading.show();
var start = 0, limit = 500;
function page() {
var query = {
IncludeItemTypes: 'Movie', Recursive: true,
Fields: 'People,ProviderIds,ProductionYear,Path,Genres,Studios',
SortBy: 'SortName', SortOrder: 'Ascending',
StartIndex: start, Limit: limit
};
if (folderId) query.ParentId = folderId;
else if (libId) query.ParentId = libId;
return ApiClient.getItems(userId, query).then(function (res) {
movies = movies.concat(res.Items || []);
start += (res.Items || []).length;
log('已加载 ' + movies.length + ' / ' + res.TotalRecordCount);
if (start < res.TotalRecordCount && (res.Items || []).length) return page();
render();
log('加载完成，共 ' + movies.length + ' 部电影。');
});
}
page().then(function () { loading.hide(); }, function (e) {
loading.hide();
log('加载失败：' + (e && e.message ? e.message : e));
});
}

$('baLoad').addEventListener('click', loadMovies);
$('baLibrary').addEventListener('change', function () {
// 切库后文件夹重置，先拉新库的文件夹，再按新库加载
loadFolders($('baLibrary').value);
if (movies.length) loadMovies();
});
$('baFolder').addEventListener('change', function () {
// 切文件夹后自动按新文件夹加载；还没加载过就等点「加载电影」
if (movies.length) loadMovies();
});
loadLibraries();

$('baFilter').addEventListener('input', render);
// 勾选的行高亮（列表是重新渲染的，所以用事件委托挂在容器上）
$('baList').addEventListener('change', function (e) {
var c = e.target && e.target.closest ? e.target.closest('.ba-check') : null;
if (!c) return;
var row = c.closest('label');
if (row) row.style.background = c.checked ? 'rgba(82,181,75,0.12)' : '';
});
$('baSelectFiltered').addEventListener('click', function () {
var ids = {};
filtered().forEach(function (m) { ids[m.Id] = true;});
view.querySelectorAll('.ba-check').forEach(function (c) { if (ids[c.value]) setChecked(c, true);});
log('已勾选当前筛选的 ' + filtered().length + ' 部。');
});
$('baSelectNoActor').addEventListener('click', function () {
view.querySelectorAll('.ba-check').forEach(function (c) {
var m = movies.filter(function (x) { return x.Id === c.value;})[0];
if (m && actorNames(m).length === 0) setChecked(c, true);
});
log('已勾选无演员的电影。');
});
$('baClear').addEventListener('click', function () {
view.querySelectorAll('.ba-check').forEach(function (c) { setChecked(c, false);});
});

function selectedMovies() {
var ids = {};
view.querySelectorAll('.ba-check:checked').forEach(function (c) { ids[c.value] = true;});
return movies.filter(function (m) { return ids[m.Id];});
}

function buildNewPeople(movie, actors, mode) {
var keep = (movie.People || []).filter(function (p) { return p.Type!== 'Actor';});
var oldActors = (movie.People || []).filter(function (p) { return p.Type === 'Actor';});
var merged = mode === 'replace'? []: oldActors.slice();
var have = {};
merged.forEach(function (p) { have[p.Name.toLowerCase()] = true;});
actors.forEach(function (a) {
if (!have[a.Name.toLowerCase()]) { merged.push(a); have[a.Name.toLowerCase()] = true;}
});
return keep.concat(merged);
}

function parseYear() {
var dateVal = ($('baPremiereDate').value || '').trim();
var yearVal = ($('baYear').value || '').trim();
if (dateVal) {
var y = parseInt(dateVal.slice(0, 4), 10);
if (yearVal && parseInt(yearVal, 10)!== y) { log('年份与上映日期的年份不一致，请改成一致。'); return 'error';}
return [y, dateVal + 'T00:00:00.0000000Z'];
}
if (yearVal) {
var yy = parseInt(yearVal, 10);
if (isNaN(yy) || yy < 1900 || yy > 2100) { log('年份不对：' + yearVal); return 'error';}
return [yy, yy + '-01-01T00:00:00.0000000Z'];
}
return null;
}

function summarize(movie, changes, mode) {
var parts = [];
if (changes.year) parts.push('年份：' + changes.year[0] + '（上映日 ' + changes.year[1].slice(0, 10) + '，原值 ' + (movie.ProductionYear || '（无）') + ' / ' + String(movie.PremiereDate || '').slice(0, 10) + '）');
if (changes.actors.length) {
var p = buildNewPeople(movie, changes.actors, mode).filter(function (x) { return x.Type === 'Actor';});
parts.push('演员：' + (p.map(function (x) { return x.Name;}).join('、') || '（无）'));
}
if (changes.genres.length) parts.push('类型：' + (mergeStrings(namesOf(movie, 'Genres', 'GenreItems'), changes.genres, mode).join('、') || '（无）'));
if (changes.tags.length) parts.push('标签：' + (mergeStrings(namesOf(movie, 'Tags', 'TagItems'), changes.tags, mode).join('、') || '（无）'));
if (changes.studios.length) {
var s = mergeNamed(movie.Studios, changes.studios, mode);
parts.push('工作室：' + (s.map(function (x) { return x.Name;}).join('、') || '（无）'));
}
return parts.join('；');
}

function doApply(dryRun) {
var yearParsed = parseYear();
if (yearParsed === 'error') return;
var changes = {
actors: parseActors(),
genres: parseList('baGenres'),
tags: parseList('baTags'),
studios: parseList('baStudios').map(function (n) { return { Name: n};}),
year: yearParsed
};
var sel = selectedMovies();
if (!changes.actors.length &&!changes.genres.length &&!changes.tags.length &&!changes.studios.length &&!changes.year) {
log('先在第 2 步填至少一项：演员、类型、标签、工作室或年份。'); return;
}
if (!sel.length) { log('先在第 1 步勾选至少一部电影。'); return;}
var mode = view.querySelector('input[name="baMode"]:checked').value;
var lock = $('baLock').checked;
var actors = changes.actors;
log((dryRun? '': '') + '模式=' + mode + '，' + summarize({ People: [], Genres: [], Tags: [], Studios: []}, changes, mode) +
'，电影 ' + sel.length + ' 部，锁定改动字段=' + lock);
// 先把所有演员的 Person Id 查好，再逐部写
var chain = Promise.resolve();
actors.forEach(function (a) {
chain = chain.then(function () { return resolvePersonId(a.Name).then(function (id) { if (id) a.Id = id;});});
});
chain.then(function () {
var seq = Promise.resolve(), ok = 0, fail = 0;
sel.forEach(function (movie) {
seq = seq.then(function () {
if (dryRun) {
log('预览 ' + movie.Name + ' -> ' + summarize(movie, changes, mode));
return;
}
var userId = ApiClient.getCurrentUserId();
// 关键：POST /Items/{Id} 不是增量更新，必须先 GET 全量再回写，否则没传的字段会被清空。
return ApiClient.getItem(userId, movie.Id).then(function (full) {
if (changes.actors.length) full.People = buildNewPeople(full, changes.actors, mode);
if (changes.genres.length) {
full.Genres = mergeStrings(namesOf(full, 'Genres', 'GenreItems'), changes.genres, mode);
// 关键：Emby 更新时读 GenreItems，忽略 Genres 字符串数组，必须成对发
full.GenreItems = mergeNamed(full.GenreItems, changes.genres.map(function (n) { return { Name: n};}), mode);
}
if (changes.tags.length) {
full.Tags = mergeStrings(namesOf(full, 'Tags', 'TagItems'), changes.tags, mode);
// 同上：Tags 必须和 TagItems 成对发
full.TagItems = mergeNamed(full.TagItems, changes.tags.map(function (n) { return { Name: n};}), mode);
}
// Studios 只发 Name，让服务端按名字关联/新建；不要把 /Studios 返回的 GUID 当 Id 发
if (changes.studios.length) full.Studios = mergeNamed(full.Studios, changes.studios, mode);
// 年份：ProductionYear 和 PremiereDate 一起写，只发 "2024" 会被静默丢弃；年份没有锁定名
if (changes.year) { full.ProductionYear = changes.year[0]; full.PremiereDate = changes.year[1];}
if (full.ProviderIds == null) full.ProviderIds = {};
if (lock) {
full.LockedFields = full.LockedFields || [];
// 锁定名：演员=Cast，类型=Genres，标签=Tags，工作室=Studios（没有 People）
var lockMap = { actors: 'Cast', genres: 'Genres', tags: 'Tags', studios: 'Studios'};
Object.keys(lockMap).forEach(function (k) {
if (changes[k].length && full.LockedFields.indexOf(lockMap[k]) < 0) full.LockedFields.push(lockMap[k]);
});
// 年份没有锁定名，不加
}
return ApiClient.ajax({
url: ApiClient.getUrl('Items/' + full.Id),
type: 'POST', data: JSON.stringify(full), contentType: 'application/json'
});
}).then(function () {
ok++;
log('OK ' + movie.Name + ' -> ' + summarize(movie, changes, mode));
if (changes.actors.length) movie.People = buildNewPeople(movie, changes.actors, mode);
if (changes.genres.length) {
movie.Genres = mergeStrings(namesOf(movie, 'Genres', 'GenreItems'), changes.genres, mode);
movie.GenreItems = mergeNamed(movie.GenreItems, changes.genres.map(function (n) { return { Name: n};}), mode);
}
if (changes.tags.length) {
movie.Tags = mergeStrings(namesOf(movie, 'Tags', 'TagItems'), changes.tags, mode);
movie.TagItems = mergeNamed(movie.TagItems, changes.tags.map(function (n) { return { Name: n};}), mode);
}
if (changes.studios.length) movie.Studios = mergeNamed(movie.Studios, changes.studios, mode);
if (changes.year) { movie.ProductionYear = changes.year[0]; movie.PremiereDate = changes.year[1];}
}).catch(function (e) {
fail++;
log('失败 ' + movie.Name + '：' + (e && e.message? e.message: e));
});
});
});
return seq.then(function () {
if (!dryRun) { render(); log('完成：成功 ' + ok + '，失败 ' + fail + '。');}
else log('预览完成。');
});
}).catch(function (e) { log('出错：' + (e && e.message? e.message: e));});
}

$('baPreview').addEventListener('click', function () { doApply(true);});
$('baApply').addEventListener('click', function () {
if (!confirm('确定要给选中的电影写入吗？建议先点「预览」核对。')) return;
doApply(false);
});

// 插件配置里的默认值带到页面上（每次打开页面时取一次）
this.loadDefaults = function () {
if (window.ApiClient && ApiClient.getPluginConfiguration) {
ApiClient.getPluginConfiguration(pluginId).then(function (cfg) {
if (cfg && cfg.LockPeopleFieldByDefault === false) $('baLock').checked = false;
if (cfg && cfg.AppendByDefault === false) {
var r = view.querySelector('input[name="baMode"][value="replace"]');
if (r) r.checked = true;
}
}).catch(function () { /* 用页面默认值即可 */});
}
};
}

Object.assign(View.prototype, BaseView.prototype);

View.prototype.onResume = function (options) {
BaseView.prototype.onResume.apply(this, arguments);
if (this.loadDefaults) this.loadDefaults();
};

return View;
});
