"""Agent 编排层：LangGraph 状态机、节点与查询解析工具。

对本层之上（``services`` / ``api``）只暴露两件东西：
``agents.graph.build_graph`` / ``agents.graph.run_agent`` 与 ``agents.graph.AgentDeps``。
``agents`` 不得 import ``services`` / ``api``（分层单向：api → services → agents → domain / rag → infra）。
"""
