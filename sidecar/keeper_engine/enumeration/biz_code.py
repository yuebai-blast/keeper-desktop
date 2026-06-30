"""业务错误码枚举（统一 ApiResponse 的 code）。

约定（见全局规范）：6 位整数，**前两位（11–99）为模块/分段号**，**后四位（0001–9999）为段内具体错误序号**。
`0` 始终表示成功，不参与分段。段位分配：
  - `11xxxx` 通用/系统
  - `21xxxx` 本地模型（层① 引擎）
  - `31xxxx` 大模型（层② 打分）
  - `41xxxx` 项目工作流

每个成员带 `code`（业务码）+ `message`（默认中文描述）。controller/service 一律抛 `BizException(BizCode.X)`，
由 app 的异常处理器统一翻译成 HTTP 200 + ApiResponse；**禁止在业务代码里散落魔法数字**。
括号注释标注其替代的原生 HTTP 语义，便于对照迁移。
"""

from __future__ import annotations

from enum import Enum


class BizCode(Enum):
    """全系统业务码。成员值为 (code, message)。"""

    SUCCESS = (0, "成功")

    # ── 11xxxx 通用/系统 ──────────────────────────────────────────────
    INTERNAL_ERROR = (110001, "服务器内部错误")          # 原 500：兜底未捕获异常
    VALIDATION_ERROR = (110002, "请求参数校验失败")       # 原 422/400：pydantic 校验失败
    AUTH_FAILED = (110003, "鉴权失败")            # 原 401：sidecar 返回纯 401，本码仅供前端 unwrap 合成标识

    # ── 21xxxx 本地模型（层① 引擎）────────────────────────────────────
    MODEL_NOT_READY = (210001, "本地模型未就绪，请稍候")   # 原 503：预热中/加载失败，可重试
    MODEL_DEPENDENCY_MISSING = (210002, "本地推理依赖缺失")  # 原 503：缺包，不可重试

    # ── 31xxxx 大模型（层② 打分）──────────────────────────────────────
    SCORER_FAILED = (310001, "大模型打分失败")            # 原 502：缺 key / 网络 / 接口错误
    FOUNDATION_MODELS_FAILED = (310002, "获取视觉模型列表失败")  # 原 502：缺 AK/SK / 网络 / 管理面接口错误

    # ── 41xxxx 项目工作流 ─────────────────────────────────────────────
    PROJECT_NAME_DUPLICATE = (410001, "项目名已存在")          # 原 409
    PROJECT_NOT_FOUND = (410002, "项目不存在")                # 原 404
    GROUP_NOT_FOUND = (410003, "分组不存在")                  # 原 404
    INVALID_PROJECT_NAME = (410004, "项目名非法")             # 空 / 路径分隔符 / 过长 / Win 禁用字符·保留名 / mac 包后缀
    NO_IMPORTABLE_IMAGES = (410005, "该文件夹内没有可导入的图片")  # 原 400
    INVALID_SOURCE_FOLDER = (410006, "源文件夹无效")          # 原 400：不存在 / 非目录
    GROUPS_NOT_ALL_CONFIRMED = (410007, "还有未确认的分组，无法完成")  # 原 400
    GROUP_HAS_UNRESOLVED_FAILURES = (410008, "本组还有未处理的评测失败，请先重试或忽略")  # 原 409
    INVALID_GUARANTEE_PARAMS = (410009, "保底参数非法")  # 原 400：百分比不在 [1,100] 或固定值 <1
    PHOTO_NOT_FOUND = (410010, "照片不存在")                  # 原 404
    PHOTO_MOVE_TARGET_ASSESSED = (410011, "目标分组已评测，无法移入未评测的照片")  # 原 409
    GROUP_CONFIRMED_LOCKED = (410012, "分组已确认并锁定，无法移动其照片")  # 原 409
    PHOTO_MOVE_BLOCKED_BY_FAILURE = (410013, "照片有未处理的评测失败，请先重试或忽略再移动")  # 原 409

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
