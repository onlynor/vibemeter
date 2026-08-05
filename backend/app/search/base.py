"""搜索引擎检索层的公共抽象

与 ``app.crawlers`` 的分工：爬虫负责取**评论**（人对话题的观点，会进情感
分析），本层负责取**网页检索结果**（标题 + 摘要，只做 LLM 上下文与展示）。
两者的产物性质不同，合并的位置也不同，详见 ``app/search/README.md``。
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

from bs4 import BeautifulSoup


# ping() 的返回：(是否可用, 面向用户的中文说明)
PingResult = tuple[bool, str]

_WS_RE = re.compile(r"\s+")

# 中日韩字符区间（含全角标点），用于识别"这个空格夹在两个汉字之间"
_CJK = (
    "⺀-〿"   # CJK 部首补充 + 中文标点
    "㐀-䶿"   # 扩展 A
    "一-鿿"   # 基本区
    "豈-﫿"   # 兼容表意文字
    "︰-﹏"   # CJK 兼容形式
    "＀-￯"   # 全角字符
)
# 夹在两个汉字之间的空格。搜索引擎会把查询词包成 <strong>，节点文本一旦
# 用带分隔符的方式取出来就会变成"小米汽车 （ 小米汽车 科技有限公司）"。
# 中文本来不用空格分词，这类空格一律是标签边界的产物，删掉即可。
_CJK_GAP_RE = re.compile(f"(?<=[{_CJK}])[ \t]+(?=[{_CJK}])")

# 摘要里的时间前缀与快照后缀：对"这条结果讲了什么"没有信息量，
# 却会占掉 LLM 上下文，还会让同一条新闻在不同引擎下看起来不一样。
_SNIPPET_NOISE_RE = [
    re.compile(r"^\d{4}年\d{1,2}月\d{1,2}日\s*[·•\-—]?\s*"),
    re.compile(r"^\d+\s*(?:秒|分钟|小时|天|周|个月|年)之?前\s*[·•\-—]?\s*"),
    re.compile(r"\s*百度快照\s*$"),
]


def clean_text(value: object) -> str:
    """把节点文本压成单行，去掉零宽字符与多余空白"""
    text = str(value or "").replace("​", " ").replace("\xa0", " ")
    text = _WS_RE.sub(" ", text).strip()
    return _CJK_GAP_RE.sub("", text)


def _node_text(node) -> str:
    """取节点文本，且**不**在标签边界插入分隔符

    ``get_text(" ")`` 会在每个子标签处插一个空格，而标题、摘要里几乎必然
    有 ``<strong>关键词</strong>``，插出来的空格会把中文词切碎。这里按原文
    拼接，真正的空白交给 ``clean_text`` 压平。
    """
    return clean_text(node.get_text())


def strip_snippet_noise(text: str) -> str:
    """去掉摘要首尾的时间戳、快照等模板文字"""
    for pattern in _SNIPPET_NOISE_RE:
        text = pattern.sub("", text)
    return text.strip()


@dataclass(frozen=True, slots=True)
class SearchResult:
    """各搜索引擎统一的结果模型

    ``source`` 存 provider 的 ``name``（baidu / bing / ...），``rank`` 从 1 起，
    表示在**该 provider 自己的结果列表**中的名次；跨 provider 的排名没有可比性，
    聚合时不要拿它做全局排序。
    """

    title: str
    url: str
    snippet: str
    source: str
    rank: int

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
            "rank": self.rank,
        }

    @classmethod
    def build(
        cls,
        *,
        title: object,
        url: object,
        snippet: object,
        source: str,
        rank: int,
    ) -> "SearchResult | None":
        """规范化并校验，拿不到标题或 http(s) 链接就返回 None

        由构造入口统一兜底，各 provider 的解析代码就不必各写一遍校验。
        """
        title_text = clean_text(title)
        url_text = clean_text(url)
        if not title_text or not url_text:
            return None
        if not url_text.startswith(("http://", "https://")):
            return None
        return cls(
            title=title_text,
            url=url_text,
            snippet=clean_text(snippet),
            source=source,
            rank=rank,
        )


@dataclass(frozen=True, slots=True)
class ResultSpec:
    """一套 CSS 选择器，描述某个引擎的结果页长什么样

    新增引擎通常只是换一组选择器，不需要再写一份解析循环——解析逻辑集中在
    ``parse_results`` 里，避免每个 provider 复制粘贴一遍 BeautifulSoup 代码。
    """

    # 每条结果的容器
    container: str
    # 容器内的标题节点（取文本）与链接节点（取 href）
    title: str
    link: str
    # 摘要候选选择器，按顺序命中第一个非空的
    snippet: Sequence[str] = ()
    # 真实目标地址所在的容器属性（百度是 mu），优先于 href 里的跳转链接
    real_url_attr: str | None = None
    # real_url_attr 里出现这些片段说明是占位地址（百度自家卡片会写
    # nourl.ubs.baidu.com），此时退回 href，否则会给出一个打不开的链接
    placeholder_url_markers: Sequence[str] = ()
    # href 里出现这些片段即判定为广告，直接丢弃
    ad_href_markers: Sequence[str] = ()
    # 容器上出现这些属性即判定为广告
    ad_attrs: Sequence[str] = ()


def _extract_snippet(node, spec: ResultSpec, title_text: str) -> str:
    """按候选选择器取摘要，都落空时退化为"容器全文去掉标题"""
    for selector in spec.snippet:
        found = node.select_one(selector)
        if found:
            text = strip_snippet_noise(_node_text(found))
            if text:
                return text
    # 兜底路径跨越块级元素，这里反而需要分隔符，否则相邻段落会粘成一个词
    whole = clean_text(node.get_text(" ", strip=True))
    if title_text and whole.startswith(title_text):
        whole = whole[len(title_text):]
    return strip_snippet_noise(clean_text(whole))


def _is_ad(node, href: str, spec: ResultSpec) -> bool:
    if any(marker in href for marker in spec.ad_href_markers):
        return True
    return any(node.get(attr) is not None for attr in spec.ad_attrs)


def parse_results(html: str, spec: ResultSpec, source: str, limit: int) -> list[SearchResult]:
    """按 spec 从结果页 HTML 中解析出统一的 SearchResult 列表

    广告会被跳过，且**跳过的条目不占用 rank**——rank 表示自然结果的名次，
    若把广告算进去，同一个词在投放前后拿到的 rank 会不一致。
    """
    soup = BeautifulSoup(html or "", "html.parser")
    results: list[SearchResult] = []
    seen_urls: set[str] = set()

    for node in soup.select(spec.container):
        if len(results) >= limit:
            break
        link = node.select_one(spec.link)
        if link is None:
            continue
        href = clean_text(link.get("href"))
        if _is_ad(node, href, spec):
            continue

        title_node = node.select_one(spec.title)
        title_text = _node_text(title_node or link)

        url = href
        if spec.real_url_attr:
            # 引擎大多把 href 写成自家跳转链接，真实地址挂在属性上
            real = clean_text(node.get(spec.real_url_attr))
            is_placeholder = any(
                marker in real for marker in spec.placeholder_url_markers
            )
            if real.startswith(("http://", "https://")) and not is_placeholder:
                url = real

        result = SearchResult.build(
            title=title_text,
            url=url,
            snippet=_extract_snippet(node, spec, title_text),
            source=source,
            rank=len(results) + 1,
        )
        if result is None or result.url in seen_urls:
            continue
        seen_urls.add(result.url)
        results.append(result)

    return results


class SearchProvider(ABC):
    """搜索引擎 provider 的抽象接口

    子类只需声明 ``name`` / ``label`` 并实现 ``search()``；用
    ``@register_provider`` 装饰即可被聚合层自动发现，无需改动任何既有代码。
    """

    name: str = "base"
    label: str = "基础"
    # 该引擎单次检索的默认条数
    default_limit: int = 10

    @abstractmethod
    async def search(self, query: str, *, limit: int) -> list[SearchResult]:
        """执行一次检索，返回统一模型的结果列表

        实现方只管抛异常，超时、隔离与降级由聚合层统一处理。
        """
        raise NotImplementedError

    async def ping(self) -> PingResult:
        """轻量可用性探测，默认用一次真实检索代替"""
        try:
            results = await self.search("新闻", limit=1)
        except Exception as exc:
            return False, f"{self.label}检索失败：{exc}"
        if not results:
            return False, f"{self.label}可达但未解析出结果（页面结构可能已调整）"
        return True, f"{self.label}检索可用"
