"""业务编排层：``api`` 只做参数校验与序列化，真正的编排在这里。

依赖方向：``services`` 依赖 ``agents`` / ``domain``（Protocol），不 import ``api``。
"""
