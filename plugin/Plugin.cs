using System;
using System.Collections.Generic;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace Emby.BatchActors
{
    /// <summary>
    /// 批量加演员插件。C# 层只做注册 + 提供配置页，
    /// 真正的批量写入在 Configuration/batchactors.js 的 AMD 控制器里，
    /// 直接调 Emby 自带 REST API，避开内部 API 在 4.9 -&gt; 4.10 间的变化。
    /// 注意：Emby 4.10 把插件页 HTML 注入控制台时行内 &lt;script&gt; 不执行，
    /// 所以不能用老写法（data-role="page" + 行内脚本），必须用 data-controller
    /// 声明一个独立 AMD 模块（见 GetPages 的第二个页面）。
    /// </summary>
    public class Plugin : BasePlugin<PluginConfiguration>, IHasWebPages
    {
        public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
            : base(applicationPaths, xmlSerializer)
        {
        }

        public override string Name => "Batch Actors 批量加演员";

        public override Guid Id => Guid.Parse("d45e648c-656d-4382-ab7b-8a919dc4aeed");

        public override string Description =>
            "在插件页里多选电影，一次给多部电影添加演员 / 类型 / 标签 / 工作室 / 年份（追加或替换，可锁定改动字段防刮削覆盖：演员=Cast，类型=Genres，标签=Tags，工作室=Studios；年份无锁定名）。";

        public IEnumerable<PluginPageInfo> GetPages()
        {
            // Emby 4.10 写法（对照 CloudDrive 插件）：
            // HTML 只做片段，JS 是独立的 AMD 控制器。HTML 里用
            // data-controller="__plugin/batchactorsjs" 声明它，这里再把 JS
            // 注册成第二个（不进菜单的）页面；只注册 HTML、不注册 JS 的话，
            // 页面在控制台里根本挂不起来、整页空白。
            return new[]
            {
                new PluginPageInfo
                {
                    // Emby 打开方式：
                    // /web/index.html#!/configurationpage?name=BatchActors
                    Name = "BatchActors",
                    EmbeddedResourcePath = GetType().Namespace + ".Configuration.batchactors.html",
                    IsMainConfigPage = true,
                    EnableInMainMenu = true
                },
                new PluginPageInfo
                {
                    Name = "batchactorsjs",
                    EmbeddedResourcePath = GetType().Namespace + ".Configuration.batchactors.js"
                }
            };
        }
    }
}
