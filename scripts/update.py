#!/usr/bin/env python3
"""Script for updating data."""

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, tzinfo
from tempfile import mkstemp
from typing import Iterator, Optional
from zipfile import ZipFile

from tqdm import tqdm

from fetch import CustomJSONEncoder, fetch_holiday, REGIONS
from generate_ics import generate_ics
from filetools import workspace_path

REGION_NAMES = {
    "xinjiang": "新疆",
    "ningxia": "宁夏",
    "guangxi": "广西",
    "xizang": "西藏",
    "neimenggu": "内蒙古",
}


class ChinaTimezone(tzinfo):
    """Timezone of china."""

    def tzname(self, dt):
        return "UTC+8"

    def utcoffset(self, dt):
        return timedelta(hours=8)

    def dst(self, dt):
        return timedelta()


def update_data(year: int, region: Optional[str] = None) -> Iterator[str]:
    """Update and store data for a year."""

    suffix = f"_{region}" if region else ""
    json_filename = workspace_path(f"{year}{suffix}.json")
    ics_filename = workspace_path(f"{year}{suffix}.ics")
    with open(json_filename, "w", encoding="utf-8", newline="\n") as f:
        data = fetch_holiday(year, region=region)

        json.dump(
            dict(
                (
                    (
                        "$schema",
                        "https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/schema.json",
                    ),
                    (
                        "$id",
                        f"https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}{suffix}.json",
                    ),
                    *data.items(),
                )
            ),
            f,
            indent=4,
            ensure_ascii=False,
            cls=CustomJSONEncoder,
        )

    yield json_filename
    calname = (
        f"中国法定节假日 ({REGION_NAMES.get(region, region)})"
        if region
        else "中国法定节假日"
    )
    generate_ics(data["days"], ics_filename, calname=calname)
    yield ics_filename


def update_main_ics(fr_year, to_year):
    all_days = []
    for year in range(fr_year, to_year + 1):
        filename = workspace_path(f"{year}.json")
        if not os.path.isfile(filename):
            continue
        with open(filename, "r", encoding="utf8") as inf:
            data = json.loads(inf.read())
            all_days.extend(data.get("days"))

    filename = workspace_path("holiday-cn.ics")
    generate_ics(
        all_days,
        filename,
    )
    return filename


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Year to update, default is current year",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Update all years since 2007, default is this year and next year",
    )
    parser.add_argument(
        "--region",
        type=str,
        choices=[*REGIONS, "all"],
        default=None,
        help="Update regional holidays",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="create new release if repository data is not up to date",
    )
    args = parser.parse_args()

    now = datetime.now(ChinaTimezone())
    is_release = args.release
    year = args.year or now.year

    filenames = []
    if args.region:
        target_regions = REGIONS if args.region == "all" else [args.region]
        for r in target_regions:
            filenames += list(update_data(year, region=r))
    else:
        progress = tqdm(range(2007 if args.all else now.year, now.year + 2))
        for i in progress:
            progress.set_description(f"Updating {i} data")
            filenames += list(update_data(i))
            if i >= 2026:
                for r in REGIONS:
                    try:
                        filenames += list(update_data(i, region=r))
                    except Exception as e:
                        print(f"Warning: failed to update {i}_{r}: {e}")
        progress.set_description("Updating holiday-cn.ics")
        filenames.append(update_main_ics(now.year - 4, now.year + 1))
    print("")

    subprocess.run(["git", "add", *filenames], check=True)
    diff = subprocess.run(
        ["git", "diff", "--stat", "--cached", "*.json", "*.ics"],
        check=True,
        stdout=subprocess.PIPE,
        encoding="utf-8",
    ).stdout
    if not diff:
        print("Already up to date.")
        return

    if not is_release:
        print("Updated repository data, skip release since not specified `--release`")
        return

    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "chore(release): update holiday data",
            "-m",
            "[skip ci]",
        ],
        check=True,
    )
    subprocess.run(["git", "push"], check=True)

    tag = now.strftime("%Y.%m.%d")
    temp_note_fd, temp_note_name = mkstemp()
    with open(temp_note_fd, "w", encoding="utf-8") as f:
        f.write(tag + "\n\n```diff\n" + diff + "\n```\n")
    os.makedirs(workspace_path("dist"), exist_ok=True)
    zip_path = workspace_path("dist", f"holiday-cn-{tag}.zip")
    pack_data(zip_path)

    subprocess.run(
        [
            "gh",
            "release",
            "create",
            "-F",
            temp_note_name,
            tag,
            f"{zip_path}#JSON数据",
        ],
        check=True,
    )
    os.unlink(temp_note_name)


def pack_data(file):
    """Pack data json in zip file."""

    zip_file = ZipFile(file, "w")
    for i in os.listdir(workspace_path()):
        if not re.match(r"\d+(?:_\w+)?\.json", i):
            continue
        zip_file.write(workspace_path(i), i)


if __name__ == "__main__":
    main()
