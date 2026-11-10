using MediaBrowser.Model.Plugins;

namespace Emby.BatchActors
{
    /// <summary>插件配置（存在 Emby 配置目录的 BatchActors.xml）。</summary>
    public class PluginConfiguration : BasePluginConfiguration
    {
        /// <summary>默认是否锁定演员（LockedFields=Cast）字段，防止以后刷新元数据时把手填演员清掉。</summary>
        public bool LockPeopleFieldByDefault { get; set; } = true;

        /// <summary>默认模式：true=追加，false=替换已有演员。</summary>
        public bool AppendByDefault { get; set; } = true;
    }
}
