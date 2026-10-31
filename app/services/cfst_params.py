"""CloudflareSpeedTest 参数规格表。

这里是 cfst 参数的唯一事实来源：默认值、取值校验、命令行拼装，以及前端表单
渲染用的 schema，全部由下面这张 CFST_PARAMS 表推导，避免同一份说明在两处维护。

只依赖标准库：defaults.py 会 import 本模块，反向 import app.core.* 会成环。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# 托管参数：Python 与 cfst_hosts.sh 之间的私有契约，固定值，不开放给用户。
#   -p 0            不把结果打到 stdout（Python 读的是结果文件）
#   -f/-o           输入输出文件名，Python 靠 result_hosts.txt 取最优 IP
#   -ip             直接指定 IP 段会绕过 ip.txt，让用户配置失效
MANAGED_FLAGS = ("-f", "-o", "-p", "-ip")

# 超时基线：脚本本身还要做 hosts 替换等收尾工作，留足余量
TIMEOUT_BASE = 900
TIMEOUT_MAX = 3600

# 分组：(键, 标题, 说明)
GROUPS: Tuple[Tuple[str, str, str], ...] = (
    ("delay", "延迟测速", "决定扫多少 IP、扫多快，直接影响整轮耗时。"),
    ("download", "下载测速", "启用后按下载速度排序挑 IP，耗时明显增加。"),
    ("filter", "结果筛选", "只保留满足条件的 IP；条件越严，越可能一个都选不出来。"),
    ("httping", "HTTPing 高级", "把延迟测速从 TCP 换成 HTTP，能拿到地区码，但对目标站点请求量更大。"),
)

_CFCOLO_RE = re.compile(r"^[A-Z]{3}(,[A-Z]{3})*$")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class ParamSpec:
    """一个 cfst 命令行参数的可配置描述。"""

    key: str                 # 配置里的键名
    flag: str                # 命令行参数名，如 -n
    label: str               # 中文名，用于界面与错误提示
    type: str                # int | float | bool | str
    default: Any
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    group: str = "delay"
    desc: str = ""           # 我们自己的说明：这个参数怎么影响结果、什么时候该改
    official: str = ""       # 官方帮助原文，便于对照
    managed: bool = False
    precision: Optional[int] = None   # 浮点参数在界面上保留几位小数（None 表示不固定）


CFST_PARAMS: Tuple[ParamSpec, ...] = (
    ParamSpec(
        key="n", flag="-n", label="延迟测速线程", type="int", default=200,
        minimum=1, maximum=1000, group="delay",
        desc="同时探测的 IP 数量。调大更快，但 NAS、路由器这类低性能设备容易被跑满。",
        official="延迟测速线程；越多延迟测速越快，性能弱的设备 (如路由器) 请勿太高；(默认 200 最多 1000)",
    ),
    ParamSpec(
        key="t", flag="-t", label="延迟测速次数", type="int", default=4,
        minimum=1, maximum=20, group="delay",
        desc="每个 IP 测几次延迟取平均。调大结果更稳，耗时线性增加。",
        official="延迟测速次数；单个 IP 延迟测速的次数；(默认 4 次)",
    ),
    ParamSpec(
        key="tp", flag="-tp", label="测速端口", type="int", default=443,
        minimum=1, maximum=65535, group="delay",
        desc="延迟与下载测速都走这个端口。目标站点只开 80 时改成 80，并用测速地址指一个 http 地址。",
        official="指定测速端口；延迟测速/下载测速时使用的端口；(默认 443 端口)",
    ),
    ParamSpec(
        # 默认沿用本项目原有的优选行为（旧脚本一直硬编码 -dd），而不是 cfst 官方默认：
        # 本项目的目标是给 PT 站点挑低延迟 IP，下载测速要多花 dn×dt 秒且会改变选 IP 的依据。
        key="dd", flag="-dd", label="仅测延迟（不测下载速度）", type="bool", default=True,
        group="download",
        desc="开启：只测延迟，结果按延迟排序，整轮最快。关闭：额外做下载测速，结果按下载速度排序，"
             "每轮多花「下载测速数量 × 单次时长」秒。",
        official="禁用下载测速；禁用后测速结果会按延迟排序 (默认按下载速度排序)；(默认 启用)",
    ),
    ParamSpec(
        key="dn", flag="-dn", label="下载测速数量", type="int", default=10,
        minimum=1, maximum=1000, group="download",
        desc="延迟排序后，取前 N 个 IP 做下载测速。禁用下载测速时本项不生效。",
        official="下载测速数量；延迟测速并排序后，从最低延迟起下载测速的数量；(默认 10 个)",
    ),
    ParamSpec(
        key="dt", flag="-dt", label="单IP下载测速时长", type="int", default=10,
        minimum=1, maximum=600, group="download",
        desc="每个 IP 最多下载测这么久（秒）。调小会低估速度，调大整轮变慢。",
        official="下载测速时间；单个 IP 下载测速最长时间，不能太短；(默认 10 秒)",
    ),
    ParamSpec(
        key="sl", flag="-sl", label="下载速度下限", type="float", default=0.0,
        minimum=0, maximum=10000, group="download", precision=2,
        desc="低于该速度（MB/s）的 IP 直接丢弃。只设它不设延迟上限时，可能为了凑够数量一直测下去。",
        official="下载速度下限；只输出高于指定下载速度的 IP，凑够指定数量 [-dn] 才会停止测速；(默认 0.00 MB/s)",
    ),
    ParamSpec(
        key="url", flag="-url", label="测速地址", type="str",
        default="https://cf.xiu2.xyz/url", group="download",
        desc="下载测速地址，也是 HTTPing 模式下的延迟测速地址。官方默认地址不保证长期可用，建议自建。",
        official="指定测速地址；延迟测速(HTTPing)/下载测速时使用的地址，默认地址不保证可用性，建议自建；(默认 https://cf.xiu2.xyz/url)",
    ),
    ParamSpec(
        key="tl", flag="-tl", label="平均延迟上限", type="int", default=9999,
        minimum=0, maximum=100000, group="filter",
        desc="平均延迟（ms）超过该值的 IP 丢弃。设了下载速度下限时，建议同时设它来兜底终止。",
        official="平均延迟上限；只输出低于指定平均延迟的 IP，各上下限条件可搭配使用；(默认 9999 ms)",
    ),
    ParamSpec(
        key="tll", flag="-tll", label="平均延迟下限", type="int", default=0,
        minimum=0, maximum=100000, group="filter",
        desc="平均延迟（ms）低于该值的 IP 丢弃。常用于排除「延迟很低但速度很差」的节点。",
        official="平均延迟下限；只输出高于指定平均延迟的 IP；(默认 0 ms)",
    ),
    ParamSpec(
        key="tlr", flag="-tlr", label="丢包率上限", type="float", default=1.0,
        minimum=0, maximum=1, group="filter", precision=2,
        desc="丢包率超过该值的 IP 丢弃，取值 0~1。填 0 表示只要丢一个包就不要。",
        official="丢包几率上限；只输出低于/等于指定丢包率的 IP，范围 0.00~1.00，0 过滤掉任何丢包的 IP；(默认 1.00)",
    ),
    ParamSpec(
        key="httping", flag="-httping", label="使用 HTTP 协议测速", type="bool", default=False,
        group="httping",
        desc="把延迟测速从 TCP 换成 HTTP。能顺带拿到 IP 的地区码，但对目标站点的请求量更大。",
        official="切换测速模式；延迟测速模式改为 HTTP 协议，所用测试地址为 [-url] 参数；(默认 TCPing)",
    ),
    ParamSpec(
        key="httping_code", flag="-httping-code", label="有效状态码", type="int", default=0,
        minimum=0, maximum=599, group="httping",
        desc="HTTPing 下认定「有效」的网页状态码。留 0 表示使用官方内置的 200/301/302。",
        official="有效状态代码；HTTPing 延迟测速时网页返回的有效 HTTP 状态码，仅限一个；(默认 200 301 302)",
    ),
    ParamSpec(
        key="cfcolo", flag="-cfcolo", label="匹配指定地区", type="str", default="",
        group="httping",
        desc="只保留指定地区的 IP，如 HKG,LAX（英文逗号分隔，大写）。仅 HTTPing 模式有效，留空表示不限制。",
        official="匹配指定地区；IATA 机场地区码或国家/城市码，英文逗号分隔，仅 HTTPing 模式可用；(默认 所有地区)",
    ),
    ParamSpec(
        key="allip", flag="-allip", label="测速全部 IP", type="bool", default=False,
        group="httping",
        desc="把每个 IP 段里的所有 IP 都测一遍（仅 IPv4）。耗时可能上升一个数量级。",
        official="测速全部的IP；对 IP 段中的每个 IP (仅支持 IPv4) 进行测速；(默认 每个 /24 段随机测速一个 IP)",
    ),
    ParamSpec(
        key="debug", flag="-debug", label="调试输出", type="bool", default=False,
        group="httping",
        desc="输出更多排查信息（仅 HTTPing 与下载测速过程）。平时不用开。",
        official="调试输出模式；会在一些非预期情况下输出更多日志以便判断原因；(默认 关闭)",
    ),
)

_BY_KEY: Dict[str, ParamSpec] = {spec.key: spec for spec in CFST_PARAMS}

_TRUE_WORDS = {"true", "1", "yes", "on", "y", "t"}
_FALSE_WORDS = {"false", "0", "no", "off", "n", "f", ""}


# ---------------------------------------------------------------- 对外查询

def specs() -> Tuple[ParamSpec, ...]:
    """全部可配置参数的规格。"""
    return CFST_PARAMS


def defaults() -> Dict[str, Any]:
    """默认值字典；每次返回新对象，避免调用方改到共享状态。"""
    return {spec.key: spec.default for spec in CFST_PARAMS}


def groups() -> List[Dict[str, str]]:
    """分组元数据，供前端分卡片渲染。"""
    return [{"key": key, "label": label, "hint": hint} for key, label, hint in GROUPS]


def schema() -> Dict[str, Any]:
    """前端渲染表单所需的全部信息（JSON 可序列化）。"""
    return {
        "groups": groups(),
        "params": [
            {
                "key": spec.key,
                "flag": spec.flag,
                "label": spec.label,
                "type": spec.type,
                "default": spec.default,
                "min": spec.minimum,
                "max": spec.maximum,
                "group": spec.group,
                "desc": spec.desc,
                "official": spec.official,
                "precision": spec.precision,
            }
            for spec in CFST_PARAMS
        ],
        "managedFlags": list(MANAGED_FLAGS),
    }


# ---------------------------------------------------------------- 类型与校验

def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in _TRUE_WORDS:
        return True
    if text in _FALSE_WORDS:
        return False
    raise ValueError("不是布尔值")


def _coerce(spec: ParamSpec, value: Any) -> Any:
    """按类型转换；转不动就退回默认值。"""
    try:
        if spec.type == "bool":
            return _to_bool(value)
        if spec.type == "int":
            if isinstance(value, bool):
                raise ValueError("不是数字")
            return int(float(str(value).strip()))
        if spec.type == "float":
            if isinstance(value, bool):
                raise ValueError("不是数字")
            return float(str(value).strip())
        return str(value).strip()
    except (TypeError, ValueError):
        return spec.default


def _invalid_reason(spec: ParamSpec, value: Any) -> Optional[str]:
    """单项校验；返回中文原因，通过时返回 None。"""
    if spec.type == "bool":
        if isinstance(value, bool):
            return None
        return "只能是开启或关闭"

    if spec.type in ("int", "float"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "必须是数字"
        if spec.type == "int" and float(value) != int(value):
            return "必须是整数"
        if spec.minimum is not None and value < spec.minimum:
            return "不能小于 %s" % _fmt_number(spec.minimum)
        if spec.maximum is not None and value > spec.maximum:
            return "不能大于 %s" % _fmt_number(spec.maximum)
        return None

    text = "" if value is None else str(value).strip()
    if not text:
        # 空值表示「用官方默认」，只有 url 不允许留空
        return "不能为空" if spec.key == "url" else None
    if _CTRL_RE.search(text):
        return "不能包含换行或控制字符"
    if text.startswith("-"):
        return "不能以 - 开头，会被当成命令行参数"
    if spec.key == "url":
        if not _URL_RE.match(text):
            return "必须以 http:// 或 https:// 开头"
        if any(ch.isspace() for ch in text):
            return "不能包含空格"
        return None
    if spec.key == "cfcolo":
        if not _CFCOLO_RE.match(text.upper()):
            return "格式应为 HKG 或 HKG,LAX（三字母地区码，英文逗号分隔）"
        return None
    return None


def validate(raw: Optional[Dict[str, Any]]) -> List[str]:
    """校验用户提交的 cfst 节；只校验出现过的键。"""
    if not raw:
        return []
    if not isinstance(raw, dict):
        return ["优选参数格式错误：cfst 必须是键值对象"]

    errors: List[str] = []
    for key, value in raw.items():
        spec = _BY_KEY.get(key)
        if spec is None:
            continue
        reason = _invalid_reason(spec, _coerce_for_check(spec, value))
        if reason:
            errors.append("%s (%s)：%s" % (spec.label, spec.flag, reason))

    # 跨字段：延迟下限不能大于上限
    tl = raw.get("tl", _BY_KEY["tl"].default)
    tll = raw.get("tll", _BY_KEY["tll"].default)
    try:
        if float(tll) > float(tl):
            errors.append("平均延迟下限 (-tll)：不能大于平均延迟上限 (-tl)")
    except (TypeError, ValueError):
        pass

    return errors


def _coerce_for_check(spec: ParamSpec, value: Any) -> Any:
    """校验用：不做回退，转不动就原样返回，让 _invalid_reason 报「必须是数字」。"""
    if spec.type == "bool":
        try:
            return _to_bool(value)
        except ValueError:
            return value
    if spec.type == "int":
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return value
    if spec.type == "float":
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return value
    return value


def normalize(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """按类型规整后返回新字典；未知键原样保留（留给未来版本）。"""
    out: Dict[str, Any] = {}
    for key, value in (raw or {}).items():
        spec = _BY_KEY.get(key)
        out[key] = _coerce(spec, value) if spec else value
    return out


def resolve(raw: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """运行期用：非法项回退默认值，并返回告警列表。

    定时任务不应该因为一个手改错的参数整晚失败，所以这里不抛异常。
    """
    params = defaults()
    warns: List[str] = []
    for key, value in (raw or {}).items():
        spec = _BY_KEY.get(key)
        if spec is None:
            continue
        coerced = _coerce_for_check(spec, value)
        reason = _invalid_reason(spec, coerced)
        if reason:
            warns.append("%s (%s) 取值 %r 无效（%s），已回退默认值 %r"
                         % (spec.label, spec.flag, value, reason, spec.default))
            continue
        params[key] = _coerce(spec, value)
    return params, warns


# ---------------------------------------------------------------- 命令行拼装

def _fmt_number(value: float) -> str:
    """数字转命令行文本：5.0 → 5，0.5 → 0.5。"""
    if float(value) == int(float(value)):
        return str(int(float(value)))
    return ("%g" % float(value))


def build_args(params: Optional[Dict[str, Any]]) -> List[str]:
    """把配置拼成 cfst 的命令行参数（不含托管参数）。

    三条规则：
      1. bool 只在为真时输出 flag —— 绝不能出现 "-dd false"，
         Go 的 flag 会把 false 当成第一个位置参数，其后的参数全部失效；
      2. 等于默认值的省略，命令行短、日志干净，行为与官方默认一致；
      3. 依赖失效的省略：-dd 打开后 -dn/-dt/-sl 无效，未开 -httping 时
         -httping-code/-cfcolo 无效。
    """
    p = defaults()
    for key, value in (params or {}).items():
        if key in _BY_KEY:
            p[key] = value

    download_enabled = not bool(p["dd"])
    httping = bool(p["httping"])

    args: List[str] = []
    for spec in CFST_PARAMS:
        if spec.key in ("dn", "dt", "sl") and not download_enabled:
            continue
        if spec.key in ("httping_code", "cfcolo") and not httping:
            continue

        value = p[spec.key]
        if spec.type == "bool":
            if value:
                args.append(spec.flag)
            continue
        if spec.type == "str":
            text = "" if value is None else str(value).strip()
            if spec.key == "cfcolo":
                text = text.upper()
            if not text or text == spec.default:
                continue
            args.extend([spec.flag, text])
            continue
        if value == spec.default:
            continue
        args.extend([spec.flag, _fmt_number(value)])
    return args


def timeout_seconds(params: Optional[Dict[str, Any]]) -> int:
    """按本轮参数估算合理超时，避免用户调大参数后被误杀。"""
    p = defaults()
    for key, value in (params or {}).items():
        if key in _BY_KEY:
            p[key] = value

    total = TIMEOUT_BASE
    if not bool(p["dd"]):
        try:
            total += int(p["dn"]) * int(p["dt"])
        except (TypeError, ValueError):
            pass
    if bool(p["allip"]):
        total += 600
    return max(TIMEOUT_BASE // 3, min(total, TIMEOUT_MAX))


def command_preview(params: Optional[Dict[str, Any]], binary: str = "cfst",
                    script_result: str = "result_hosts.txt") -> str:
    """给人看的等效命令行，包含托管参数，便于手工复现。"""
    parts = [binary, "-p", "0", "-f", "ip.txt", "-o", script_result]
    parts.extend(build_args(params))
    return " ".join(parts)
