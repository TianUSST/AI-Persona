---
name: testing
description: 测试代码和验证指南。适用于需要编写或运行测试用例时使用。
allowed-tools: Bash(pytest *)
---
## 测试指导
- 使用 **pytest** 框架编写单元测试，命名规则 `test_*.py`，每个函数/类模块对应一个测试函数。
- 编写测试时覆盖正常场景和边界情况。对每个功能点至少写一个测试用例，并使用断言（assert）检查预期输出。
- 在CLI执行测试：示例命令 `pytest --maxfail=1 --disable-warnings -q`。集成在CI中应设置为自动失败。
- 若有数据库或外部服务依赖，使用Mock或临时环境，避免在测试中修改生产配置。
- 测试失败时，Skill指导Claude定位问题并修正代码，同时保持原有功能正确性。
