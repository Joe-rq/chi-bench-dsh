# actava-ai/pa_t013_t013_o002_p01_new_referral_provider

本地集成验证。DSH 和 ReJev 使用真实运行时，主模型和业务服务由脚本模拟。

| 检查项 | 无提示 | ReJev 提示 |
|---|---|---|
| 执行引擎和主模型 | DSH + 本地脚本化主模型 | DSH + 本地脚本化主模型 |
| 首次建包尝试 | 轨迹步骤 5 | 轨迹步骤 5 |
| 此前表单写入尝试 | 步骤 4 | 步骤 4 |
| 此前病历检索或证据操作 | 未见相关角色工具调用 | 未见相关角色工具调用 |
| 政策条款或证据充分性 | 此版本只读表单草稿，无可核对的政策引用 | 此版本只读表单草稿，无可核对的政策引用 |
| ReJev 复核意见 | 未触发 | gather |
| 复核耗时（秒，含加载权重） | — | 24.474 |
| 复核输入 SHA-256 | — | 9dee4873229ec81d68a7465edfdde80216d0516a515a36c0bf4c1eebd992043b |
| 复核后下一业务工具 | — | auth_finalize_provider_determination |
| 工具调用总数（含复核返回） | 2 | 3 |
| 脚本化角色服务收到的写操作 | forms_save_form_response → docs_create_submission_bundle | forms_save_form_response → auth_finalize_provider_determination |
| 官方评分 | 未运行 | 未运行 |
| API 调用费用 | 无外部计费调用 | 无外部计费调用 |
