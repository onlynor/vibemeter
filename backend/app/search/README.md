# 搜索检索层（app.search）

给 LLM 补充**事件背景**的网页检索层，与 `app.crawlers` 并列但职责不同：

| | `app.crawlers` | `app.search` |
|---|---|---|
| 取什么 | 网友评论 | 网页检索结果（标题 + 摘要） |
| 产物性质 | 主观观点 | 客观描述 |
| 是否进情感分析 | **是** | **否** |
| 落点 | `comments` 表 → SnowNLP | `summary.search_results` → LLM 上下文 / 前端展示 |

> 检索结果刻意不并入评论流。标题和摘要是对事件的客观描述而非网友观点，
> 喂进 SnowNLP 会以接近中性的分数稀释真实的情感分布——知乎热榜标题曾经
> 就是这么污染结果的。要改这条约定前请先想清楚这一点。

## 新增一个 provider

只需在本目录下新建一个文件，**不需要修改任何既有代码**（注册表会自动发现）。

```python
# app/search/sogou.py
from app.crawlers.http_utils import fetch_text, make_client
from app.search.base import ResultSpec, SearchProvider, parse_results
from app.search.registry import register_provider

SOGOU_SPEC = ResultSpec(
    container=".vrwrap",         # 每条结果的容器
    title="h3",
    link="h3 a",
    snippet=(".text-layout", ".fz-mid"),   # 按顺序取第一个非空
    ad_href_markers=("/gg/",),             # 命中即判为广告并跳过
)


@register_provider
class SogouSearchProvider(SearchProvider):
    name = "sogou"          # 必须唯一，重名会在注册时报错
    label = "搜狗搜索"

    async def search(self, query: str, *, limit: int):
        async with make_client(referer="https://www.sogou.com/") as client:
            html = await fetch_text(
                client, "https://www.sogou.com/web", params={"query": query},
            )
        if not html:
            raise RuntimeError("搜狗检索无响应")
        return parse_results(html, SOGOU_SPEC, self.name, limit)
```

就这样。`search_all()` 下次调用时会自动带上它，前端的可用性检测、结果卡片、
LLM 上下文也都会自动包含，无需改动。前端若要让用户单独勾选它，只需在
`frontend/src/state/analysisForm.ts` 的 `SOURCES` 里加一行，把 `provider`
填成这里的 `name`。

### 约定

- **只管抛异常**。超时、异常隔离、状态汇报都由 `registry` 统一处理；
  单个 provider 失败只会把自己标成不可用，不影响其它 provider 和整个任务。
- **复用 HTTP 工具**。用 `app.crawlers.http_utils` 的 `make_client` /
  `fetch_text` / `fetch_json`，它们已经处理了 UA 轮换、重试退避，并且固定
  `trust_env=False`（本项目一律直连，不走环境变量里的代理）。
- **别自己写解析循环**。绝大多数引擎只是选择器不同，用 `ResultSpec` +
  `parse_results` 即可；广告过滤、跳转地址还原、去重、rank 编号都在里面。
  只有结构特殊到 spec 表达不了时才自己解析，且仍要返回 `SearchResult`。
- **rank 从 1 起**，表示在**该 provider 自身**结果里的名次；广告被跳过时
  不占名次。跨 provider 的 rank 没有可比性，聚合层是轮转合并而不是按 rank 排序。
- **不必自己去重**。`search_all` 合并时会按归一化 URL（忽略协议 / `www.` /
  结尾斜杠）与归一化标题跨引擎去重——多引擎并联后前几条成对重复是常态，
  不去重等于把 LLM 的背景资料预算浪费一半。`limit` 是单引擎上限，
  `total_limit` 才是合并去重后的总量上限。

### ResultSpec 字段

| 字段 | 说明 |
|---|---|
| `container` | 每条结果的容器选择器 |
| `title` / `link` | 容器内的标题节点、链接节点（取 `href`） |
| `snippet` | 摘要候选选择器，按顺序取第一个非空；全落空时退化为"容器全文去掉标题" |
| `real_url_attr` | 真实地址所在的容器属性（百度是 `mu`），优先于 `href` 里的跳转链接 |
| `placeholder_url_markers` | `real_url_attr` 命中这些片段说明是占位地址，退回 `href` |
| `ad_href_markers` | `href` 命中即判为广告 |
| `ad_attrs` | 容器上存在这些属性即判为广告 |

## 百度实现要点

- 必须先访问一次 `www.baidu.com` 拿 `BAIDUID` 再检索。直连 `/s` 只能拿到
  7 个左右的容器且多为卡片；带 Cookie 后是完整一页（实测 20 容器 / 19 自然结果）。
- 广告与自然结果的区别在跳转域名：广告 `baidu.php?url=`，自然结果 `link?url=`。
- 真实地址在容器的 `mu` 属性上；百度自家卡片会写成 `nourl.ubs.baidu.com`
  这种占位值，已在 spec 里标为 placeholder 并退回 `href`。

## 必应实现要点

- 结果容器 `li.b_algo`，广告在 `li.b_ad` 里，选择器本身就排除了广告；
  `ad_href_markers` 只是对漏进来的 `/aclick?` 兜底。
- 多数结果 `h2 a[href]` 就是真实地址；少数包成
  `bing.com/ck/a?...&u=a1<base64url>`，`_resolve_redirect` 就地解开，解不开
  则退回原链接而不是丢掉这条结果。
- `ensearch=0` 保证走中文界面。不带这个参数在部分出口 IP 上会返回英文页，
  摘要语言与评论语料对不上，LLM 读起来是割裂的。
- 存在的意义不只是"多一个源"：百度高频检索会弹安全验证，一旦触发检索增强
  整段消失；必应风控宽松得多，两者并联后单边被限流时仍有背景资料可用。

## 文本归一化

`clean_text` 会删掉**夹在两个汉字之间**的空格。引擎把查询词包成
`<strong>`，节点文本一旦带分隔符取出就会变成「小米汽车 （ 小米汽车 科技
有限公司）」。中文本来不用空格分词，这类空格一律是标签边界的产物。
字母之间的空格保留（`AI 技术`、`Xiaomi SU7` 不受影响）。

摘要还会剥掉开头的时间前缀（`2026年1月2日 ·`、`15 小时之前 ·`）与结尾的
`百度快照`：对"这条结果讲了什么"没有信息量，却会占掉 LLM 的上下文预算。

## 测试

```bash
backend/.venv/bin/python tests/test_search.py
```

覆盖解析（含广告过滤、占位地址、去重、rank 连续性）、统一模型校验、
provider 注册（含重名冲突）、以及聚合层的失败隔离、超时隔离与轮转合并。
解析用内联 HTML 夹具，聚合用桩 provider，**不依赖网络**。
