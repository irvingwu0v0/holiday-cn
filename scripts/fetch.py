#!/usr/bin/env python3
"""Fetch holidays from gov.cn"""

import argparse
import functools
import json
import re
from datetime import date, timedelta
from itertools import chain
from typing import Iterator, List, Optional, Tuple

import hashlib
import os

try:
    from filetools import workspace_path
except ImportError:
    from scripts.filetools import workspace_path
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
        2024: [
            "http://lswz.xinjiang.gov.cn/xjgrain/tzgg/202402/32460e4f20f249f4a3a19e62aea3593c.shtml"
        ],
        2025: [
            "http://www.xinjiang.gov.cn/xinjiang/tzgg/202412/01242215d31b4ede946837906c473b7c.shtml"
        ],
        2026: [
            "http://www.xinjiang.gov.cn/xinjiang/tzgg/202512/aaece21b6906443e8d50b981070764a8.shtml"
        ],
    },
    "ningxia": {
        2023: ["https://www.nx.gov.cn/zwgk/qzfwj/202212/t20221230_3900106.html"],
        2024: ["https://www.nx.gov.cn/zwgk/qzfwj/202312/t20231218_4387767.html"],
        2025: ["https://www.nx.gov.cn/zwgk/qzfwj/202412/t20241223_4767357.html"],
        2026: ["https://www.nx.gov.cn/zwgk/qzfwj/202512/t20251216_5110308.html"],
    },
    "guangxi": {
        2023: ["http://www.gxzf.gov.cn/gggs/t16001206.shtml"],
        2024: ["http://www.gxzf.gov.cn/gggs/t18173750.shtml"],
        2025: ["http://www.gxzf.gov.cn/gggs/t19661326.shtml"],
        2026: ["http://www.gxzf.gov.cn/gggs/t27317475.shtml"],
    },
    "xizang": {
        2023: [
            "http://www.lasa.gov.cn/lasa/tggs/202302/92009f75a2a746268888d93e55024b52.shtml"
        ],
        2024: [
            "http://www.lasa.gov.cn/lasa/tggs/202401/0ceebdd88bb54d9ca8ca296efc8f364f.shtml"
        ],
        2025: [
            "http://www.lasa.gov.cn/lasa/tggs/202502/d797f554aae04eb1930766d0f6a56f90.shtml"
        ],
        2026: [
            "http://www.lasa.gov.cn/lasa/tggs/202601/f87553d7183d439fb044eca99fcbf225.shtml"
        ],
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


def _get_guangxi_paper_urls(year: int) -> Iterator[str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.post(
            "https://api.so-gov.cn/query/s",
            data={
                "siteCode": "4500000123",
                "tab": "all",
                "qt": f"{year}年 壮族三月三 放假",
            },
            headers=headers,
            verify=False,
            timeout=5 if os.getenv("CI") else 10,
        )
        if resp.status_code == 200:
            docs = resp.json().get("resultDocs", [])
            for d in docs:
                data = d.get("data", {})
                title = data.get("title", "").replace("<em>", "").replace("</em>", "")
                url = data.get("url", "")
                if (
                    f"{year}年" in title
                    and "三月三" in title
                    and ("放假" in title or "安排" in title)
                    and "/gggs/" in url
                ):
                    yield url
    except Exception:
        pass


def _get_ningxia_paper_urls(year: int) -> Iterator[str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/json",
    }
    search_params = {
        "code": "17c793b087e",
        "sorts": [{"sortField": "f_20211027344499", "sortOrder": "DESC"}],
        "granularity": "ALL",
        "historySearchWords": [],
        "pageSize": 10,
        "pageNo": 1,
        "tableName": "t_17c0cde31e1",
        "analyzerType": "none",
        "customFilter": {
            "operator": "and",
            "properties": [
                {
                    "property": "f_2021924588154",
                    "operator": "eq",
                    "value": f"{year}年部分节假日",
                }
            ],
            "filters": [
                {
                    "operator": "or",
                    "properties": [
                        {
                            "property": "f_2021924985750",
                            "operator": "eq",
                            "value": "22751",
                        },
                        {
                            "property": "f_2021924985750",
                            "operator": "eq",
                            "value": "22753",
                        },
                    ],
                }
            ],
        },
        "tenantId": 19,
    }
    try:
        resp = requests.post(
            "https://www.nx.gov.cn/irs/front/list",
            json=search_params,
            headers=headers,
            verify=False,
            timeout=5 if os.getenv("CI") else 10,
        )
        if resp.status_code == 200:
            items = resp.json().get("data", {}).get("list", [])
            for it in items:
                url = it.get("doc_pub_url")
                if url:
                    yield url
    except Exception:
        pass


def _get_xinjiang_paper_urls(year: int) -> Iterator[str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.post(
            "https://www.xinjiang.gov.cn/search5/search/s",
            data={
                "siteCode": "6500000034",
                "searchWord": f"{year}年 节假日",
                "column": "全部",
            },
            headers=headers,
            verify=False,
            timeout=5 if os.getenv("CI") else 10,
        )
        if resp.status_code == 200:
            xj = resp.json()
            items = xj.get("searchResultAll", {}).get("searchTotal", []) + xj.get(
                "searchResultAll", {}
            ).get("intelligentRecommend", [])
            for it in items:
                title = it.get("title", "").replace("<span>", "").replace("</span>", "")
                url = it.get("url") or it.get("docPubUrl") or ""
                url = url.replace(
                    "https://www.xinjiang.gov.cn", "http://www.xinjiang.gov.cn"
                )
                if (
                    f"{year}年" in title
                    and "节假日" in title
                    and "人民政府办公厅" in title
                    and ("tzgg" in url or "xinjiang.gov.cn" in url)
                ):
                    yield url
    except Exception:
        pass


def _get_xizang_paper_urls(year: int) -> Iterator[str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        url = (
            f"http://sousuo.www.lasa.gov.cn/search4/s?column=%E5%85%A8%E9%83%A8"
            f"&searchWord={year}%E5%B9%B4+%E8%97%8F%E5%8E%86%E6%96%B0%E5%B9%B4+%E6%94%BE%E5%81%87"
            f"&columnId=0&siteCode=5401000001"
        )
        timeout = 5 if os.getenv("CI") else 10
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            soup = bs4.BeautifulSoup(resp.text, features="html.parser")
            for a in soup.find_all("a"):
                href = a.get("href", "")
                title = a.get_text(strip=True)
                if (
                    str(year) in title
                    and "藏历新年" in title
                    and "放假" in title
                    and "解读" not in title
                    and "咨询" not in title
                    and "/tggs/" in href
                ):
                    yield href
    except Exception:
        pass


def get_regional_paper_urls(region: str, year: int) -> List[str]:
    """Find region related paper urls dynamically or from fallback."""
    urls = []
    if region == "guangxi":
        urls = list(dict.fromkeys(_get_guangxi_paper_urls(year)))
    elif region == "ningxia":
        urls = list(dict.fromkeys(_get_ningxia_paper_urls(year)))
    elif region == "xinjiang":
        urls = list(dict.fromkeys(_get_xinjiang_paper_urls(year)))
    elif region == "xizang":
        urls = list(dict.fromkeys(_get_xizang_paper_urls(year)))
    if not urls:
        urls = REGIONAL_PAPERS.get(region, {}).get(year, [])
    return urls


@functools.lru_cache()
def get_paper(url: str) -> str:
    """Extract paper text from url.

    Args:
        url (str): Paper url.

    Returns:
        str: Extracted paper text.
    """

    cache_file = workspace_path(
        "scripts", "cache", f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}.txt"
    )
    timeout = 5 if os.getenv("CI") else 15

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
                " like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, verify=False, timeout=timeout)
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
            or soup.find("div", class_="content_p")
            or soup.find(class_="contentbox")
            or soup.find(class_="TRS_UEDITOR")
        )
        assert isinstance(
            container, bs4.Tag
        ), f"Can not get paper container from url: {url}"
        p = bs4.BeautifulSoup(
            container.decode().replace("<br/>", "</p><p>"), features="html.parser"
        ).find_all("p")
        ret = "\n".join((i.get_text().strip() for i in p if i.get_text().strip()))
        assert ret, f"can not get paper content from url: {url}"
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(ret)
        except Exception:
            pass
        return ret
    except Exception as ex:
        if os.path.isfile(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                return f.read()
        raise ex


def get_rules(paper: str) -> Iterator[Tuple[str, str]]:
    """Extract rules from paper.

    Args:
        paper (str): Paper text

    Raises:
        NotImplementedError: When find no rules.

    Returns:
        Iterator[Tuple[str, str]]: (name, description)
    """

    lines: list = [i.strip() for i in paper.splitlines() if i.strip()]
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
        match = re.match(
            r"^(?:[（\(]?[一二三四五六七八九十]+[）\)]|[一二三四五六七八九十]+、)\s*(.+?)：\s*(.+)$",
            i,
        )
        if match:
            name, desc = match.group(1), match.group(2)
            if "作息" in name or not any(
                k in desc for k in ("放假", "休息", "上班", "调休")
            ):
                continue
            yield name, desc


def get_patch_rules(lines: Iterator[str]) -> Iterator[Tuple[str, str]]:
    """Get holiday patch rule for existed holiday

    Args:
        lines (Iterator[str]): paper content

    Returns:
        Iterator[Tuple[str, str]]: (name, description)
    """
    name = None
    for i in lines:
        cleaned_i = re.sub(r"\s+", "", i)
        lhasa_match = re.match(
            r"^\d+年(春节[、及]藏历新年|藏历新年).*?(?:即[：:]|时间为)(.+)",
            cleaned_i,
        )
        if lhasa_match:
            holiday_name = lhasa_match.group(1).replace("及", "、")
            desc = lhasa_match.group(2)
            yield holiday_name, desc
            continue
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
        description = self.description
        description = re.sub(r"(\d+)\s+([月日])", r"\1\2", description)
        description = re.sub(r"，(?:周末)?正常休息", "正常休息", description)
        description = re.sub(r"按照.+?执行[，、]?", "", description)
        description = re.sub(r"是[^，。；]+节[，、]?", "", description)
        description = re.sub(r"鼓励各单位.+", "", description)
        description = re.sub(
            r"^((?:\d+年)?\d+月\d+日至\d+月\d+日)[，、]", r"\g<1>放假，", description
        )
        description = re.sub(r"放假时间为([^，。；]+)", r"\g<1>放假", description)
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
        match = re.match(r"(?:正常)?(.+?)(?:正常)?上班$", self.sentence)
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
        papers = get_regional_paper_urls(region, year)
        if not papers:
            if date.today().year >= year:
                raise RuntimeError(f"could not found papers for {year} in {region}")
            return {
                "year": year,
                "papers": [],
                "days": [],
            }
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
        regional_papers = get_regional_paper_urls("guangxi", year)
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
        regional_papers = get_regional_paper_urls("xizang", year)
        papers.extend(regional_papers)
        regional_days = [k for p in regional_papers for k in parse_paper(year, p)]
        is_combined = any("春节" in d.get("name", "") for d in regional_days)
        if is_combined:
            days = {d["date"]: d for d in national_data["days"] if d["name"] != "春节"}
        else:
            days = {d["date"]: d for d in national_data["days"]}
        for k in regional_days:
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
