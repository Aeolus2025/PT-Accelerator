"""接口层的数据模型。

只保留真正参与请求校验与鉴权的模型。配置类结构（tracker、hosts 源、
下载器、通知渠道）走整份 dict 读写，字段允许缺失与扩展，不适合用固定
模型约束，因此不在此定义。
"""

from typing import List, Union

from pydantic import BaseModel


class BatchAddDomainsRequest(BaseModel):
    """批量添加域的请求体

    domains 既可以是按行分隔的字符串，也可以是字符串列表，
    与 domain_service.clean_domains 支持的两入参形式保持一致。
    """

    domains: Union[str, List[str]]


class User(BaseModel):
    """当前登录用户，用于鉴权依赖返回"""

    username: str
    is_authenticated: bool = True
