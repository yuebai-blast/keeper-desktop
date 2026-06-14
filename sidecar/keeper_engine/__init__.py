"""Keeper（留影）本地推理引擎。

分层架构（Spring Boot 式 + 依赖注入，容器见 container.py）：
  controller/    路由层，只接线，@inject 注入 service
  service/       领域服务与编排（分组 / 层① 评分 / 漏斗 / 层② 打分 / 就绪态）
  client/        外部依赖（VisionClient 本地模型 / Scorer 大模型打分）
  config/        部署运行配置（Settings）
  request/ response/ vo/ enumeration/   入参 / 出参 / 值对象 / 枚举
  converter/     漏斗结果 → 带 origin 的对外条目
  exception/     领域异常
  util/          纯函数工具（影像 IO / CV 信号）

两层级联漏斗（详见 ../../docs/product-flow.md）：
  分组 → 层① 本地评分漏斗（保底数 M）→ 层② 大模型打分漏斗（保底数 N）→ 用户 A/B 擂台（在桌面端）。

设计原则：不静默降级——依赖缺失或模型加载失败立刻抛异常。
"""

__version__ = "0.1.0"
