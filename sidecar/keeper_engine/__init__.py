"""Keeper（留影）本地推理引擎。

两层级联漏斗（详见 ../../docs/product-flow.md）：
  分组               grouping.py     —— DINOv2 语义 + 时间 + 人脸聚类
  漏斗通用规则       funnel.py       —— apply_funnel(scores, n)，两层共用
  层① 本地评分漏斗   prescreen.py    —— 打 0–100 技术质量分，底数 M按保 筛
  层② 大模型打分     scorer.py       —— Scorer ，打 0–100 审美分接口
  层② 出口 / 组装 PK ranking.py      —— assemble_pk_set，按保底数 N 筛
  用户 PK            在桌面端，不在本服务

设计原则：不静默降级——依赖缺失或模型加载失败立刻抛异常。
"""

__version__ = "0.1.0"
