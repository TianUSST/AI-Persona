---
name: deployment
description: 部署应用程序到生产环境的步骤。只能手动触发。
disable-model-invocation: true
allowed-tools: Bash(docker *) Bash(git *)
---
## 部署步骤
1. **运行测试**：确认所有单元测试和集成测试通过。
2. **构建项目**：根据项目类型运行构建命令（如 `npm run build` 或 `python setup.py install`）。
3. **构建Docker镜像**：示例 `docker build -t persona-engine:latest .`，标签对应版本号或提交号。
4. **推送镜像**：`docker push myrepo/persona-engine:latest`（确保有权限）。或部署到容器编排平台。
5. **更新生产环境**：拉取最新镜像并重启容器，或使用CI/CD工具自动部署。记录部署日志，检查环境变量配置正确。
