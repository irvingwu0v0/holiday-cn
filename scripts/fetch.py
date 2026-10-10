#!/usr/bin/env python3
"""Fetch holidays from gov.cn"""

import argparse
import functools
import json
import re
from datetime import date, timedelta
from itertools import chain
from typing import Iterator, List, Optional, Tuple

import bs4
import requests

PAPER_EXCLUDE = [
    "http://www.gov.cn/zhengce/zhengceku/2014-09/29/content_9102.htm",
    "http://www.gov.cn/zhengce/zhengceku/2015-02/09/content_9466.htm",
]
PAPER_INCLUDE = {
    2015: ["http://www.gov.cn/zhengce/zhengceku/2015-05/13/content_9742.htm"]
}

PRE_PARSED_PAPERS = {
    "http://www.gov.cn/zhengce/zhengceku/2015-05/13/content_9742.htm": [
        {
            "name": "抗日战争暨世界反法西斯战争胜利70周年纪念日",
            "date": date(2015, 9, 3),
            "isOffDay": True,
        },
        {
            "name": "抗日战争暨世界反法西斯战争胜利70周年纪念日",
            "date": date(2015, 9, 4),
            "isOffDay": True,
        },
        {
            "name": "抗日战争暨世界反法西斯战争胜利70周年纪念日",
            "date": date(2015, 9, 5),
            "isOffDay": True,
        },
        {
            "name": "抗日战争暨世界反法西斯战争胜利70周年纪念日",
            "date": date(2015, 9, 6),
            "isOffDay": False,
        },
    ],
    "http://www.gov.cn/zhengce/zhengceku/2020-01/27/content_5472352.htm": [
        {
            "name": "春节",
            "date": date(2020, 1, 31),
            "isOffDay": True,
        },
        {
            "name": "春节",
            "date": date(2020, 2, 1),
            "isOffDay": True,
        },
        {
            "name": "春节",
            "date": date(2020, 2, 2),
            "isOffDay": True,
        },
        {
            "name": "春节",
            "date": date(2020, 2, 3),
            "isOffDay": False,
        },
    ],
    "https://www.xizang.gov.cn/xwzx_406/bmkx/202602/t20260214_525301.html": [
        {
            "name": "春节、藏历新年",
            "date": date(2026, 2, 14),
            "isOffDay": False,
        },
        *[
            {
                "name": "春节、藏历新年",
                "date": date(2026, 2, 15) + timedelta(days=i),
                "isOffDay": True,
            }
            for i in range(12)
        ],
        {
            "name": "春节、藏历新年",
            "date": date(2026, 2, 28),
            "isOffDay": False,
        },
    ],
}

REGIONS = ["xinjiang", "ningxia", "guangxi", "xizang", "neimenggu"]

REGIONAL_PAPERS = {
    "xinjiang": {
        2026: [
            "http://www.xinjiang.gov.cn/xinjiang/tzgg/202512/aaece21b6906443e8d50b981070764a8.shtml"
        ]
    },
    "ningxia": {
        2026: ["https://www.nx.gov.cn/zwgk/qzfwj/202512/t20251216_5110308.html"]
    },
    "guangxi": {2026: ["http://www.gxzf.gov.cn/gggs/t27317475.shtml"]},
    "xizang": {
        2026: ["https://www.xizang.gov.cn/xwzx_406/bmkx/202602/t20260214_525301.html"]
    },
    "neimenggu": {},
}


def _raise_for_status_200(resp: requests.Response):
    resp.raise_for_status()
    if resp.status_code != 200:
        raise requests.HTTPError(
            "request failed: %d: %s" % (resp.status_code, resp.request.url),
            response=resp,
        )


def _get_paper_urls(year: int) -> Iterator[str]:
    has_next_page = True
    page_index = 0
    while has_next_page:
        resp = requests.get(
            "https://sousuo.www.gov.cn/search-gov/data",
            params={
                "t": "zhengcelibrary_gw",
                "p": page_index,
                "n": 5,
                "q": "假期 %d" % (year,),
                "pcodeJiguan": "国办发明电",
                "puborg": "国务院办公厅",
                "filetype": "通知",
                "sort": "pubtime",
            },
        )
        _raise_for_status_200(resp)
        data = resp.json()
        if data["code"] == 1001:
            # no match
            return
        assert data["code"] == 200, "%s: %s: %s" % (
            resp.url,
            data["code"],
            data["msg"],
        )
        for i in data["searchVO"]["listVO"]:
            if str(year) in i["title"]:
                yield i["url"]
        page_index += 1
        has_next_page = page_index < data["searchVO"]["totalpage"]


def get_paper_urls(year: int) -> List[str]:
    """Find year related paper urls.

    Args:
        year (int): eg. 2018

    Returns:
        List[str]: Urls， sort by publish time.
    """

    ret = [i for i in _get_paper_urls(year) if i not in PAPER_EXCLUDE]
    ret += PAPER_INCLUDE.get(year, [])
    ret.sort()
    if not ret and date.today().year >= year:
        raise RuntimeError("could not found papers for %d" % (year,))
    return ret


@functools.lru_cache()
def get_paper(url: str) -> str:
    """Extract paper text from url.

    Args:
        url (str): Paper url.

    Returns:
        str: Extracted paper text.
    """

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
            " like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, verify=False, timeout=15)
    _raise_for_status_200(response)
    response.encoding = "utf-8"
    soup = bs4.BeautifulSoup(response.text, features="html.parser")
    container = (
        soup.find(id="UCAP-CONTENT")
        or soup.find(id="NewsContent")
        or soup.find(id="info_content")
        or soup.find(class_="pages_content")
        or soup.find(class_="article-center")
        or soup.find("div", class_="article-content")
    )
    assert isinstance(
        container, bs4.Tag
    ), f"Can not get paper container from url: {url}"
    p = bs4.BeautifulSoup(
        container.decode().replace("<br/>", "</p><p>"), features="html.parser"
    ).find_all("p")
    ret = "\n".join((i.get_text().strip() for i in p if i.get_text().strip()))
    assert ret, f"can not get paper content from url: {url}"
    return ret


def get_rules(paper: str) -> Iterator[Tuple[str, str]]:
    """Extract rules from paper.

    Args:
        paper (str): Paper text

    Raises:
        NotImplementedError: When find no rules.

    Returns:
        Iterator[Tuple[str, str]]: (name, description)
    """

    lines: list = paper.splitlines()
    lines = sorted(set(lines), key=lines.index)
    count = 0
    for i in chain(get_normal_rules(lines), get_patch_rules(lines)):
        count += 1
        yield i
    if not count:
        raise NotImplementedError(lines)


def get_normal_rules(lines: Iterator[str]) -> Iterator[Tuple[str, str]]:
    """Get normal holiday rule for a year

    Args:
        lines (Iterator[str]): paper content

    Returns:
        Iterator[Tuple[str, str]]: (name, description)
    """
    for i in lines:
        match = re.match(r"[一二三四五六七八九十]、(.+?)：(.+)", i)
        if match:
            yield match.groups()


def get_patch_rules(lines: Iterator[str]) -> Iterator[Tuple[str, str]]:
    """Get holiday patch rule for existed holiday

    Args:
        lines (Iterator[str]): paper content

    Returns:
        Iterator[Tuple[str, str]]: (name, description)
    """
    name = None
    for i in lines:
        match = re.match(
            r".*\d+年(?:度)?(?:广西|自治区)?([^和、]{2,}?)(?:假期|放假).*(?:安排|通知)",
            i,
        )
        if match and "节假日" not in match.group(1):
            name = match.group(1)
            if "三月三" in name:
                name = "壮族三月三"
        if not name:
            continue
        match = re.match(r"^[一二三四五六七八九十]、(.+)$", i)
        if not match:
            continue
        description = match.group(1)
        if re.match(r".*\d+月\d+日.*", description):
            yield name, description


def _cast_int(value):
    return int(value) if value else None


class DescriptionParser:
    """Parser for holiday shift description."""

    def __init__(self, description: str, year: int):
        self.description = description
        self.year = year
        self.date_history = list()

    def parse(self) -> Iterator[dict]:
        """Generator for description parsing result.

        Args:
            year (int): Context year
        """

        del self.date_history[:]
        description = re.sub(r"，(?:周末)?正常休息", "正常休息", self.description)
        for i in re.split("[，。；]", description):
            for j in SentenceParser(self, i).parse():
                yield j

        if not self.date_history:
            raise NotImplementedError(self.description)

    def get_date(self, year: Optional[int], month: Optional[int], day: int) -> date:
        """Get date in context.

        Args:
            year (Optional[int]): year
            month (int): month
            day (int): day

        Returns:
            date: Date result
        """

        assert day, "No day specified"

        # Special case: month inherit
        if month is None:
            month = self.date_history[-1].month

        # Special case: 12 month may mean previous year
        if (
            year is None
            and month == 12
            and self.date_history
            and max(self.date_history) < date(year=self.year, month=2, day=1)
        ):
            year = self.year - 1

        year = year or self.year
        return date(year=year, month=month, day=day)


class SentenceParser:
    """Parser for holiday shift description sentence."""

    def __init__(self, parent: DescriptionParser, sentence: str):
        self.parent = parent
        self.sentence = sentence

    def extract_dates(self, text: str) -> Iterator[date]:
        """Extract date from text.

        Args:
            text (str): Text to extract

        Returns:
            Iterator[date]: Extracted dates.
        """

        count = 0
        text = text.replace("(", "（").replace(")", "）")
        for i in chain(
            *(method(self, text) for method in self.date_extraction_methods)
        ):
            count += 1
            is_seen = i in self.parent.date_history
            self.parent.date_history.append(i)
            if is_seen:
                continue
            yield i

        if not count:
            raise NotImplementedError(text)

    def _extract_dates_1(self, value: str) -> Iterator[date]:
        match = re.findall(r"(?:(\d+)年)?(?:(\d+)月)?(\d+)日", value)
        for groups in match:
            groups = [_cast_int(i) for i in groups]
            assert len(groups) == 3, groups
            yield self.parent.get_date(year=groups[0], month=groups[1], day=groups[2])

    def _extract_dates_2(self, value: str) -> Iterator[date]:
        value = re.sub(r"（.+?）", "", value)
        match = re.findall(
            r"(?:(\d+)年)?(?:(\d+)月)?(\d+)日(?:至|-|—)(?:(\d+)年)?(?:(\d+)月)?(\d+)日",
            value,
        )
        for groups in match:
            groups = [_cast_int(i) for i in groups]
            assert len(groups) == 6, groups
            start = self.parent.get_date(year=groups[0], month=groups[1], day=groups[2])
            end = self.parent.get_date(year=groups[3], month=groups[4], day=groups[5])
            for i in range((end - start).days + 1):
                yield start + timedelta(days=i)

    def _extract_dates_3(self, value: str) -> Iterator[date]:
        value = re.sub(r"（.+?）", "", value)
        match = re.findall(
            r"(?:(\d+)年)?(?:(\d+)月)?(\d+)日(?:（[^）]+）)?"
            r"(?:、(?:(\d+)年)?(?:(\d+)月)?(\d+)日(?:（[^）]+）)?)+",
            value,
        )
        for groups in match:
            groups = [_cast_int(i) for i in groups]
            assert not (len(groups) % 3), groups
            for i in range(0, len(groups), 3):
                yield self.parent.get_date(
                    year=groups[i], month=groups[i + 1], day=groups[i + 2]
                )

    date_extraction_methods = [_extract_dates_1, _extract_dates_2, _extract_dates_3]

    def parse(self) -> Iterator[dict]:
        """Parse days with memory

        Args:
            memory (set): Date memory

        Returns:
            Iterator[dict]: Days without name field.
        """
        for method in self.parsing_methods:
            for i in method(self):
                yield i

    def _parse_rest_1(self):
        if self.sentence.startswith("不"):
            return
        match = re.match(
            r"(.+)(放假|补休|调休|公休|正常休息)+(?:\d+天)?$", self.sentence
        )
        if match:
            for i in self.extract_dates(match.group(1)):
                yield {"date": i, "isOffDay": True}

    def _parse_work_1(self):
        match = re.match("(.+)上班$", self.sentence)
        if match:
            for i in self.extract_dates(match.group(1)):
                yield {"date": i, "isOffDay": False}

    def _parse_shift_1(self):
        match = re.match("(.+)调至(.+)", self.sentence)
        if match:
            for i in self.extract_dates(match.group(1)):
                yield {"date": i, "isOffDay": False}
            for i in self.extract_dates(match.group(2)):
                yield {"date": i, "isOffDay": True}

    parsing_methods = [
        _parse_rest_1,
        _parse_work_1,
        _parse_shift_1,
    ]


def parse_paper(year: int, url: str) -> Iterator[dict]:
    """Parse one paper

    Args:
        year (int): Year
        url (str): Paper url

    Returns:
        Iterator[dict]: Days
    """
    if url in PRE_PARSED_PAPERS:
        yield from PRE_PARSED_PAPERS[url]
        return
    paper = get_paper(url)
    rules = get_rules(paper)
    ret = (
        {"name": name, **i}
        for name, description in rules
        for i in DescriptionParser(description, year).parse()
    )
    try:
        for i in ret:
            yield i
    except NotImplementedError as ex:
        raise RuntimeError("Can not parse paper", url) from ex


def fetch_holiday(year: int, region: Optional[str] = None):
    """Fetch holiday data."""
    if region is not None and region not in REGIONS:
        raise ValueError(f"Unknown region: {region}, must be one of {REGIONS}")

    if region is None:
        papers = get_paper_urls(year)
        days = dict()
        for k in (j for i in papers for j in parse_paper(year, i)):
            days[k["date"]] = k
        return {
            "year": year,
            "papers": papers,
            "days": sorted(days.values(), key=lambda x: x["date"]),
        }

    if region in ("xinjiang", "ningxia"):
        papers = REGIONAL_PAPERS[region].get(year, [])
        if not papers:
            raise RuntimeError(f"could not found papers for {year} in {region}")
        days = dict()
        for k in (j for i in papers for j in parse_paper(year, i)):
            days[k["date"]] = k
        return {
            "year": year,
            "papers": papers,
            "days": sorted(days.values(), key=lambda x: x["date"]),
        }

    if region == "guangxi":
        national_data = fetch_holiday(year)
        papers = list(national_data["papers"])
        days = {d["date"]: d for d in national_data["days"]}
        regional_papers = REGIONAL_PAPERS["guangxi"].get(year, [])
        papers.extend(regional_papers)
        for p in regional_papers:
            for k in parse_paper(year, p):
                days[k["date"]] = k
        return {
            "year": year,
            "papers": papers,
            "days": sorted(days.values(), key=lambda x: x["date"]),
        }

    if region == "xizang":
        national_data = fetch_holiday(year)
        papers = list(national_data["papers"])
        regional_papers = REGIONAL_PAPERS["xizang"].get(year, [])
        papers.extend(regional_papers)
        days = {d["date"]: d for d in national_data["days"] if d["name"] != "春节"}
        for p in regional_papers:
            for k in parse_paper(year, p):
                days[k["date"]] = k
        return {
            "year": year,
            "papers": papers,
            "days": sorted(days.values(), key=lambda x: x["date"]),
        }

    if region == "neimenggu":
        national_data = fetch_holiday(year)
        return {
            "year": year,
            "papers": list(national_data["papers"]),
            "days": list(national_data["days"]),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("year", type=int)
    parser.add_argument(
        "--region",
        type=str,
        choices=REGIONS,
        default=None,
        help="Regional holiday to fetch",
    )
    args = parser.parse_args()

    print(
        json.dumps(
            fetch_holiday(args.year, region=args.region),
            indent=4,
            ensure_ascii=False,
            cls=CustomJSONEncoder,
        )
    )


class CustomJSONEncoder(json.JSONEncoder):
    """Custom json encoder."""

    def default(self, o):
        # pylint:disable=method-hidden
        if isinstance(o, date):
            return o.isoformat()

        return super().default(o)


if __name__ == "__main__":
    main()
