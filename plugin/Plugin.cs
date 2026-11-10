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
    /// 真正的批量写入在 Configuration/batchactors.html 的 JS 里，
    /// 直接调 Emby 自带 REST API，避开内部 API 在 4.9 -> 4.10 间的变化。
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
            return new[]
            {
                new PluginPageInfo
                {
                    // Emby 打开方式：
                    // /web/index.html#!/configurationpage?name=BatchActors
                    Name = "BatchActors",
                    EmbeddedResourcePath = GetType().Namespace + ".Configuration.batchactors.html",
                    EnableInMainMenu = true
                }
            };
        }
    }
}
