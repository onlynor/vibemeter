"""评论清洗与数据质量测试

不依赖网络。运行： backend/.venv/bin/python tests/test_preprocess.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.preprocess import (
    clean_comment,
    dedup_key,
    is_meaningful,
    preprocess_comments,
)


def test_markup_and_data_uri_stripped():
    """内联 base64 图片曾被当成一条负向评论计入分布"""
    blob = (
        '<img class="BDE_Image" src="data:image/jpeg;base64,'
        '/9j/4AAQSkZJRgABAQAQABAAD/2wBDAAgGBgcGBQgHBwcJ" >这张图说明问题'
    )
    assert clean_comment(blob) == "这张图说明问题", repr(clean_comment(blob))
    # 转义过的标签同样要处理，否则标签正则匹配不到。
    # 标签替换成空格而非删除：<br> 两侧本就是两句话，粘起来会造出假词。
    assert clean_comment("&lt;b&gt;加粗&lt;/b&gt;内容") == "加粗 内容"
    # 但正常的小于号不能误伤
    assert "3<5" in clean_comment("我觉得 3<5 是对的")
    assert clean_comment("<3 这个梗") == "<3 这个梗"
    print("  markup / data URI OK")


def test_noise_removal():
    assert clean_comment("回复 张三：说得对") == "说得对"
    assert clean_comment("看这里 https://t.cn/abc 很好") == "看这里 很好"
    assert clean_comment("@某某 你怎么看") == "你怎么看"
    assert clean_comment("#热搜话题# 讨论一下") == "讨论一下"
    assert clean_comment("真好[doge][二哈]") == "真好"
    assert clean_comment("好好好好好看") == "好看", clean_comment("好好好好好看")
    print("  noise removal OK")


def test_near_duplicate_dedup():
    """只按完整字符串去重时，同一句话配不同标点会各占一条"""
    assert dedup_key("太好了！！！") == dedup_key("太好了。")
    assert dedup_key("Good ") == dedup_key("good")
    assert dedup_key("说得对") != dedup_key("说得不对")

    out = preprocess_comments([
        "这个产品真的很不错",
        "这个产品真的很不错！",
        "这个产品真的很不错。。。",
        "这个产品真的很不错 ",
        "这个产品确实一般",
    ])
    print(f"  dedup -> {out}")
    assert len(out) == 2, out
    print("  near-duplicate dedup OK")


def test_promo_filtered_but_normal_mentions_kept():
    """引流评论要滤掉，正常提到微信/QQ 的讨论不能一起被滤"""
    dropped = [
        "加微信 abc123 领取资料",
        "扫码进群一起讨论",
        "私信我领福利",
        "点击链接查看详情",
        "微信号：superdeal2026",
        "长期收人，日结",
    ]
    kept = [
        "微信支付比支付宝方便一点",
        "我在QQ空间看到过这个",
        "这个功能微信早就有了",
    ]
    out = preprocess_comments(dropped + kept)
    print(f"  kept -> {out}")
    assert len(out) == len(kept), out
    for text in kept:
        assert text in out, f"正常讨论被误删: {text}"
    print("  promo filter OK")


def test_meaningfulness():
    assert is_meaningful("不错")
    assert is_meaningful("ok")
    assert not is_meaningful("！")
    assert not is_meaningful("")
    assert not is_meaningful("  ")
    # 饭圈短评被过滤
    assert preprocess_comments(["哥哥好帅", "剧情节奏把控得很好"]) == ["剧情节奏把控得很好"]
    print("  meaningfulness OK")


def test_order_preserved():
    """去重保留首次出现的写法与顺序，代表性评论才不会错位"""
    out = preprocess_comments(["第一条评论", "第二条评论", "第一条评论！", "第三条评论"])
    assert out == ["第一条评论", "第二条评论", "第三条评论"], out
    print("  order OK")


def main() -> None:
    for fn in (
        test_markup_and_data_uri_stripped,
        test_noise_removal,
        test_near_duplicate_dedup,
        test_promo_filtered_but_normal_mentions_kept,
        test_meaningfulness,
        test_order_preserved,
    ):
        print(f"{fn.__name__}:")
        fn()
    print("\nALL PASS")


main()
