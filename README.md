# holiday-cn

> 本项目是 [NateScarlet/holiday-cn](https://github.com/NateScarlet/holiday-cn) 的 Fork，维护者：[@irvingwu0v0](https://github.com/irvingwu0v0)。  
> 在原项目国务院法定节假日数据的基础上，增加了中国五个少数民族自治区（新疆、宁夏、广西、西藏、内蒙古）特色节假日放假安排的自动化检索、解析与日历数据生成。

[![Build Status](https://github.com/irvingwu0v0/holiday-cn/workflows/CI/badge.svg)](https://github.com/irvingwu0v0/holiday-cn/actions)
[![Release](https://img.shields.io/github/release/irvingwu0v0/holiday-cn.svg)](https://github.com/irvingwu0v0/holiday-cn/releases/latest)
[![CalVer](https://img.shields.io/badge/calver-YYYY.0M.0D-22bfda.svg)](http://calver.org)
[![JSDelivr](https://data.jsdelivr.com/v1/package/gh/irvingwu0v0/holiday-cn/badge?style=rounded)](https://www.jsdelivr.com/package/gh/irvingwu0v0/holiday-cn)
![Maintenance](https://img.shields.io/maintenance/yes/2026.svg)

中国法定节假日及少数民族自治区节假日数据 自动每日抓取官方政府网站公告

- [x] 提供 JSON 格式节假日数据（全国及各自治区）
- [x] CI 自动更新与自动化全文检索抓取
- [x] 数据变化时自动发布新版本 ( `Watch` - `Release only` 以获取邮件提醒! )
- [x] [发布页面]提供 JSON 打包下载

数据格式:

[JSON Schema](./schema.json)

```TypeScript
interface Holidays {
  /** 完整年份, 整数。*/
  year: number;
  /** 所用官方文件网址列表（国务院及自治区政府网站） */
  papers: string[];
  days: {
    /** 节日名称 */
    name: string;
    /** 日期, ISO 8601 格式 */
    date: string;
    /** 是否为休息日 */
    isOffDay: boolean;
  }[]
}
```

## 注意事项

- 年份是按照政府文件标题年份而不是日期年份，12 月份的日期可能会被下一年的文件影响，因此应检查两个文件。

- `与周末连休` 的周末不是法定节假日，数据里不会包含，见[《全国年节及纪念日放假办法》](https://www.gov.cn/zhengce/content/202411/content_6986380.htm) [#213](https://github.com/NateScarlet/holiday-cn/issues/213#issuecomment-1869546011) [#221](https://github.com/NateScarlet/holiday-cn/issues/221)

- 依据《全国年节及纪念日放假办法》第四条：“少数民族习惯的节日，由各少数民族聚居地区的地方人民政府，按照各该民族习惯，规定放假日期。”

## 少数民族自治区节假日数据

除全国统一法定节假日外，本项目自动检索各省区政府官方网站，支持五个少数民族自治区的特色放假安排：

- **新疆维吾尔自治区 (`xinjiang`)**：自动检索新疆维吾尔自治区人民政府官方公告，包含肉孜节（开斋节）、古尔邦节。
- **宁夏回族自治区 (`ningxia`)**：自动检索宁夏回族自治区人民政府官方公告，包含开斋节、古尔邦节。
- **广西壮族自治区 (`guangxi`)**：自动检索广西壮族自治区人民政府官方公告，包含“壮族三月三”。
- **西藏自治区 (`xizang`)**：自动检索拉萨市人民政府（`lasa.gov.cn`）官方公告。根据藏历与农历年份规律：
  - 当春节与藏历新年相重合或紧密相连（如 2024、2026 年）时，合并放假（“春节、藏历新年”），替换国家单一春节假期；
  - 当春节与藏历新年相隔约一个月（如 2023、2025 年）时，西藏群众既享受国家法定春节（7~8天），又额外享受藏历新年（6~7天），两者独立保留。
- **内蒙古自治区 (`neimenggu`)**：依规执行全国统一法定节假日安排。

文件命名规则：
- 全国节假日：`{年份}.json` 与 `{年份}.ics`
- 自治区节假日：`{年份}_{地区}.json`（例如 `2026_xinjiang.json`、`2026_xizang.json`）与 `{年份}_{地区}.ics`（例如 `2026_xinjiang.ics`、`2026_xizang.ics`）

## 通过互联网使用

提示：任何第三方服务都可能故障或停止服务，如果稳定性要求高请自己搭建静态文件服务。

全国数据地址格式:

`https://raw.githubusercontent.com/irvingwu0v0/holiday-cn/master/{年份}.json`

自治区数据地址格式:

`https://raw.githubusercontent.com/irvingwu0v0/holiday-cn/master/{年份}_{地区}.json`

或使用 JSDelivr：

`https://cdn.jsdelivr.net/gh/irvingwu0v0/holiday-cn@master/{年份}.json`

`https://cdn.jsdelivr.net/gh/irvingwu0v0/holiday-cn@master/{年份}_{地区}.json`

`https://fastly.jsdelivr.net/gh/irvingwu0v0/holiday-cn@master/{年份}.json`

`https://fastly.jsdelivr.net/gh/irvingwu0v0/holiday-cn@master/{年份}_{地区}.json`

也可尝试使用 [ghproxy](https://github.com/hunshcn/gh-proxy) 或其他 Github 加速：

`https://{ghproxy服务}/https://raw.githubusercontent.com/irvingwu0v0/holiday-cn/master/{年份}.json`

## ICalendar 订阅

网址格式参见上一节

- `{年份}.ics` 为对应年份全国节假日
- `{年份}_{地区}.ics` 为对应年份自治区的节假日（含全国法定假日与自治区特色假日）
- `holiday-cn.ics` 为 3 年前至次年的全国节假日

感谢 @retanoj 的 ics 格式转换实现

## 作为 git 子模块使用

参见 [Git 工具 - 子模块](https://git-scm.com/book/zh/v2/Git-%E5%B7%A5%E5%85%B7-%E5%AD%90%E6%A8%A1%E5%9D%97)

[发布页面]: https://github.com/irvingwu0v0/holiday-cn/releases
