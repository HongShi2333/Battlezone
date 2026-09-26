# 外部枪械模型

本目录的运行时缓存 (`cache/`) **不会**提交进仓库。

游戏会按 `render/gun_packs.py` 里的索引, 从下面两个上游仓库拉取 Bedrock `geo.json` 与贴图, 缓存在本地后渲染:

| 来源 | 仓库 | 资源协议 |
|---|---|---|
| TACZ | https://github.com/MCModderAnchor/TACZ | 代码 GPL-3.0; **模型与贴图 CC BY-NC-ND 4.0** |
| SuperbWarfare | https://github.com/Mercurows/SuperbWarfare | 代码 GPL-3.0; **模型与贴图由制作组保留所有权利** |

这些美术资源不允许随本项目再分发, 所以只在玩家本机缓存, 并在界面上署名。

## 离线 / 自备文件

任选其一:

* 把文件放到 `assets/gunpacks/cache/<pack>/<name>.geo.json` 与同名 `.png`
* 或设置 `BATTLEZONE_GUNPACKS` 指向同样布局的目录
* 或克隆上游仓库后设置:
  * `BATTLEZONE_TACZ` = TACZ 仓库根目录
  * `BATTLEZONE_SW` = SuperbWarfare 仓库根目录

手动预下载:

```bash
python tools/fetch_gun_models.py
```

GitHub API 未登录时每小时限额较低。可设置 `GITHUB_TOKEN` 或 `GH_TOKEN` 提高限额。拉取失败时该武器自动回退到程序化模型, 游戏仍可运行。
