import re
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from reader_test_html import nodes
from tools.equipment.wikitext import WikiSubset
from tools.homepage_preview import build
from tools.identity import ROOT, registry


class HomepageIndexTests(unittest.TestCase):
    def test_source_preview_renders_without_local_images_or_activity_snapshot(self):
        with TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            build(site, as_of=date(2026, 11, 21), without_assets=True)
            page = (site / "index.html").read_text("utf8")
            self.assertEqual(list((site / "images").iterdir()), [])
            self.assertIn("td2-icon-placeholder", page)
            self.assertIn('href="weapons.html"', page)
            self.assertIn("—", nodes(page, "td2-home-reading")[0].text)
            self.assertNotIn("homepage-preview-avatar", page)

    def test_homepage_uses_the_game_calendar_and_its_registered_images(self):
        with TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            build(site, as_of=date(2026, 11, 21))
            example = (site / "index.html").read_text("utf8")
            release = (site / "release.html").read_text("utf8")
            empty = (site / "empty.html").read_text("utf8")
            season_art = "TD2-UI-RedHorizon-Background.jpg"
            self.assertTrue((site / "images" / season_art).is_file())
            picture = re.search(r'class="td2-home-season-art"><img[^>]+src="([^"]+)"', release)
            self.assertIn(season_art, picture[1])
            self.assertTrue((site / picture[1]).is_file())
            badge = re.search(r'class="td2-home-season-badge"><img[^>]+src="([^"]+)"', release)
            self.assertIn("TD2-UI-RedHorizon-Icon.png", badge[1])
            self.assertTrue((site / badge[1]).is_file())
            for url in re.findall(r'<img[^>]+src="([^"]+)"', example):
                self.assertTrue((site / url).is_file(), url)
        self.assertEqual(len(nodes(example, "td2-home-news")), 2)
        self.assertNotIn("images/borda-medium.otf", release)
        self.assertEqual(re.sub(r'<style>@font-face\{font-family:"Borda Medium";[^<]*</style>', "", example), release)
        self.assertEqual({node.text for node in nodes(example, "td2-home-news-title")},
                         {"中央公园活动", "“牧羊人”活动", "突击", "肯利学院远征"})
        self.assertNotIn("版本信息", example)
        self.assertNotIn("Y8S3.3", example)
        self.assertFalse(nodes(empty, "td2-home-season-card"))
        self.assertFalse(nodes(empty, "td2-home-story"))
        self.assertEqual([n.text for n in nodes(empty, "td2-home-empty")], ["暂无赛季信息", "暂无活动日程"])
        self.assertEqual(len(nodes(release, "td2-home-statistics")), 1)
        self.assertEqual(nodes(release, "td2-home-followers")[0].text, "关注数:4")
        self.assertIn("TD2-UI-Loadout11-Icon.png", release)
        main, = nodes(release, "td2-home-main")
        edits, comments = main.find_all("td2-home-recent")
        sections = [child for child in main.children if not isinstance(child, str)]
        self.assertIs(sections[sections.index(edits) + 1], comments)
        self.assertTrue(edits.find_all("activityembed-wrapper"))
        self.assertTrue(comments.text.startswith("最新评论"))
        self.assertTrue(comments.find_all("commentsembed-wrapper"))

    def test_native_activity_switches_at_the_exact_utc_second(self):
        wiki = WikiSubset(ROOT)
        def active(when):
            epoch = int(datetime.fromisoformat(when).replace(tzinfo=timezone.utc).timestamp())
            result = wiki.expand("{{#invoke:TD2首页活动|render|时刻=" + str(epoch) + "}}", {})
            cards = nodes(result, "td2-home-story")
            return {c.find_all("td2-home-news-title")[0].text: c for c in cards
                    if "td2-home-event-off" not in c.attrs["class"].split()}
        central = "中央公园活动"
        before = {"黄金子弹", "x5 赛季经验值活动", central}
        after = {"“牧羊人”活动", "肯利学院远征", "突击"}
        self.assertEqual(set(active("2026-11-17T07:59:59")), before)
        current = active("2026-11-17T08:00:00")
        self.assertEqual(set(current), after | {central})
        self.assertEqual(current[central].find_all("td2-home-event-time")[0].text, "7天 0小时")
        self.assertEqual(current[central].find_all("td2-home-event-type")[0].text, "公告")
        self.assertEqual(current["突击"].find_all("td2-home-event-type")[0].text, "全域事件")
        self.assertEqual(current["“牧羊人”活动"].find_all("td2-home-event-type")[0].text, "计划")
        self.assertEqual(current["肯利学院远征"].find_all("td2-home-event-type")[0].text, "赛季活动")
        self.assertEqual(active("2026-11-24T07:59:59")[central].find_all("td2-home-event-time")[0].text, "不足1分钟")
        self.assertEqual(set(active("2026-11-24T07:59:59")), after | {central})
        self.assertEqual(set(active("2026-11-24T08:00:00")), after)
        self.assertEqual(set(active("2026-11-26T07:59:59")), after)
        self.assertFalse(active("2026-11-26T08:00:00"))

    def test_each_news_panel_keeps_its_heading_when_empty(self):
        wiki = WikiSubset(ROOT, today=date(2026, 11, 21))
        current = "{{TD2首页活动|名称=活动甲|开始=2026-11-21|结束=2026-11-21}}"
        expired = current.replace("2026-11-21", "2026-11-20")
        for event, present in [(expired, False), (current, True), ("{{TD2首页活动}}", False)]:
            with self.subTest(event=event):
                markup = wiki.expand("{{TD2首页消息栏|赛季=|活动=" + event + "}}", {})
                self.assertEqual(re.findall("<h2>(.*?)</h2>", markup), ["赛季信息", "活动日程"])
                self.assertEqual([n.text for n in nodes(markup, "td2-home-empty")], ["暂无赛季信息", "暂无活动日程"])
                self.assertEqual(bool(nodes(markup, "td2-home-story")), present)

    def test_season_ring_fills_as_the_remaining_time_decreases(self):
        wiki = WikiSubset(ROOT)
        start, end = 1787817600, 1795680000
        def season(now):
            return wiki.expand("{{#invoke:TD2首页赛季|render|时刻=" + str(now) + "}}", {})
        upcoming, = nodes(season(start - 1), "td2-home-season-card")
        self.assertIn('<time datetime="2026-11-26T08:00:00Z">11月26日 16:00 结束（北京时间）</time>', season(start))
        self.assertIn("td2-home-season-off", upcoming.attrs["class"])
        self.assertEqual(upcoming.find_all("td2-home-ring")[0].attrs["style"], "--td2-home-arc:0.0000deg")
        for now, arc, reading in [(start, 0, "13周 0日 0时"), (start + (end - start) // 4, 90, "9周 5日 6时"),
                                  ((start + end) // 2, 180, "6周 3日 12时"),
                                  (end - 1, 360 - 360 / (end - start), "0周 0日 0时")]:
            card, = nodes(season(now), "td2-home-season-card")
            self.assertNotIn("td2-home-season-off", card.attrs["class"])
            self.assertEqual(card.find_all("td2-home-season-name")[0].text, "Y8S3 · 红色地平线")
            self.assertEqual(card.find_all("td2-home-season-time")[0].text, reading)
            ring, = card.find_all("td2-home-ring")
            self.assertEqual(ring.attrs["style"], f"--td2-home-arc:{arc:.4f}deg")
            self.assertEqual("td2-home-ring-filled" in ring.attrs["class"].split(), now > start)
        self.assertEqual(season(end), "")

    def test_scheduled_events_include_both_boundary_dates_and_overlap(self):
        def event(name, start, end):
            return ("{{TD2首页活动|名称=" + name + "|图片=cover.jpg|开始=" + start +
                    "|结束=" + end + "|来源=https://example.org/news}}")
        schedule = event("甲", "2026-11-10", "2026-11-24") + event("乙", "2026-11-17", "2026-11-26")
        for day, names in [(9, []), (10, ["甲"]), (17, ["甲", "乙"]), (24, ["甲", "乙"]),
                           (25, ["乙"]), (26, ["乙"]), (27, [])]:
            with self.subTest(day=day):
                wiki = WikiSubset(ROOT, today=date(2026, 11, day))
                markup = wiki.expand(schedule, {})
                cards = nodes(markup, "td2-home-story")
                stories = [c for c in cards if "td2-home-event-off" not in c.attrs["class"].split()]
                self.assertEqual(markup.count("[[File:cover.jpg|640px|link=|alt=]]"), len(cards))
                self.assertEqual(len(cards) - len(stories), int(day < 10) + int(day < 17))
                if day == 9:
                    self.assertEqual([(int(c.attrs["data-start"]), int(c.attrs["data-end"])) for c in cards],
                                     [(1794268800, 1795564800), (1794873600, 1795737600)])
                self.assertEqual([s.find_all("td2-home-news-title")[0].text for s in stories],
                                 ["[https://example.org/news " + n + "]" for n in names])
                ends = {"甲": 25, "乙": 27}
                self.assertEqual([s.find_all("td2-home-event-time")[0].text for s in stories],
                                 [f"{ends[n] - day}天 0小时" for n in names])
        prior = WikiSubset(ROOT, today=date(2026, 11, 9))
        self.assertFalse(nodes(prior.expand(event("倒置", "2026-11-12", "2026-11-10"), {}), "td2-home-story"))

    def test_masthead_uses_the_english_logo_with_a_chinese_accessible_name(self):
        rows = {row["id"]: row for row in registry(ROOT)}
        source = (ROOT / rows["td2-home"]["source"]).read_text(encoding="utf-8")
        title, = re.findall(r"<h1>(.*?)</h1>", source, re.S)
        file_title = rows["site-logo-division2-en"]["title"]
        options = re.fullmatch(r"\[\[" + re.escape(file_title) + r"\|([^\[\]]+)\]\]", title)
        self.assertIsNotNone(options)
        self.assertIn("link=", options[1].split("|"))
        self.assertIn("alt=全境封锁2", options[1].split("|"))
        self.assertNotRegex(source, r"(?i)\[\[(?:特殊:搜索|special:search)\b|<inputbox\b")

    def test_home_tiles_point_to_whole_indexes_and_preserve_navbox_groups(self):
        wiki = WikiSubset(ROOT)
        rows = {row["id"]: row for row in registry(ROOT)}
        navigation = wiki.template("TD2首页导航", {})
        labels = [n.text for n in nodes(navigation, "td2-navbox-name")]
        self.assertEqual(labels, ["[[装备索引|装备]]", "[[武器索引|武器]]", "天赋", "技能", "获取与制作",
                                  "专精", "玩法与活动", "世界资料", "实用工具", "感谢名单"])
        self.assertEqual(len(nodes(navigation, "td2-navbox-card")), 2)
        self.assertEqual(len(nodes(navigation, "td2-home-spare")), 3)
        self.assertFalse(nodes(navigation, "td2-navbox"))
        for tile in nodes(navigation, "td2-home-tile"):
            self.assertEqual(len(tile.find_all("td2-corner-node")), 4)

        pairs = (("equipment-index", "equipment-navbox", {"brands", "gear_sets", "named", "exotics"}),
                 ("weapon-index", "weapon-navigation", {"normal", "named", "exotics", "signature"}))
        for index_id, nav_id, groups in pairs:
            with self.subTest(index=index_id):
                index = rows[index_id]
                indexed = wiki.expand((ROOT / index["source"]).read_text("utf8"), {})
                panels = nodes(indexed, "td2-navbox-panel")
                destinations = {p.attrs["id"]: p for p in panels if "id" in p.attrs}
                self.assertEqual(set(destinations), {"td2-index-" + group for group in groups})
                for panel in destinations.values():
                    self.assertTrue(panel.find_all("td2-navbox-card"))
                ordinary = wiki.template(rows[nav_id]["title"].split(":", 1)[1], {})
                self.assertNotIn('id="td2-index-', ordinary)
                self.assertEqual(re.findall(r'data-target="([^"]+)"', ordinary),
                                 re.findall(r'data-target="([^"]+)"', indexed))

    def test_statistics_use_the_next_power_of_two_and_preserve_an_unknown_count(self):
        wiki = WikiSubset(ROOT)
        def counts(pages, edits, followers=""):
            return wiki.expand("{{#invoke:TD2首页统计|render|页面数=" + pages +
                               "|编辑数=" + edits + "|关注数=" + followers + "}}", {})
        sample = counts("1，716", "3,851")
        self.assertEqual([n.attrs["style"] for n in nodes(sample, "td2-home-ring")],
                         ["--td2-home-arc:338.4668deg", "--td2-home-arc:301.6406deg"])
        dial, = nodes(sample, "td2-home-dial")
        reading, = dial.find_all("td2-home-reading")
        self.assertEqual(reading.text, "编辑数3851页面数1716")
        self.assertEqual(reading.find_all("td2-home-edits")[0].attrs["title"], "编辑数 3851 / 4096")
        self.assertNotRegex(sample, "[,，]")
        self.assertEqual(dial.text, reading.text)
        self.assertEqual(len(dial.find_all("td2-home-ring-filled")), 2)
        self.assertTrue(all(r.attrs.get("aria-hidden") == "true" for r in dial.find_all("td2-home-ring")))
        boundary = counts("0", "16", "0")
        self.assertEqual(nodes(boundary, "td2-home-followers")[0].text, "关注数:0")
        rings = nodes(boundary, "td2-home-ring")
        self.assertEqual(rings[0].attrs["style"], "--td2-home-arc:180.0000deg")
        self.assertEqual(rings[1].attrs["style"], "--td2-home-arc:0.0000deg")
        self.assertNotIn("td2-home-ring-filled", rings[1].attrs["class"])
        unknown = counts("", "未取得")
        self.assertEqual(nodes(unknown, "td2-home-followers")[0].text, "关注数:—")
        self.assertFalse(nodes(unknown, "td2-home-ring-filled"))
        self.assertTrue(all("style" not in r.attrs for r in nodes(unknown, "td2-home-ring")))
        self.assertEqual(nodes(unknown, "td2-home-reading")[0].text, "编辑数—页面数—")
        large = counts("12", "12,345,678")
        self.assertIn("--td2-digits:8", large)
        self.assertEqual(nodes(large, "td2-home-reading")[0].text, "编辑数12345678页面数12")
