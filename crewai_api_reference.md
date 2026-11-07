# crewAI API 参考手册

> 本文档由脚本从**真实安装的 crewai 包**反射生成，非人工编写：所有字段、类型、默认值、方法签名均来自源码内省。
> 生成环境：Python 3.12 / crewai 见文末版本信息。

## 阅读说明

- **字段表**：`类型` 为 Pydantic 注解原文；`默认值` 中 `**必填**` 表示构造时必须提供。
- **方法表**：签名为 `inspect.signature` 原文（已去掉 `self`），`返回` 为返回注解，`—` 表示无注解。
- 所有 Pydantic 模型都自动带有 `model_dump()` / `model_dump_json()` / `model_validate()` / `model_copy()` 等基类方法，为避免重复，正文只列业务方法，通用方法见本节末尾。
- 模块路径可用于 `from <模块> import <类>`。

### 公共基类方法（所有 Pydantic 模型通用）

| 方法 | 说明 |
|---|---|
| `model_dump(**kwargs) -> dict` | 序列化为字典 |
| `model_dump_json(**kwargs) -> str` | 序列化为 JSON 字符串 |
| `model_validate(obj) -> Self` | 从字典/对象反序列化 |
| `model_validate_json(s) -> Self` | 从 JSON 字符串反序列化 |
| `model_copy(update=None, deep=False) -> Self` | 复制（可局部更新） |
| `model_fields` | 字段定义字典（类属性） |
| `model_json_schema()` | 生成 JSON Schema |

---

> crewai 版本：`1.14.4`；安装路径：`/workspace/.venv312/lib/python3.12/site-packages/crewai`

---

## 目录

- [一、四大核心类](#一、四大核心类)：`Agent`、`Task`、`Crew`、`Flow`
- [二、工具类](#二、工具类)：`BaseTool`、`Tool 装饰器`
- [三、模型类](#三、模型类)：`LLM`、`BaseLLM`
- [四、配置类](#四、配置类)：`PlanningConfig`、`SecurityConfig`、`CheckpointConfig`、`KnowledgeConfig`
- [五、记忆类](#五、记忆类)：`Memory`、`MemoryScope`、`MemorySlice`
- [六、知识源类](#六、知识源类)：`TextFileKnowledgeSource`、`StringKnowledgeSource`、`BaseKnowledgeSource`、`Knowledge`
- [七、技能类](#七、技能类)：`Skill`、`SkillFrontmatter`
- [八、MCP 配置类](#八、MCP-配置类)：`MCPServerStdio`、`MCPServerHTTP`、`MCPServerSSE`
- [九、A2A 配置类](#九、A2A-配置类)：`A2AConfig`、`A2AServerConfig`、`A2AClientConfig`
- [十、输出类](#十、输出类)：`CrewOutput`、`TaskOutput`、`LiteAgentOutput`
- [十一、上下文与状态类](#十一、上下文与状态类)：`ExecutionContext`、`RuntimeState`
- [十二、枚举](#十二、枚举)：`Process`、`OutputFormat`
- [十三、Flow 装饰器](#十三、Flow-装饰器)：`start`、`listen`、`router`、`and_`、`or_`
- [十四、其他工具类](#十四、其他工具类)：`Converter`、`UsageMetrics`
- [十五、crewai_tools 预置工具](#十五、crewai_tools-预置工具)
- [十六、全包类索引](#十六、全包类索引)

---

## 一、四大核心类

### Agent

**模块：** `crewai.agent.core`

**说明：** Represents an agent in a system.

**父类：** BaseAgent

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `entity_type` | `typing.Literal['agent']` | 'agent' |  |
| `id` | `<class 'uuid.UUID'>` | factory: uuid4 |  |
| `role` | `<class 'str'>` | **必填** | Role of the agent |
| `goal` | `<class 'str'>` | **必填** | Objective of the agent |
| `backstory` | `<class 'str'>` | **必填** | Backstory of the agent |
| `config` | `dict[str, typing.Any] \| None` | None | Configuration for the agent |
| `cache` | `<class 'bool'>` | True | Whether the agent should use a cache for tool usage. |
| `verbose` | `<class 'bool'>` | False | Verbose mode for the Agent Execution |
| `max_rpm` | `int \| None` | None | Maximum number of requests per minute for the agent execution to be respected. |
| `allow_delegation` | `<class 'bool'>` | False | Enable agent to delegate and ask questions among each other. |
| `tools` | `list[crewai.tools.base_tool.BaseTool] \| None` | factory: list | Tools at agents' disposal |
| `max_iter` | `<class 'int'>` | 25 | Maximum iterations for an agent to execute a task |
| `agent_executor` | `crewai.agents.crew_agent_executor.CrewAgentExecutor \| crewai.experimental.agent_executor.AgentExecutor \| None` | None | An instance of the CrewAgentExecutor class. |
| `llm` | `str \| crewai.llms.base_llm.BaseLLM \| None` | None | Language model that will run the agent. |
| `crew` | `crewai.crew.Crew \| str \| None` | None | Crew to which the agent belongs. |
| `cache_handler` | `crewai.agents.cache.cache_handler.CacheHandler \| None` | None | An instance of the CacheHandler class. |
| `tools_handler` | `<class 'crewai.agents.tools_handler.ToolsHandler'>` | factory: ToolsHandler | An instance of the ToolsHandler class. |
| `tools_results` | `list[dict[str, typing.Any]]` | factory: list | Results of the tools used by the agent. |
| `max_tokens` | `int \| None` | None | Maximum number of tokens for the agent's execution. |
| `knowledge` | `crewai.knowledge.knowledge.Knowledge \| None` | None | Knowledge for the agent. |
| `knowledge_sources` | `list[crewai.knowledge.source.base_knowledge_source.BaseKnowledgeSource] \| None` | None | Knowledge sources for the agent. |
| `knowledge_storage` | `crewai.knowledge.storage.base_knowledge_storage.BaseKnowledgeStorage \| None` | None | Custom knowledge storage for the agent. |
| `security_config` | `<class 'crewai.security.security_config.SecurityConfig'>` | factory: SecurityConfig | Security configuration for the agent, including fingerprinting. |
| `checkpoint` | `crewai.state.checkpoint_config.CheckpointConfig \| bool \| None` | None | Automatic checkpointing configuration. True for defaults, False to opt out, None to inherit. |
| `callbacks` | `list[typing.Annotated[collections.abc.Callable[..., typing.Any], BeforeValidator(func=<function string_to_callable at 0x7f91f4b8ca40>, json_schema_input_type=PydanticUndefined), PlainSerializer(func=<function callable_to_string at 0x7f91f4b8ccc0>, return_type=<class 'str'>, when_used='json'), WithJsonSchema(json_schema={'type': 'string'}, mode=None)]]` | factory: list | Callbacks to be used for the agent |
| `adapted_agent` | `<class 'bool'>` | False | Whether the agent is adapted |
| `knowledge_config` | `crewai.knowledge.knowledge_config.KnowledgeConfig \| None` | None | Knowledge configuration for the agent such as limits and threshold |
| `apps` | `list[typing.Union[typing.Literal['asana', 'box', 'clickup', 'github', 'gmail', 'google_calendar', 'google_sheets', 'hubspot', 'jira', 'linear', 'notion', 'salesforce', 'shopify', 'slack', 'stripe', 'zendesk'], str]] \| None` | None | List of applications or application/action combinations that the agent can access through CrewAI Platform. Can contain app names (e.g., 'gmail') or specific actions (e.g., 'gmail/send_email') |
| `mcps` | `list[str \| crewai.mcp.config.MCPServerStdio \| crewai.mcp.config.MCPServerHTTP \| crewai.mcp.config.MCPServerSSE] \| None` | None | List of MCP server references. Supports 'https://server.com/path' for external servers and bare slugs like 'notion' for connected MCP integrations. Use '#tool_name' suffix for specific tools. |
| `memory` | `bool \| crewai.memory.unified_memory.Memory \| crewai.memory.memory_scope.MemoryScope \| crewai.memory.memory_scope.MemorySlice \| None` | None | Enable agent memory. Pass True for default Memory(), or a Memory/MemoryScope/MemorySlice instance for custom configuration. If not set, falls back to crew memory. |
| `skills` | `list[pathlib.Path \| crewai.skills.models.Skill] \| None` | None | Agent Skills. Accepts paths for discovery or pre-loaded Skill objects. |
| `execution_context` | `crewai.context.ExecutionContext \| None` | None |  |
| `checkpoint_kickoff_event_id` | `str \| None` | None |  |
| `max_execution_time` | `int \| None` | None | Maximum execution time for an agent to execute a task |
| `step_callback` | `typing.Optional[typing.Annotated[collections.abc.Callable[..., typing.Any], BeforeValidator(func=<function string_to_callable at 0x7f91f4b8ca40>, json_schema_input_type=PydanticUndefined), PlainSerializer(func=<function callable_to_string at 0x7f91f4b8ccc0>, return_type=<class 'str'>, when_used='json'), WithJsonSchema(json_schema={'type': 'string'}, mode=None)]]` | None | Callback to be executed after each step of the agent execution. |
| `use_system_prompt` | `bool \| None` | True | Use system prompt for the agent. |
| `function_calling_llm` | `str \| crewai.llms.base_llm.BaseLLM \| None` | None | Language model that will run the agent. |
| `system_template` | `str \| None` | None | System format for the agent. |
| `prompt_template` | `str \| None` | None | Prompt format for the agent. |
| `response_template` | `str \| None` | None | Response format for the agent. |
| `allow_code_execution` | `bool \| None` | False | Deprecated. CodeInterpreterTool is no longer available. Use dedicated sandbox services instead. |
| `respect_context_window` | `<class 'bool'>` | True | Keep messages under the context window size by summarizing content. |
| `max_retry_limit` | `<class 'int'>` | 2 | Maximum number of retries for an agent to execute a task when an error occurs. |
| `multimodal` | `<class 'bool'>` | False | [DEPRECATED, will be removed in v2.0 - pass files natively.] Whether the agent is multimodal. |
| `inject_date` | `<class 'bool'>` | False | Whether to automatically inject the current date into tasks. |
| `date_format` | `<class 'str'>` | '%Y-%m-%d' | Format string for date when inject_date is enabled. |
| `code_execution_mode` | `typing.Literal['safe', 'unsafe']` | 'safe' | Deprecated. CodeInterpreterTool is no longer available. Use dedicated sandbox services instead. |
| `planning_config` | `crewai.agent.planning_config.PlanningConfig \| None` | None | Configuration for agent planning before task execution. |
| `planning` | `<class 'bool'>` | False | Whether the agent should reflect and create a plan before executing a task. |
| `reasoning` | `<class 'bool'>` | False | [DEPRECATED: Use planning_config instead] Whether the agent should reflect and create a plan before executing a task. |
| `max_reasoning_attempts` | `int \| None` | None | [DEPRECATED: Use planning_config.max_attempts instead] Maximum number of reasoning attempts before executing the task. If None, will try until ready. |
| `embedder` | `crewai.rag.embeddings.providers.microsoft.types.AzureProviderSpec \| crewai.rag.embeddings.providers.aws.types.BedrockProviderSpec \| crewai.rag.embeddings.providers.cohere.types.CohereProviderSpec \| crewai.rag.embeddings.providers.custom.types.CustomProviderSpec \| crewai.rag.embeddings.providers.google.types.GenerativeAiProviderSpec \| crewai.rag.embeddings.providers.huggingface.types.HuggingFaceProviderSpec \| crewai.rag.embeddings.providers.instructor.types.InstructorProviderSpec \| crewai.rag.embeddings.providers.jina.types.JinaProviderSpec \| crewai.rag.embeddings.providers.ollama.types.OllamaProviderSpec \| crewai.rag.embeddings.providers.onnx.types.ONNXProviderSpec \| crewai.rag.embeddings.providers.openai.types.OpenAIProviderSpec \| crewai.rag.embeddings.providers.openclip.types.OpenCLIPProviderSpec \| crewai.rag.embeddings.providers.roboflow.types.RoboflowProviderSpec \| crewai.rag.embeddings.providers.sentence_transformer.types.SentenceTransformerProviderSpec \| crewai.rag.embeddings.providers.text2vec.types.Text2VecProviderSpec \| crewai.rag.embeddings.providers.google.types.VertexAIProviderSpec \| crewai.rag.embeddings.providers.voyageai.types.VoyageAIProviderSpec \| crewai.rag.embeddings.providers.ibm.types.WatsonXProviderSpec \| crewai.rag.core.base_embeddings_provider.BaseEmbeddingsProvider[Any] \| type[crewai.rag.core.base_embeddings_provider.BaseEmbeddingsProvider[Any]] \| None` | None | Embedder configuration for the agent. |
| `agent_knowledge_context` | `str \| None` | None | Knowledge context for the agent. |
| `crew_knowledge_context` | `str \| None` | None | Knowledge context for the crew. |
| `knowledge_search_query` | `str \| None` | None | Knowledge search query for the agent dynamically generated by the agent. |
| `from_repository` | `str \| None` | None | The Agent's role to be used from your repository. |
| `guardrail` | `collections.abc.Callable[[crewai.tasks.task_output.TaskOutput \| crewai.lite_agent_output.LiteAgentOutput], tuple[bool, typing.Any]] \| str \| None` | None | Function or string description of a guardrail to validate agent output |
| `guardrail_max_retries` | `<class 'int'>` | 3 | Maximum number of retries when guardrail fails |
| `a2a` | `list[crewai.a2a.config.A2AConfig \| crewai.a2a.config.A2AServerConfig \| crewai.a2a.config.A2AClientConfig] \| crewai.a2a.config.A2AConfig \| crewai.a2a.config.A2AServerConfig \| crewai.a2a.config.A2AClientConfig \| None` | None |          A2A (Agent-to-Agent) configuration for delegating tasks to remote agents.         Can be a single A2AConfig/A2AClientConfig/A2AServerConfig, or a list of any number of A2AConfig/A2AClientConfig with a single A2AServerConfig.          |
| `executor_class` | `type[crewai.agents.crew_agent_executor.CrewAgentExecutor] \| type[crewai.experimental.agent_executor.AgentExecutor]` | <class 'crewai.agents.crew_agent_executor.CrewAgentExecutor'> | Class to use for the agent executor. Defaults to CrewAgentExecutor, can optionally use AgentExecutor. |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `aexecute_task` | `(task: 'Task', context: 'str \| None' = None, tools: 'list[BaseTool] \| None' = None) -> 'Any'` | Any | Execute a task with the agent asynchronously. |
| `akickoff` | `(messages: 'str \| list[LLMMessage]', response_format: 'type[Any] \| None' = None, input_files: 'dict[str, FileInput] \| None' = None, from_checkpoint: 'CheckpointConfig \| None' = None) -> 'LiteAgentOutput'` | LiteAgentOutput | Async version of kickoff. Alias for kickoff_async. |
| `copy` | `() -> 'Self'` | Self | Create a deep copy of the Agent. |
| `create_agent_executor` | `(tools: 'list[BaseTool] \| None' = None, task: 'Task \| None' = None) -> 'None'` | None | Create an agent executor for the agent. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `execute_task` | `(task: 'Task', context: 'str \| None' = None, tools: 'list[BaseTool] \| None' = None) -> 'Any'` | Any | Execute a task with the agent. |
| `fingerprint` | *(property)* | — | Get the agent's fingerprint. |
| `get_code_execution_tools` | `() -> 'list[Any]'` | list[Any] | Deprecated: CodeInterpreterTool is no longer available. |
| `get_delegation_tools` | `(agents: 'Sequence[BaseAgent]') -> 'list[BaseTool]'` | list[BaseTool] | Set the task tools that init BaseAgenTools class. |
| `get_mcp_tools` | `(mcps: 'list[str \| MCPServerConfig]') -> 'list[BaseTool]'` | list[BaseTool] | Convert MCP server references/configs to CrewAI tools. |
| `get_multimodal_tools` | `() -> 'Sequence[BaseTool]'` | Sequence[BaseTool] | Return tools for multimodal agent capabilities. |
| `get_output_converter` | `(llm: 'BaseLLM', text: 'str', model: 'type[BaseModel]', instructions: 'str') -> 'Converter'` | Converter | Create a Converter instance for transforming LLM output to a structured model. |
| `get_platform_tools` | `(apps: 'list[PlatformAppOrAction]') -> 'list[BaseTool]'` | list[BaseTool] | Get platform tools for the specified list of applications and/or application/action combinations. |
| `interpolate_inputs` | `(inputs: 'dict[str, Any]') -> 'None'` | None | Interpolate inputs into the agent description and backstory. |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `key` | *(property)* | — |  |
| `kickoff` | `(messages: 'str \| list[LLMMessage]', response_format: 'type[Any] \| None' = None, input_files: 'dict[str, FileInput] \| None' = None, from_checkpoint: 'CheckpointConfig \| None' = None) -> 'LiteAgentOutput \| Coroutine[Any, Any, LiteAgentOutput]'` | LiteAgentOutput \| Coroutine[Any, Any, LiteAgentOutput] | Execute the agent with the given messages using the AgentExecutor. |
| `kickoff_async` | `(messages: 'str \| list[LLMMessage]', response_format: 'type[Any] \| None' = None, input_files: 'dict[str, FileInput] \| None' = None, from_checkpoint: 'CheckpointConfig \| None' = None) -> 'LiteAgentOutput'` | LiteAgentOutput | Execute the agent asynchronously with the given messages. |
| `last_messages` | *(property)* | — | Get messages from the last task execution. |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(self: 'BaseModel', context: 'Any', /) -> 'None'` | None | This function is meant to behave like a BaseModel method to initialise private attributes. |
| `planning_enabled` | *(property)* | — | Check if planning is enabled for this agent. |
| `post_init_setup` | `(self: Any) -> Any` | typing.Any | Wrap post_init_setup to apply extensions after initialization. |
| `resolve_memory` | `() -> 'Self'` | Self | Resolve memory field: True creates a default Memory(), instance is used as-is. |
| `set_cache_handler` | `(cache_handler: 'CacheHandler') -> 'None'` | None | Set the cache handler for the agent. |
| `set_fingerprint` | `(fingerprint: 'Fingerprint') -> 'None'` | None | Set the agent's security fingerprint. |
| `set_knowledge` | `(crew_embedder: 'EmbedderConfig \| None' = None) -> 'None'` | None | Initialize knowledge sources with the agent or crew embedder config. |
| `set_private_attrs` | `() -> 'Self'` | Self | Set private attributes. |
| `set_rpm_controller` | `(rpm_controller: 'RPMController') -> 'None'` | None | Set the rpm controller for the agent. |
| `set_skills` | `(resolved_crew_skills: 'list[SkillModel] \| None' = None) -> 'None'` | None | Resolve skill paths while preserving explicit disclosure levels. |
| `validate_and_set_attributes` | `() -> 'Self'` | Self |  |

### Task

**模块：** `crewai.task`

**说明：** Class that represents a task to be executed.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `used_tools` | `<class 'int'>` | 0 |  |
| `tools_errors` | `<class 'int'>` | 0 |  |
| `delegations` | `<class 'int'>` | 0 |  |
| `name` | `str \| None` | None |  |
| `prompt_context` | `str \| None` | None |  |
| `description` | `<class 'str'>` | **必填** | Description of the actual task. |
| `expected_output` | `<class 'str'>` | **必填** | Clear definition of expected output for the task. |
| `config` | `dict[str, typing.Any] \| None` | None | Configuration for the agent |
| `callback` | `typing.Optional[typing.Annotated[collections.abc.Callable[..., typing.Any], BeforeValidator(func=<function string_to_callable at 0x7f91f4b8ca40>, json_schema_input_type=PydanticUndefined), PlainSerializer(func=<function callable_to_string at 0x7f91f4b8ccc0>, return_type=<class 'str'>, when_used='json'), WithJsonSchema(json_schema={'type': 'string'}, mode=None)]]` | None | Callback to be executed after the task is completed. |
| `agent` | `crewai.agents.agent_builder.base_agent.BaseAgent \| None` | None | Agent responsible for execution the task. |
| `context` | `list[crewai.task.Task] \| None \| crewai.utilities.constants._NotSpecified` | NOT_SPECIFIED | Other tasks that will have their output used as context for this task. |
| `async_execution` | `bool \| None` | False | Whether the task should be executed asynchronously or not. |
| `output_json` | `type[pydantic.main.BaseModel] \| None` | None | A Pydantic model to be used to create a JSON output. |
| `output_pydantic` | `type[pydantic.main.BaseModel] \| None` | None | A Pydantic model to be used to create a Pydantic output. |
| `response_model` | `type[pydantic.main.BaseModel] \| None` | None | A Pydantic model for structured LLM outputs using native provider features. |
| `output_file` | `str \| None` | None | A file path to be used to create a file output. |
| `create_directory` | `bool \| None` | True | Whether to create the directory for output_file if it doesn't exist. |
| `output` | `crewai.tasks.task_output.TaskOutput \| None` | None | Task output, it's final result after being executed |
| `tools` | `list[crewai.tools.base_tool.BaseTool] \| None` | factory: list | Tools the agent is limited to use for this task. |
| `input_files` | `dict[str, typing.Any]` | factory: dict | Named input files for this task. Keys are reference names, values are paths or File objects. |
| `security_config` | `<class 'crewai.security.security_config.SecurityConfig'>` | factory: SecurityConfig | Security configuration for the task. |
| `id` | `<class 'uuid.UUID'>` | factory: uuid4 | Unique identifier for the object, not set by user. |
| `human_input` | `bool \| None` | False | Whether the task should have a human review the final answer of the agent |
| `markdown` | `bool \| None` | False | Whether the task should instruct the agent to return the final answer formatted in Markdown |
| `converter_cls` | `type[crewai.utilities.converter.Converter] \| None` | None | A converter class used to export structured output |
| `processed_by_agents` | `set[str]` | factory: set |  |
| `guardrail` | `collections.abc.Callable[[crewai.tasks.task_output.TaskOutput \| crewai.lite_agent_output.LiteAgentOutput], tuple[bool, typing.Any]] \| str \| None` | None | Function or string description of a guardrail to validate task output before proceeding to next task |
| `guardrails` | `collections.abc.Sequence[collections.abc.Callable[[crewai.tasks.task_output.TaskOutput \| crewai.lite_agent_output.LiteAgentOutput], tuple[bool, typing.Any]] \| str] \| collections.abc.Callable[[crewai.tasks.task_output.TaskOutput \| crewai.lite_agent_output.LiteAgentOutput], tuple[bool, typing.Any]] \| str \| None` | None | List of guardrails to validate task output before proceeding to next task. Also supports a single guardrail function or string description of a guardrail to validate task output before proceeding to next task |
| `max_retries` | `int \| None` | None | [DEPRECATED] Maximum number of retries when guardrail fails. Use guardrail_max_retries instead. Will be removed in v1.0.0 |
| `guardrail_max_retries` | `<class 'int'>` | 3 | Maximum number of retries when guardrail fails |
| `retry_count` | `<class 'int'>` | 0 | Current number of retries |
| `start_time` | `datetime.datetime \| None` | None | Start time of the task execution |
| `end_time` | `datetime.datetime \| None` | None | End time of the task execution |
| `allow_crewai_trigger_context` | `bool \| None` | None | Whether this task should append 'Trigger Payload: {crewai_trigger_payload}' to the task description when crewai_trigger_payload exists in crew inputs. |
| `checkpoint_original_description` | `str \| None` | None |  |
| `checkpoint_original_expected_output` | `str \| None` | None |  |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `aexecute_sync` | `(agent: 'BaseAgent \| None' = None, context: 'str \| None' = None, tools: 'list[BaseTool] \| None' = None) -> 'TaskOutput'` | TaskOutput | Execute the task asynchronously using native async/await. |
| `check_output` | `() -> 'Self'` | Self | Check if an output type is set. |
| `check_tools` | `() -> 'Self'` | Self | Check if the tools are set. |
| `copy` | `(agents: 'Sequence[BaseAgent]', task_mapping: 'dict[str, Task]') -> 'Task'` | Task | Creates a deep copy of the Task while preserving its original class type. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `ensure_guardrail_is_callable` | `() -> 'Task'` | Task |  |
| `ensure_guardrails_is_list_of_callables` | `() -> 'Task'` | Task |  |
| `execute_async` | `(agent: 'BaseAgent \| None' = None, context: 'str \| None' = None, tools: 'list[BaseTool] \| None' = None) -> 'Future[TaskOutput]'` | Future[TaskOutput] | Execute the task asynchronously. |
| `execute_sync` | `(agent: 'BaseAgent \| None' = None, context: 'str \| None' = None, tools: 'list[BaseTool] \| None' = None) -> 'TaskOutput'` | TaskOutput | Execute the task synchronously. |
| `execution_duration` | *(property)* | — |  |
| `fingerprint` | *(property)* | — | Get the fingerprint of the task. |
| `handle_max_retries_deprecation` | `() -> 'Self'` | Self |  |
| `increment_delegations` | `(agent_name: 'str \| None') -> 'None'` | None | Increment the delegations counter. |
| `increment_tools_errors` | `() -> 'None'` | None | Increment the tools errors counter. |
| `interpolate_inputs_and_add_conversation_history` | `(inputs: 'dict[str, str \| int \| float \| dict[str, Any] \| list[Any]]') -> 'None'` | None | Interpolate inputs into the task description, expected output, and output file path. |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `key` | *(property)* | — |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(self: 'BaseModel', context: 'Any', /) -> 'None'` | None | This function is meant to behave like a BaseModel method to initialise private attributes. |
| `prompt` | `() -> 'str'` | str | Generates the task prompt with optional markdown formatting. |
| `set_attributes_based_on_config` | `() -> 'Task'` | Task | Set attributes based on the agent configuration. |
| `validate_required_fields` | `() -> 'Self'` | Self |  |

### Crew

**模块：** `crewai.crew`

**说明：** Represents a group of agents, defining how they should collaborate and the tasks they should perform.

**父类：** FlowTrackable, BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `entity_type` | `typing.Literal['crew']` | 'crew' |  |
| `name` | `str \| None` | 'crew' |  |
| `cache` | `<class 'bool'>` | True |  |
| `tasks` | `list[crewai.task.Task]` | factory: list |  |
| `agents` | `list[crewai.agents.agent_builder.base_agent.BaseAgent]` | factory: list |  |
| `process` | `<enum 'Process'>` | <Process.sequential: 'sequential'> |  |
| `verbose` | `<class 'bool'>` | False |  |
| `memory` | `bool \| crewai.memory.unified_memory.Memory \| crewai.memory.memory_scope.MemoryScope \| crewai.memory.memory_scope.MemorySlice \| None` | False | Enable crew memory. Pass True for default Memory(), or a Memory/MemoryScope/MemorySlice instance for custom configuration. |
| `embedder` | `crewai.rag.embeddings.providers.microsoft.types.AzureProviderSpec \| crewai.rag.embeddings.providers.aws.types.BedrockProviderSpec \| crewai.rag.embeddings.providers.cohere.types.CohereProviderSpec \| crewai.rag.embeddings.providers.custom.types.CustomProviderSpec \| crewai.rag.embeddings.providers.google.types.GenerativeAiProviderSpec \| crewai.rag.embeddings.providers.huggingface.types.HuggingFaceProviderSpec \| crewai.rag.embeddings.providers.instructor.types.InstructorProviderSpec \| crewai.rag.embeddings.providers.jina.types.JinaProviderSpec \| crewai.rag.embeddings.providers.ollama.types.OllamaProviderSpec \| crewai.rag.embeddings.providers.onnx.types.ONNXProviderSpec \| crewai.rag.embeddings.providers.openai.types.OpenAIProviderSpec \| crewai.rag.embeddings.providers.openclip.types.OpenCLIPProviderSpec \| crewai.rag.embeddings.providers.roboflow.types.RoboflowProviderSpec \| crewai.rag.embeddings.providers.sentence_transformer.types.SentenceTransformerProviderSpec \| crewai.rag.embeddings.providers.text2vec.types.Text2VecProviderSpec \| crewai.rag.embeddings.providers.google.types.VertexAIProviderSpec \| crewai.rag.embeddings.providers.voyageai.types.VoyageAIProviderSpec \| crewai.rag.embeddings.providers.ibm.types.WatsonXProviderSpec \| crewai.rag.core.base_embeddings_provider.BaseEmbeddingsProvider[Any] \| type[crewai.rag.core.base_embeddings_provider.BaseEmbeddingsProvider[Any]] \| None` | None | Configuration for the embedder to be used for the crew. |
| `usage_metrics` | `crewai.types.usage_metrics.UsageMetrics \| None` | None | Metrics for the LLM usage during all tasks execution. |
| `manager_llm` | `str \| crewai.llms.base_llm.BaseLLM \| None` | None | Language model that will run the agent. |
| `manager_agent` | `crewai.agents.agent_builder.base_agent.BaseAgent \| None` | None | Custom agent that will be used as manager. |
| `function_calling_llm` | `str \| crewai.llm.LLM \| None` | None | Language model that will run the agent. |
| `config` | `typing.Union[typing.Annotated[dict[str, typing.Any], Json], dict[str, typing.Any], NoneType]` | None |  |
| `id` | `<class 'uuid.UUID'>` | factory: uuid4 |  |
| `share_crew` | `bool \| None` | False |  |
| `step_callback` | `typing.Optional[typing.Annotated[collections.abc.Callable[..., typing.Any], BeforeValidator(func=<function string_to_callable at 0x7f91f4b8ca40>, json_schema_input_type=PydanticUndefined), PlainSerializer(func=<function callable_to_string at 0x7f91f4b8ccc0>, return_type=<class 'str'>, when_used='json'), WithJsonSchema(json_schema={'type': 'string'}, mode=None)]]` | None | Callback to be executed after each step for all agents execution. |
| `task_callback` | `typing.Optional[typing.Annotated[collections.abc.Callable[..., typing.Any], BeforeValidator(func=<function string_to_callable at 0x7f91f4b8ca40>, json_schema_input_type=PydanticUndefined), PlainSerializer(func=<function callable_to_string at 0x7f91f4b8ccc0>, return_type=<class 'str'>, when_used='json'), WithJsonSchema(json_schema={'type': 'string'}, mode=None)]]` | None | Callback to be executed after each task for all agents execution. |
| `before_kickoff_callbacks` | `list[typing.Annotated[collections.abc.Callable[..., typing.Any], BeforeValidator(func=<function string_to_callable at 0x7f91f4b8ca40>, json_schema_input_type=PydanticUndefined), PlainSerializer(func=<function callable_to_string at 0x7f91f4b8ccc0>, return_type=<class 'str'>, when_used='json'), WithJsonSchema(json_schema={'type': 'string'}, mode=None)]]` | factory: list | List of callbacks to be executed before crew kickoff. It may be used to adjust inputs before the crew is executed. |
| `after_kickoff_callbacks` | `list[typing.Annotated[collections.abc.Callable[..., typing.Any], BeforeValidator(func=<function string_to_callable at 0x7f91f4b8ca40>, json_schema_input_type=PydanticUndefined), PlainSerializer(func=<function callable_to_string at 0x7f91f4b8ccc0>, return_type=<class 'str'>, when_used='json'), WithJsonSchema(json_schema={'type': 'string'}, mode=None)]]` | factory: list | List of callbacks to be executed after crew kickoff. It may be used to adjust the output of the crew. |
| `stream` | `<class 'bool'>` | False | Whether to stream output from the crew execution. |
| `max_rpm` | `int \| None` | None | Maximum number of requests per minute for the crew execution to be respected. |
| `prompt_file` | `str \| None` | None | Path to the prompt json file to be used for the crew. |
| `output_log_file` | `bool \| str \| None` | None | Path to the log file to be saved |
| `planning` | `bool \| None` | False | Plan the crew execution and add the plan to the crew. |
| `planning_llm` | `str \| crewai.llms.base_llm.BaseLLM \| None` | None | Language model that will run the AgentPlanner if planning is True. |
| `task_execution_output_json_files` | `list[str] \| None` | None | list of file paths for task execution JSON files. |
| `execution_logs` | `list[dict[str, typing.Any]]` | factory: list | list of execution logs for tasks |
| `knowledge_sources` | `list[crewai.knowledge.source.base_knowledge_source.BaseKnowledgeSource] \| None` | None | Knowledge sources for the crew. Add knowledge sources to the knowledge object. |
| `chat_llm` | `str \| crewai.llms.base_llm.BaseLLM \| None` | None | LLM used to handle chatting with the crew. |
| `knowledge` | `crewai.knowledge.knowledge.Knowledge \| None` | None | Knowledge for the crew. |
| `skills` | `list[pathlib.Path \| crewai.skills.models.Skill] \| None` | None | Skill search paths or pre-loaded Skill objects applied to all agents in the crew. |
| `security_config` | `<class 'crewai.security.security_config.SecurityConfig'>` | factory: SecurityConfig | Security configuration for the crew, including fingerprinting. |
| `checkpoint` | `crewai.state.checkpoint_config.CheckpointConfig \| bool \| None` | None | Automatic checkpointing configuration. True for defaults, False to opt out, None to inherit. |
| `token_usage` | `crewai.types.usage_metrics.UsageMetrics \| None` | None | Metrics for the LLM usage during all tasks execution. |
| `tracing` | `bool \| None` | None | Whether to enable tracing for the crew. True=always enable, False=always disable, None=check environment/user settings. |
| `execution_context` | `crewai.context.ExecutionContext \| None` | None |  |
| `checkpoint_inputs` | `dict[str, typing.Any] \| None` | None |  |
| `checkpoint_train` | `bool \| None` | None |  |
| `checkpoint_kickoff_event_id` | `str \| None` | None |  |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `akickoff` | `(inputs: 'dict[str, Any] \| None' = None, input_files: 'dict[str, FileInput] \| None' = None, from_checkpoint: 'CheckpointConfig \| None' = None) -> 'CrewOutput \| CrewStreamingOutput'` | CrewOutput \| CrewStreamingOutput | Native async kickoff method using async task execution throughout. |
| `akickoff_for_each` | `(inputs: 'list[dict[str, Any]]', input_files: 'dict[str, FileInput] \| None' = None) -> 'list[CrewOutput \| CrewStreamingOutput] \| CrewStreamingOutput'` | list[CrewOutput \| CrewStreamingOutput] \| CrewStreamingOutput | Native async execution of the Crew's workflow for each input. |
| `aquery_knowledge` | `(query: 'list[str]', results_limit: 'int' = 3, score_threshold: 'float' = 0.35) -> 'list[SearchResult] \| None'` | list[SearchResult] \| None | Query the crew's knowledge base for relevant information asynchronously. |
| `calculate_usage_metrics` | `() -> 'UsageMetrics'` | UsageMetrics | Calculates and returns the usage metrics. |
| `check_config` | `() -> 'Self'` | Self | Validates that the crew is properly configured with agents and tasks. |
| `check_manager_llm` | `() -> 'Self'` | Self | Validates that the language model is set when using hierarchical process. |
| `copy` | `() -> 'Crew'` | Crew | Creates a deep copy of the Crew instance. |
| `create_crew_knowledge` | `() -> 'Crew'` | Crew | Create the knowledge for the crew. |
| `create_crew_memory` | `() -> 'Crew'` | Crew | Initialize unified memory, respecting crew embedder config. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `fetch_inputs` | `() -> 'set[str]'` | set[str] | Gathers placeholders (e.g., {something}) referenced in tasks or agents. |
| `fingerprint` | *(property)* | — | Get the crew's fingerprint. |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `key` | *(property)* | — |  |
| `kickoff` | `(inputs: 'dict[str, Any] \| None' = None, input_files: 'dict[str, FileInput] \| None' = None, from_checkpoint: 'CheckpointConfig \| None' = None) -> 'CrewOutput \| CrewStreamingOutput'` | CrewOutput \| CrewStreamingOutput | Execute the crew's workflow. |
| `kickoff_async` | `(inputs: 'dict[str, Any] \| None' = None, input_files: 'dict[str, FileInput] \| None' = None, from_checkpoint: 'CheckpointConfig \| None' = None) -> 'CrewOutput \| CrewStreamingOutput'` | CrewOutput \| CrewStreamingOutput | Asynchronous kickoff method to start the crew execution. |
| `kickoff_for_each` | `(inputs: 'list[dict[str, Any]]', input_files: 'dict[str, FileInput] \| None' = None) -> 'list[CrewOutput \| CrewStreamingOutput]'` | list[CrewOutput \| CrewStreamingOutput] | Executes the Crew's workflow for each input and aggregates results. |
| `kickoff_for_each_async` | `(inputs: 'list[dict[str, Any]]', input_files: 'dict[str, FileInput] \| None' = None) -> 'list[CrewOutput \| CrewStreamingOutput] \| CrewStreamingOutput'` | list[CrewOutput \| CrewStreamingOutput] \| CrewStreamingOutput | Executes the Crew's workflow for each input asynchronously. |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(self: 'BaseModel', context: 'Any', /) -> 'None'` | None | This function is meant to behave like a BaseModel method to initialise private attributes. |
| `query_knowledge` | `(query: 'list[str]', results_limit: 'int' = 3, score_threshold: 'float' = 0.35) -> 'list[SearchResult] \| None'` | list[SearchResult] \| None | Query the crew's knowledge base for relevant information. |
| `replay` | `(task_id: 'str', inputs: 'dict[str, Any] \| None' = None) -> 'CrewOutput'` | CrewOutput | Replay the crew execution from a specific task. |
| `reset_knowledge` | `(knowledges: 'list[Knowledge]') -> 'None'` | None | Reset crew and agent knowledge storage. |
| `reset_memories` | `(command_type: 'str') -> 'None'` | None | Reset specific or all memories for the crew. |
| `set_private_attrs` | `() -> 'Crew'` | Crew | set private attributes. |
| `test` | `(n_iterations: 'int', eval_llm: 'str \| BaseLLM', inputs: 'dict[str, Any] \| None' = None) -> 'None'` | None | Test and evaluate the Crew with the given inputs for n iterations. |
| `train` | `(n_iterations: 'int', filename: 'str', inputs: 'dict[str, Any] \| None' = None) -> 'None'` | None | Trains the crew for a given number of iterations. |
| `validate_async_task_cannot_include_sequential_async_tasks_in_context` | `() -> 'Self'` | Self | Validates that if a task is set to be executed asynchronously, |
| `validate_async_tasks_not_async` | `() -> 'Crew'` | Crew | Ensure that ConditionalTask is not async. |
| `validate_context_no_future_tasks` | `() -> 'Self'` | Self | Validates that a task's context does not include future tasks. |
| `validate_end_with_at_most_one_async_task` | `() -> 'Self'` | Self | Validates that the crew ends with at most one asynchronous task. |
| `validate_first_task` | `() -> 'Crew'` | Crew | Ensure the first task is not a ConditionalTask. |
| `validate_must_have_non_conditional_task` | `() -> 'Crew'` | Crew | Ensure that a crew has at least one non-conditional task. |
| `validate_tasks` | `() -> 'Self'` | Self |  |

### Flow

**模块：** `crewai.flow.flow`

**说明：** Base class for all flows.

**父类：** BaseModel, Generic

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `entity_type` | `typing.Literal['flow']` | 'flow' |  |
| `initial_state` | `type[pydantic.main.BaseModel] \| type[dict] \| dict[str, typing.Any] \| pydantic.main.BaseModel \| None` | None |  |
| `name` | `str \| None` | None |  |
| `tracing` | `bool \| None` | None |  |
| `stream` | `<class 'bool'>` | False |  |
| `memory` | `crewai.memory.unified_memory.Memory \| crewai.memory.memory_scope.MemoryScope \| crewai.memory.memory_scope.MemorySlice \| None` | None |  |
| `input_provider` | `crewai.flow.input_provider.InputProvider \| None` | None |  |
| `suppress_flow_events` | `<class 'bool'>` | False |  |
| `human_feedback_history` | `list[crewai.flow.human_feedback.HumanFeedbackResult]` | factory: list |  |
| `last_human_feedback` | `crewai.flow.human_feedback.HumanFeedbackResult \| None` | None |  |
| `persistence` | `typing.Union[typing.Annotated[crewai.flow.persistence.base.FlowPersistence, SerializeAsAny()], typing.Any]` | None |  |
| `max_method_calls` | `<class 'int'>` | 100 |  |
| `execution_context` | `crewai.context.ExecutionContext \| None` | None |  |
| `checkpoint` | `crewai.state.checkpoint_config.CheckpointConfig \| bool \| None` | None |  |
| `checkpoint_completed_methods` | `set[str] \| None` | None |  |
| `checkpoint_method_outputs` | `list[typing.Any] \| None` | None |  |
| `checkpoint_method_counts` | `dict[str, int] \| None` | None |  |
| `checkpoint_state` | `dict[str, typing.Any] \| None` | None |  |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `akickoff` | `(inputs: 'dict[str, Any] \| None' = None, input_files: 'dict[str, FileInput] \| None' = None, from_checkpoint: 'CheckpointConfig \| None' = None) -> 'Any \| FlowStreamingOutput'` | Any \| FlowStreamingOutput | Native async method to start the flow execution. Alias for kickoff_async. |
| `ask` | `(message: 'str', timeout: 'float \| None' = None, metadata: 'dict[str, Any] \| None' = None) -> 'str \| None'` | str \| None | Request input from the user during flow execution. |
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `execution_id` | *(property)* | — | Stable identifier for this flow execution. |
| `extract_memories` | `(content: 'str') -> 'list[str]'` | list[str] | Extract discrete memories from content. Delegates to this flow's memory. |
| `flow_id` | *(property)* | — | Returns the unique identifier of this flow instance. |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `kickoff` | `(inputs: 'dict[str, Any] \| None' = None, input_files: 'dict[str, FileInput] \| None' = None, from_checkpoint: 'CheckpointConfig \| None' = None) -> 'Any \| FlowStreamingOutput'` | Any \| FlowStreamingOutput | Start the flow execution in a synchronous context. |
| `kickoff_async` | `(inputs: 'dict[str, Any] \| None' = None, input_files: 'dict[str, FileInput] \| None' = None, from_checkpoint: 'CheckpointConfig \| None' = None) -> 'Any \| FlowStreamingOutput'` | Any \| FlowStreamingOutput | Start the flow execution asynchronously. |
| `method_outputs` | *(property)* | — | Returns the list of all outputs from executed methods. |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(_Flow__context: 'Any') -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |
| `pending_feedback` | *(property)* | — | Get the pending feedback context if this flow is waiting for feedback. |
| `plot` | `(filename: 'str' = 'crewai_flow.html', show: 'bool' = True) -> 'str'` | str | Create interactive HTML visualization of Flow structure. |
| `recall` | `(query: 'str', **kwargs: 'Any') -> 'Any'` | Any | Recall relevant memories. Delegates to this flow's memory. |
| `reload` | `(execution_data: 'FlowExecutionData') -> 'None'` | None | Reloads the flow from an execution data dict. |
| `remember` | `(content: 'str \| list[str]', **kwargs: 'Any') -> 'Any'` | Any | Store one or more items in memory. |
| `resume` | `(feedback: 'str' = '') -> 'Any'` | Any | Resume flow execution, optionally with human feedback. |
| `resume_async` | `(feedback: 'str' = '') -> 'Any'` | Any | Async version of resume. |
| `state` | *(property)* | — |  |

---

## 二、工具类

### BaseTool

**模块：** `crewai.tools.base_tool`

**说明：** !!! abstract "Usage Documentation"     [Models](../concepts/models.md)

**父类：** BaseModel, ABC

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `name` | `<class 'str'>` | **必填** | The unique name of the tool that clearly communicates its purpose. |
| `description` | `<class 'str'>` | **必填** | Used to tell the model how/when/why to use the tool. |
| `env_vars` | `list[crewai.tools.base_tool.EnvVar]` | factory: list | List of environment variables used by the tool. |
| `args_schema` | `type[pydantic.main.BaseModel]` | <class 'crewai.tools.base_tool.BaseTool._ArgsSchemaPlaceholder'> | The schema for the arguments that the tool accepts. |
| `description_updated` | `<class 'bool'>` | False | Flag to check if the description has been updated. |
| `cache_function` | `collections.abc.Callable[..., typing.Any]` | <function _default_cache_function at 0x7f91f4b8cae0> | Function that will be used to determine if the tool should be cached, should return a boolean. If None, the tool will be cached. |
| `result_as_answer` | `<class 'bool'>` | False | Flag to check if the tool should be the final agent answer. |
| `max_usage_count` | `int \| None` | None | Maximum number of times this tool can be used. None means unlimited usage. |
| `current_usage_count` | `<class 'int'>` | 0 | Current number of times this tool has been used. |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `arun` | `(*args: 'Any', **kwargs: 'Any') -> 'Any'` | Any | Execute the tool asynchronously. |
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(_BaseTool__context: 'Any') -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |
| `reset_usage_count` | `() -> 'None'` | None | Reset the current usage count to zero. |
| `run` | `(*args: 'Any', **kwargs: 'Any') -> 'Any'` | Any |  |
| `to_structured_tool` | `() -> 'CrewStructuredTool'` | CrewStructuredTool | Convert this tool to a CrewStructuredTool instance. |
| `tool_type` | *(property)* | — |  |

### ToolUsage

**模块：** `crewai.tools.tool_usage`

**说明：** Class that represents the usage of a tool by an agent.

**父类：** object

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `ause` | `(calling: 'ToolCalling \| InstructorToolCalling', tool_string: 'str') -> 'str'` | str | Execute a tool asynchronously. |
| `on_tool_error` | `(tool: 'Any', tool_calling: 'ToolCalling \| InstructorToolCalling', e: 'Exception') -> 'None'` | None |  |
| `on_tool_use_finished` | `(tool: 'Any', tool_calling: 'ToolCalling \| InstructorToolCalling', from_cache: 'bool', started_at: 'float', result: 'Any') -> 'None'` | None |  |
| `parse_tool_calling` | `(tool_string: 'str') -> 'ToolCalling \| InstructorToolCalling \| ToolUsageError'` | ToolCalling \| InstructorToolCalling \| ToolUsageError | Parse the tool string and return the tool calling. |
| `use` | `(calling: 'ToolCalling \| InstructorToolCalling', tool_string: 'str') -> 'str'` | str |  |

### tool()

**模块：** `crewai.tools`

**签名：** `(*args: 'Callable[P2, R2] \| str', result_as_answer: 'bool' = False, max_usage_count: 'int \| None' = None) -> 'Tool[P2, R2] \| Callable[[Callable[P2, R2]], Tool[P2, R2]]'`

**说明：** Decorator to create a Tool from a function.

---

## 三、模型类

### LLM

**模块：** `crewai.llm`

**说明：** Abstract base class for LLM implementations.

**父类：** BaseLLM

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `llm_type` | `typing.Literal['litellm']` | 'litellm' |  |
| `model` | `<class 'str'>` | **必填** |  |
| `temperature` | `float \| None` | None |  |
| `api_key` | `str \| None` | None |  |
| `base_url` | `str \| None` | None |  |
| `provider` | `<class 'str'>` | 'openai' |  |
| `prefer_upload` | `<class 'bool'>` | False |  |
| `is_litellm` | `<class 'bool'>` | False |  |
| `stop` | `list[str]` | factory: list |  |
| `additional_params` | `dict[str, typing.Any]` | factory: dict |  |
| `completion_cost` | `float \| None` | None |  |
| `timeout` | `float \| int \| None` | None |  |
| `top_p` | `float \| None` | None |  |
| `n` | `int \| None` | None |  |
| `max_completion_tokens` | `int \| None` | None |  |
| `max_tokens` | `int \| float \| None` | None |  |
| `presence_penalty` | `float \| None` | None |  |
| `frequency_penalty` | `float \| None` | None |  |
| `logit_bias` | `dict[int, float] \| None` | None |  |
| `response_format` | `crewai.llms.base_llm.JsonResponseFormat \| type[pydantic.main.BaseModel] \| None` | None |  |
| `seed` | `int \| None` | None |  |
| `logprobs` | `int \| None` | None |  |
| `top_logprobs` | `int \| None` | None |  |
| `api_base` | `str \| None` | None |  |
| `api_version` | `str \| None` | None |  |
| `callbacks` | `list[typing.Any] \| None` | None |  |
| `reasoning_effort` | `typing.Optional[typing.Literal['none', 'low', 'medium', 'high']]` | None |  |
| `stream` | `<class 'bool'>` | False |  |
| `interceptor` | `typing.Any` | None |  |
| `thinking` | `typing.Any` | None |  |
| `context_window_size` | `<class 'int'>` | 0 |  |
| `is_anthropic` | `<class 'bool'>` | False |  |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `acall` | `(messages: 'str \| list[LLMMessage]', tools: 'list[dict[str, BaseTool]] \| None' = None, callbacks: 'list[Any] \| None' = None, available_functions: 'dict[str, Any] \| None' = None, from_task: 'Task \| None' = None, from_agent: 'BaseAgent \| None' = None, response_model: 'type[BaseModel] \| None' = None) -> 'str \| Any'` | str \| Any | Async high-level LLM call method. |
| `call` | `(messages: 'str \| list[LLMMessage]', tools: 'list[dict[str, BaseTool]] \| None' = None, callbacks: 'list[Any] \| None' = None, available_functions: 'dict[str, Any] \| None' = None, from_task: 'Task \| None' = None, from_agent: 'BaseAgent \| None' = None, response_model: 'type[BaseModel] \| None' = None) -> 'str \| Any'` | str \| Any | High-level LLM call method. |
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `format_text_content` | `(text: 'str') -> 'dict[str, Any]'` | dict[str, Any] | Format text as a content block for the LLM. |
| `get_context_window_size` | `() -> 'int'` | int | Returns the context window size, using 75% of the maximum to avoid |
| `get_file_uploader` | `() -> 'Any'` | Any | Get a file uploader configured with this LLM's client. |
| `get_token_usage_summary` | `() -> 'UsageMetrics'` | UsageMetrics | Get summary of token usage for this LLM instance. |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(self: 'BaseModel', context: 'Any', /) -> 'None'` | None | This function is meant to behave like a BaseModel method to initialise private attributes. |
| `set_callbacks` | `(callbacks: 'list[Any]') -> 'None'` | None | Attempt to keep a single set of callbacks in litellm by removing old |
| `set_env_callbacks` | `() -> 'None'` | None | Sets the success and failure callbacks for the LiteLLM library from environment variables. |
| `stop_sequences` | *(property)* | — | Alias for ``stop`` — kept for backward compatibility with provider APIs. |
| `supports_function_calling` | `() -> 'bool'` | bool | Check if the model supports function calling. |
| `supports_multimodal` | `() -> 'bool'` | bool | Check if the model supports multimodal inputs. |
| `supports_stop_words` | `() -> 'bool'` | bool | Check if the model supports stop words. |
| `to_config_dict` | `() -> 'dict[str, Any]'` | dict[str, Any] | Serialize this LLM to a dict that can reconstruct it via ``LLM(**config)``. |

### BaseLLM

**模块：** `crewai.llms.base_llm`

**说明：** Abstract base class for LLM implementations.

**父类：** BaseModel, ABC

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `llm_type` | `<class 'str'>` | 'base' |  |
| `model` | `<class 'str'>` | **必填** |  |
| `temperature` | `float \| None` | None |  |
| `api_key` | `str \| None` | None |  |
| `base_url` | `str \| None` | None |  |
| `provider` | `<class 'str'>` | 'openai' |  |
| `prefer_upload` | `<class 'bool'>` | False |  |
| `is_litellm` | `<class 'bool'>` | False |  |
| `stop` | `list[str]` | factory: list |  |
| `additional_params` | `dict[str, typing.Any]` | factory: dict |  |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `acall` | `(messages: 'str \| list[LLMMessage]', tools: 'list[dict[str, BaseTool]] \| None' = None, callbacks: 'list[Any] \| None' = None, available_functions: 'dict[str, Any] \| None' = None, from_task: 'Task \| None' = None, from_agent: 'BaseAgent \| None' = None, response_model: 'type[BaseModel] \| None' = None) -> 'str \| Any'` | str \| Any | Call the LLM with the given messages. |
| `call` | `(messages: 'str \| list[LLMMessage]', tools: 'list[dict[str, BaseTool]] \| None' = None, callbacks: 'list[Any] \| None' = None, available_functions: 'dict[str, Any] \| None' = None, from_task: 'Task \| None' = None, from_agent: 'BaseAgent \| None' = None, response_model: 'type[BaseModel] \| None' = None) -> 'str \| Any'` | str \| Any | Call the LLM with the given messages. |
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `format_text_content` | `(text: 'str') -> 'dict[str, Any]'` | dict[str, Any] | Format text as a content block for the LLM. |
| `get_context_window_size` | `() -> 'int'` | int | Get the context window size for the LLM. |
| `get_file_uploader` | `() -> 'Any'` | Any | Get a file uploader configured with this LLM's client. |
| `get_token_usage_summary` | `() -> 'UsageMetrics'` | UsageMetrics | Get summary of token usage for this LLM instance. |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(self: 'BaseModel', context: 'Any', /) -> 'None'` | None | This function is meant to behave like a BaseModel method to initialise private attributes. |
| `stop_sequences` | *(property)* | — | Alias for ``stop`` — kept for backward compatibility with provider APIs. |
| `supports_multimodal` | `() -> 'bool'` | bool | Check if the LLM supports multimodal inputs. |
| `supports_stop_words` | `() -> 'bool'` | bool | Check if the LLM supports stop words. |
| `to_config_dict` | `() -> 'dict[str, Any]'` | dict[str, Any] | Serialize this LLM to a dict that can reconstruct it via ``LLM(**config)``. |

---

## 四、配置类

### PlanningConfig

**模块：** `crewai.agent.planning_config`

**说明：** Configuration for agent planning/reasoning before task execution.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `reasoning_effort` | `typing.Literal['low', 'medium', 'high']` | 'medium' | Controls post-step observation and replanning behavior. 'low' observes steps but skips replanning/refinement (fastest). 'medium' observes and replans only on step failure (balanced). 'high' runs full observation pipeline with replanning, refinement, and early goal detection (most adaptive, highest latency). |
| `max_attempts` | `int \| None` | None | Maximum number of planning refinement attempts. If None, will continue until the agent indicates readiness. |
| `max_steps` | `<class 'int'>` | 20 | Maximum number of steps in the generated plan. |
| `system_prompt` | `str \| None` | None | Custom system prompt for planning. Uses default if None. |
| `plan_prompt` | `str \| None` | None | Custom prompt for creating the initial plan. |
| `refine_prompt` | `str \| None` | None | Custom prompt for refining the plan. |
| `max_replans` | `<class 'int'>` | 3 | Maximum number of full replanning attempts before finalizing. |
| `max_step_iterations` | `<class 'int'>` | 15 | Maximum LLM iterations per step in the StepExecutor multi-turn loop. Lower values make steps faster but less thorough. |
| `step_timeout` | `int \| None` | None | Maximum wall-clock seconds for a single step execution. If exceeded, the step is marked as failed and observation decides whether to continue or replan. None means no per-step timeout. |
| `llm` | `str \| crewai.llms.base_llm.BaseLLM \| None` | None | LLM to use for planning. Uses agent's LLM if None. |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |

### SecurityConfig

**模块：** `crewai.security.security_config`

**说明：** Configuration for CrewAI security features.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `fingerprint` | `<class 'crewai.security.fingerprint.Fingerprint'>` | factory: Fingerprint | Unique identifier for the component |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |
| `to_dict` | `() -> dict[str, typing.Any]` | dict[str, typing.Any] | Convert the security config to a dictionary. |

### CheckpointConfig

**模块：** `crewai.state.checkpoint_config`

**说明：** Configuration for automatic checkpointing.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `location` | `<class 'str'>` | './.checkpoints' | Storage destination. For JsonProvider this is a directory path; for SqliteProvider it is a database file path. |
| `on_events` | `list[typing.Union[typing.Literal['task_started', 'task_completed', 'task_failed', 'task_evaluation', 'crew_kickoff_started', 'crew_kickoff_completed', 'crew_kickoff_failed', 'crew_train_started', 'crew_train_completed', 'crew_train_failed', 'crew_test_started', 'crew_test_completed', 'crew_test_failed', 'crew_test_result', 'agent_execution_started', 'agent_execution_completed', 'agent_execution_error', 'lite_agent_execution_started', 'lite_agent_execution_completed', 'lite_agent_execution_error', 'agent_evaluation_started', 'agent_evaluation_completed', 'agent_evaluation_failed', 'flow_created', 'flow_started', 'flow_finished', 'flow_paused', 'method_execution_started', 'method_execution_finished', 'method_execution_failed', 'method_execution_paused', 'human_feedback_requested', 'human_feedback_received', 'flow_input_requested', 'flow_input_received', 'llm_call_started', 'llm_call_completed', 'llm_call_failed', 'llm_stream_chunk', 'llm_thinking_chunk', 'llm_guardrail_started', 'llm_guardrail_completed', 'llm_guardrail_failed', 'tool_usage_started', 'tool_usage_finished', 'tool_usage_error', 'tool_validate_input_error', 'tool_selection_error', 'tool_execution_error', 'memory_save_started', 'memory_save_completed', 'memory_save_failed', 'memory_query_started', 'memory_query_completed', 'memory_query_failed', 'memory_retrieval_started', 'memory_retrieval_completed', 'memory_retrieval_failed', 'knowledge_search_query_started', 'knowledge_search_query_completed', 'knowledge_query_started', 'knowledge_query_completed', 'knowledge_query_failed', 'knowledge_search_query_failed', 'agent_reasoning_started', 'agent_reasoning_completed', 'agent_reasoning_failed', 'mcp_connection_started', 'mcp_connection_completed', 'mcp_connection_failed', 'mcp_tool_execution_started', 'mcp_tool_execution_completed', 'mcp_tool_execution_failed', 'mcp_config_fetch_failed', 'step_observation_started', 'step_observation_completed', 'step_observation_failed', 'plan_refinement', 'plan_replan_triggered', 'goal_achieved_early', 'skill_discovery_started', 'skill_discovery_completed', 'skill_loaded', 'skill_activated', 'skill_load_failed', 'agent_logs_started', 'agent_logs_execution', 'a2a_delegation_started', 'a2a_delegation_completed', 'a2a_conversation_started', 'a2a_conversation_completed', 'a2a_message_sent', 'a2a_response_received', 'a2a_polling_started', 'a2a_polling_status', 'a2a_push_notification_registered', 'a2a_push_notification_received', 'a2a_push_notification_sent', 'a2a_push_notification_timeout', 'a2a_streaming_started', 'a2a_streaming_chunk', 'a2a_agent_card_fetched', 'a2a_authentication_failed', 'a2a_artifact_received', 'a2a_connection_error', 'a2a_server_task_started', 'a2a_server_task_completed', 'a2a_server_task_canceled', 'a2a_server_task_failed', 'a2a_parallel_delegation_started', 'a2a_parallel_delegation_completed', 'a2a_transport_negotiated', 'a2a_content_type_negotiated', 'a2a_context_created', 'a2a_context_expired', 'a2a_context_idle', 'a2a_context_completed', 'a2a_context_pruned', 'SIGTERM', 'SIGINT', 'SIGHUP', 'SIGTSTP', 'SIGCONT', 'cc_env', 'codex_env', 'cursor_env', 'default_env'], typing.Literal['*']]]` | ['task_completed'] | Event types that trigger a checkpoint write. Use ["*"] to checkpoint on every event. |
| `provider` | `crewai.state.provider.json_provider.JsonProvider \| crewai.state.provider.sqlite_provider.SqliteProvider` | factory: JsonProvider | Storage backend. Defaults to JsonProvider. |
| `max_checkpoints` | `int \| None` | None | Maximum checkpoints to keep. Oldest are pruned after each write. None means keep all. |
| `restore_from` | `pathlib.Path \| str \| None` | None | Path or location of a checkpoint to restore from. When passed via a kickoff method's from_checkpoint parameter, the crew or flow resumes from this checkpoint. |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |
| `trigger_all` | *(property)* | — |  |
| `trigger_events` | *(property)* | — |  |

### KnowledgeConfig

**模块：** `crewai.knowledge.knowledge_config`

**说明：** Configuration for knowledge retrieval.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `results_limit` | `<class 'int'>` | 5 | The number of results to return |
| `score_threshold` | `<class 'float'>` | 0.6 | The minimum score for a result to be considered relevant |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |

---

## 五、记忆类

### Memory

**模块：** `crewai.memory.unified_memory`

**说明：** Unified memory: standalone, LLM-analyzed, with intelligent recall flow.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `llm` | `crewai.llms.base_llm.BaseLLM \| str` | 'gpt-4o-mini' | LLM for analysis (model name or BaseLLM instance). |
| `storage` | `crewai.memory.storage.backend.StorageBackend \| str` | 'lancedb' | Storage backend instance or path string. |
| `embedder` | `typing.Any` | None | Embedding callable, provider config dict, or None for default OpenAI. |
| `recency_weight` | `<class 'float'>` | 0.3 | Weight for recency in the composite relevance score. |
| `semantic_weight` | `<class 'float'>` | 0.5 | Weight for semantic similarity in the composite relevance score. |
| `importance_weight` | `<class 'float'>` | 0.2 | Weight for importance in the composite relevance score. |
| `recency_half_life_days` | `<class 'int'>` | 30 | Recency score halves every N days (exponential decay). |
| `consolidation_threshold` | `<class 'float'>` | 0.85 | Similarity above which consolidation is triggered on save. |
| `consolidation_limit` | `<class 'int'>` | 5 | Max existing records to compare during consolidation. |
| `default_importance` | `<class 'float'>` | 0.5 | Default importance when not provided or inferred. |
| `confidence_threshold_high` | `<class 'float'>` | 0.8 | Recall confidence above which results are returned directly. |
| `confidence_threshold_low` | `<class 'float'>` | 0.5 | Recall confidence below which deeper exploration is triggered. |
| `complex_query_threshold` | `<class 'float'>` | 0.7 | For complex queries, explore deeper below this confidence. |
| `exploration_budget` | `<class 'int'>` | 1 | Number of LLM-driven exploration rounds during deep recall. |
| `query_analysis_threshold` | `<class 'int'>` | 200 | Queries shorter than this skip LLM analysis during deep recall. |
| `read_only` | `<class 'bool'>` | False | If True, remember() and remember_many() are silent no-ops. |
| `root_scope` | `str \| None` | None | Structural root scope prefix. When set, LLM-inferred or explicit scopes are nested under this root. For example, a crew with root_scope='/crew/research' will store memories at '/crew/research/<inferred_scope>'. |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `aextract_memories` | `(content: 'str') -> 'list[str]'` | list[str] | Async variant of extract_memories. |
| `arecall` | `(query: 'str', scope: 'str \| None' = None, categories: 'list[str] \| None' = None, limit: 'int' = 10, depth: "Literal['shallow', 'deep']" = 'deep', source: 'str \| None' = None, include_private: 'bool' = False) -> 'list[MemoryMatch]'` | list[MemoryMatch] | Async recall: delegates to sync for now. |
| `aremember` | `(content: 'str', scope: 'str \| None' = None, categories: 'list[str] \| None' = None, metadata: 'dict[str, Any] \| None' = None, importance: 'float \| None' = None, source: 'str \| None' = None, private: 'bool' = False) -> 'MemoryRecord \| None'` | MemoryRecord \| None | Async remember: delegates to sync for now. |
| `aremember_many` | `(contents: 'list[str]', scope: 'str \| None' = None, categories: 'list[str] \| None' = None, metadata: 'dict[str, Any] \| None' = None, importance: 'float \| None' = None, source: 'str \| None' = None, private: 'bool' = False, agent_role: 'str \| None' = None) -> 'list[MemoryRecord]'` | list[MemoryRecord] | Async remember_many: delegates to sync for now. |
| `close` | `() -> 'None'` | None | Drain pending saves, flush storage, and shut down the background thread pool. |
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `drain_writes` | `() -> 'None'` | None | Block until all pending background saves have completed. |
| `extract_memories` | `(content: 'str') -> 'list[str]'` | list[str] | Extract discrete memories from a raw content blob using the LLM. |
| `forget` | `(scope: 'str \| None' = None, categories: 'list[str] \| None' = None, older_than: 'datetime \| None' = None, metadata_filter: 'dict[str, Any] \| None' = None, record_ids: 'list[str] \| None' = None) -> 'int'` | int | Delete memories matching criteria. |
| `info` | `(path: 'str \| None' = None) -> 'ScopeInfo'` | ScopeInfo | Return scope info for path. |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `list_categories` | `(path: 'str \| None' = None) -> 'dict[str, int]'` | dict[str, int] | List categories and counts. |
| `list_records` | `(scope: 'str \| None' = None, limit: 'int' = 200, offset: 'int' = 0) -> 'list[MemoryRecord]'` | list[MemoryRecord] | List records in a scope, newest first. |
| `list_scopes` | `(path: 'str \| None' = None) -> 'list[str]'` | list[str] | List immediate child scopes under path. |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(_Memory__context: 'Any') -> 'None'` | None | Initialize runtime state from field values. |
| `recall` | `(query: 'str', scope: 'str \| None' = None, categories: 'list[str] \| None' = None, limit: 'int' = 10, depth: "Literal['shallow', 'deep']" = 'deep', source: 'str \| None' = None, include_private: 'bool' = False) -> 'list[MemoryMatch]'` | list[MemoryMatch] | Retrieve relevant memories. |
| `remember` | `(content: 'str', scope: 'str \| None' = None, categories: 'list[str] \| None' = None, metadata: 'dict[str, Any] \| None' = None, importance: 'float \| None' = None, source: 'str \| None' = None, private: 'bool' = False, agent_role: 'str \| None' = None, root_scope: 'str \| None' = None) -> 'MemoryRecord \| None'` | MemoryRecord \| None | Store a single item in memory (synchronous). |
| `remember_many` | `(contents: 'list[str]', scope: 'str \| None' = None, categories: 'list[str] \| None' = None, metadata: 'dict[str, Any] \| None' = None, importance: 'float \| None' = None, source: 'str \| None' = None, private: 'bool' = False, agent_role: 'str \| None' = None, root_scope: 'str \| None' = None) -> 'list[MemoryRecord]'` | list[MemoryRecord] | Store multiple items in memory (non-blocking). |
| `reset` | `(scope: 'str \| None' = None) -> 'None'` | None | Reset (delete all) memories in scope. |
| `scope` | `(path: 'str') -> 'Any'` | Any | Return a scoped view of this memory. |
| `slice` | `(scopes: 'list[str]', categories: 'list[str] \| None' = None, read_only: 'bool' = True) -> 'Any'` | Any | Return a multi-scope view (slice) of this memory. |
| `tree` | `(path: 'str \| None' = None, max_depth: 'int' = 3) -> 'str'` | str | Return a formatted tree of scopes (string). |
| `update` | `(record_id: 'str', content: 'str \| None' = None, scope: 'str \| None' = None, categories: 'list[str] \| None' = None, metadata: 'dict[str, Any] \| None' = None, importance: 'float \| None' = None) -> 'MemoryRecord'` | MemoryRecord | Update an existing memory record by ID. |

### MemoryScope

**模块：** `crewai.memory.memory_scope`

**说明：** View of Memory restricted to a root path. All operations are scoped under that path.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `root_path` | `<class 'str'>` | '/' |  |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `extract_memories` | `(content: 'str') -> 'list[str]'` | list[str] | Extract discrete memories from content; delegates to underlying Memory. |
| `forget` | `(scope: 'str \| None' = None, categories: 'list[str] \| None' = None, older_than: 'datetime \| None' = None, metadata_filter: 'dict[str, Any] \| None' = None, record_ids: 'list[str] \| None' = None) -> 'int'` | int | Forget within this scope. |
| `info` | `(path: 'str' = '/') -> 'ScopeInfo'` | ScopeInfo | Info for path under this scope. |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `list_categories` | `(path: 'str \| None' = None) -> 'dict[str, int]'` | dict[str, int] | Categories in this scope; path None means this scope root. |
| `list_scopes` | `(path: 'str' = '/') -> 'list[str]'` | list[str] | List child scopes under path (relative to this scope's root). |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(self: 'BaseModel', context: 'Any', /) -> 'None'` | None | This function is meant to behave like a BaseModel method to initialise private attributes. |
| `read_only` | *(property)* | — | Whether the underlying memory is read-only. |
| `recall` | `(query: 'str', scope: 'str \| None' = None, categories: 'list[str] \| None' = None, limit: 'int' = 10, depth: "Literal['shallow', 'deep']" = 'deep', source: 'str \| None' = None, include_private: 'bool' = False) -> 'list[MemoryMatch]'` | list[MemoryMatch] | Recall within this scope (root path and below). |
| `remember` | `(content: 'str', scope: 'str \| None' = '/', categories: 'list[str] \| None' = None, metadata: 'dict[str, Any] \| None' = None, importance: 'float \| None' = None, source: 'str \| None' = None, private: 'bool' = False) -> 'MemoryRecord \| None'` | MemoryRecord \| None | Remember content; scope is relative to this scope's root. |
| `remember_many` | `(contents: 'list[str]', scope: 'str \| None' = '/', categories: 'list[str] \| None' = None, metadata: 'dict[str, Any] \| None' = None, importance: 'float \| None' = None, source: 'str \| None' = None, private: 'bool' = False, agent_role: 'str \| None' = None) -> 'list[MemoryRecord]'` | list[MemoryRecord] | Remember multiple items; scope is relative to this scope's root. |
| `reset` | `(scope: 'str \| None' = None) -> 'None'` | None | Reset within this scope. |
| `subscope` | `(path: 'str') -> 'MemoryScope'` | MemoryScope | Return a narrower scope under this scope. |
| `tree` | `(path: 'str' = '/', max_depth: 'int' = 3) -> 'str'` | str | Tree under path within this scope. |

### MemorySlice

**模块：** `crewai.memory.memory_scope`

**说明：** View over multiple scopes: recall searches all, remember is a no-op when read_only.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `scopes` | `list[str]` | factory: list |  |
| `categories` | `list[str] \| None` | None |  |
| `read_only` | `<class 'bool'>` | True |  |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `extract_memories` | `(content: 'str') -> 'list[str]'` | list[str] | Extract discrete memories from content; delegates to underlying Memory. |
| `info` | `(path: 'str' = '/') -> 'ScopeInfo'` | ScopeInfo | Aggregate info across slice scopes (record counts summed). |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `list_categories` | `(path: 'str \| None' = None) -> 'dict[str, int]'` | dict[str, int] | Categories and counts across slice scopes. |
| `list_scopes` | `(path: 'str' = '/') -> 'list[str]'` | list[str] | List scopes across all slice roots. |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(self: 'BaseModel', context: 'Any', /) -> 'None'` | None | This function is meant to behave like a BaseModel method to initialise private attributes. |
| `recall` | `(query: 'str', scope: 'str \| None' = None, categories: 'list[str] \| None' = None, limit: 'int' = 10, depth: "Literal['shallow', 'deep']" = 'deep', source: 'str \| None' = None, include_private: 'bool' = False) -> 'list[MemoryMatch]'` | list[MemoryMatch] | Recall across all slice scopes; results merged and re-ranked. |
| `remember` | `(content: 'str', scope: 'str', categories: 'list[str] \| None' = None, metadata: 'dict[str, Any] \| None' = None, importance: 'float \| None' = None, source: 'str \| None' = None, private: 'bool' = False) -> 'MemoryRecord \| None'` | MemoryRecord \| None | Remember into an explicit scope. No-op when read_only=True. |

---

## 六、知识源类

### TextFileKnowledgeSource

**模块：** `crewai.knowledge.source.text_file_knowledge_source`

**说明：** A knowledge source that stores and queries text file content using embeddings.

**父类：** BaseFileKnowledgeSource

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `chunk_size` | `<class 'int'>` | 4000 |  |
| `chunk_overlap` | `<class 'int'>` | 200 |  |
| `chunks` | `list[str]` | factory: list |  |
| `chunk_embeddings` | `list[numpy.ndarray[typing.Any, numpy.dtype[typing.Any]]]` | factory: list |  |
| `storage` | `crewai.knowledge.storage.knowledge_storage.KnowledgeStorage \| None` | None |  |
| `metadata` | `dict[str, typing.Any]` | factory: dict |  |
| `collection_name` | `str \| None` | None |  |
| `file_path` | `pathlib.Path \| list[pathlib.Path] \| str \| list[str] \| None` | None | [Deprecated] The path to the file. Use file_paths instead. |
| `file_paths` | `pathlib.Path \| list[pathlib.Path] \| str \| list[str] \| None` | factory: list | The path to the file |
| `content` | `dict[pathlib.Path, str]` | factory: dict |  |
| `safe_file_paths` | `list[pathlib.Path]` | factory: list |  |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `aadd` | `() -> None` | — | Add text file content asynchronously. |
| `add` | `() -> None` | — | Add text file content to the knowledge source, chunk it, compute embeddings, |
| `convert_to_path` | `(path: pathlib.Path \| str) -> pathlib.Path` | <class 'pathlib.Path'> | Convert a path to a Path object. |
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `get_embeddings` | `() -> list[numpy.ndarray[typing.Any, numpy.dtype[typing.Any]]]` | list[numpy.ndarray[typing.Any, numpy.dtype[typing.Any]]] | Return the list of embeddings for the chunks. |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `load_content` | `() -> dict[pathlib.Path, str]` | dict[pathlib.Path, str] | Load and preprocess text file content. |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(_: Any) -> None` | — | Post-initialization method to load content. |
| `validate_content` | `() -> None` | — | Validate the paths. |

### StringKnowledgeSource

**模块：** `crewai.knowledge.source.string_knowledge_source`

**说明：** A knowledge source that stores and queries plain text content using embeddings.

**父类：** BaseKnowledgeSource

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `chunk_size` | `<class 'int'>` | 4000 |  |
| `chunk_overlap` | `<class 'int'>` | 200 |  |
| `chunks` | `list[str]` | factory: list |  |
| `chunk_embeddings` | `list[numpy.ndarray[typing.Any, numpy.dtype[typing.Any]]]` | factory: list |  |
| `storage` | `crewai.knowledge.storage.knowledge_storage.KnowledgeStorage \| None` | None |  |
| `metadata` | `dict[str, typing.Any]` | factory: dict |  |
| `collection_name` | `str \| None` | None |  |
| `content` | `<class 'str'>` | **必填** |  |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `aadd` | `() -> None` | — | Add string content asynchronously. |
| `add` | `() -> None` | — | Add string content to the knowledge source, chunk it, compute embeddings, and save them. |
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `get_embeddings` | `() -> list[numpy.ndarray[typing.Any, numpy.dtype[typing.Any]]]` | list[numpy.ndarray[typing.Any, numpy.dtype[typing.Any]]] | Return the list of embeddings for the chunks. |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(_: Any) -> None` | — | Post-initialization method to validate content. |
| `validate_content` | `() -> None` | — | Validate string content. |

### BaseKnowledgeSource

**模块：** `crewai.knowledge.source.base_knowledge_source`

**说明：** Abstract base class for knowledge sources.

**父类：** BaseModel, ABC

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `chunk_size` | `<class 'int'>` | 4000 |  |
| `chunk_overlap` | `<class 'int'>` | 200 |  |
| `chunks` | `list[str]` | factory: list |  |
| `chunk_embeddings` | `list[numpy.ndarray[typing.Any, numpy.dtype[typing.Any]]]` | factory: list |  |
| `storage` | `crewai.knowledge.storage.knowledge_storage.KnowledgeStorage \| None` | None |  |
| `metadata` | `dict[str, typing.Any]` | factory: dict |  |
| `collection_name` | `str \| None` | None |  |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `aadd` | `() -> None` | — | Process content, chunk it, compute embeddings, and save them asynchronously. |
| `add` | `() -> None` | — | Process content, chunk it, compute embeddings, and save them. |
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `get_embeddings` | `() -> list[numpy.ndarray[typing.Any, numpy.dtype[typing.Any]]]` | list[numpy.ndarray[typing.Any, numpy.dtype[typing.Any]]] | Return the list of embeddings for the chunks. |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |
| `validate_content` | `() -> Any` | typing.Any | Load and preprocess content from the source. |

### Knowledge

**模块：** `crewai.knowledge.knowledge`

**说明：** Knowledge is a collection of sources and setup for the vector store to save and query relevant context. Args:     sources: list[BaseKnowledgeSource] = Field(default_factory=list)     storage: KnowledgeStorage \| None = Field(default=None)     embedder: EmbedderConfig \| None = None

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `sources` | `list[crewai.knowledge.source.base_knowledge_source.BaseKnowledgeSource]` | factory: list |  |
| `storage` | `crewai.knowledge.storage.knowledge_storage.KnowledgeStorage \| None` | None |  |
| `embedder` | `crewai.rag.embeddings.providers.microsoft.types.AzureProviderSpec \| crewai.rag.embeddings.providers.aws.types.BedrockProviderSpec \| crewai.rag.embeddings.providers.cohere.types.CohereProviderSpec \| crewai.rag.embeddings.providers.custom.types.CustomProviderSpec \| crewai.rag.embeddings.providers.google.types.GenerativeAiProviderSpec \| crewai.rag.embeddings.providers.huggingface.types.HuggingFaceProviderSpec \| crewai.rag.embeddings.providers.instructor.types.InstructorProviderSpec \| crewai.rag.embeddings.providers.jina.types.JinaProviderSpec \| crewai.rag.embeddings.providers.ollama.types.OllamaProviderSpec \| crewai.rag.embeddings.providers.onnx.types.ONNXProviderSpec \| crewai.rag.embeddings.providers.openai.types.OpenAIProviderSpec \| crewai.rag.embeddings.providers.openclip.types.OpenCLIPProviderSpec \| crewai.rag.embeddings.providers.roboflow.types.RoboflowProviderSpec \| crewai.rag.embeddings.providers.sentence_transformer.types.SentenceTransformerProviderSpec \| crewai.rag.embeddings.providers.text2vec.types.Text2VecProviderSpec \| crewai.rag.embeddings.providers.google.types.VertexAIProviderSpec \| crewai.rag.embeddings.providers.voyageai.types.VoyageAIProviderSpec \| crewai.rag.embeddings.providers.ibm.types.WatsonXProviderSpec \| crewai.rag.core.base_embeddings_provider.BaseEmbeddingsProvider[Any] \| type[crewai.rag.core.base_embeddings_provider.BaseEmbeddingsProvider[Any]] \| None` | None |  |
| `collection_name` | `str \| None` | None |  |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `aadd_sources` | `() -> None` | — | Add all knowledge sources to storage asynchronously. |
| `add_sources` | `() -> None` | — |  |
| `aquery` | `(query: list[str], results_limit: int = 5, score_threshold: float = 0.6) -> list[crewai.rag.types.SearchResult]` | list[crewai.rag.types.SearchResult] | Query across all knowledge sources asynchronously. |
| `areset` | `() -> None` | — | Reset the knowledge base asynchronously. |
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |
| `query` | `(query: list[str], results_limit: int = 5, score_threshold: float = 0.6) -> list[crewai.rag.types.SearchResult]` | list[crewai.rag.types.SearchResult] | Query across all knowledge sources to find the most relevant information. |
| `reset` | `() -> None` | — |  |

---

## 七、技能类

### Skill

**模块：** `crewai.skills.models`

**说明：** A loaded Agent Skill with progressive disclosure support.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `frontmatter` | `<class 'crewai.skills.models.SkillFrontmatter'>` | **必填** | Parsed YAML frontmatter from SKILL.md. |
| `instructions` | `str \| None` | None | Full SKILL.md body text, populated at INSTRUCTIONS level. |
| `path` | `<class 'pathlib.Path'>` | **必填** | Filesystem path to the skill directory. |
| `disclosure_level` | `typing.Literal[1, 2, 3]` | 1 | Current progressive disclosure level of the skill. |
| `resource_files` | `dict[typing.Literal['scripts', 'references', 'assets'], list[str]] \| None` | None | Cataloged resource files by directory, populated at RESOURCES level. |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `assets_dir` | *(property)* | — | Path to the assets directory. |
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `description` | *(property)* | — | Skill description from frontmatter. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |
| `name` | *(property)* | — | Skill name from frontmatter. |
| `references_dir` | *(property)* | — | Path to the references directory. |
| `scripts_dir` | *(property)* | — | Path to the scripts directory. |
| `with_disclosure_level` | `(level: 'DisclosureLevel', instructions: 'str \| None' = None, resource_files: 'dict[ResourceDirName, list[str]] \| None' = None) -> 'Skill'` | Skill | Create a new Skill at a different disclosure level. |

### SkillFrontmatter

**模块：** `crewai.skills.models`

**说明：** YAML frontmatter from a SKILL.md file.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `name` | `<class 'str'>` | **必填** |  |
| `description` | `<class 'str'>` | **必填** |  |
| `license` | `str \| None` | None | SPDX license identifier or free-text license reference, e.g. 'MIT', 'Apache-2.0'. |
| `compatibility` | `str \| None` | None | Version or platform constraints for the skill, e.g. 'crewai >= 0.80'. |
| `metadata` | `dict[str, str] \| None` | None | Arbitrary string key-value pairs for custom skill metadata. |
| `allowed_tools` | `list[str] \| None` | None | Pre-approved tool names the skill may use, parsed from a space-delimited string in frontmatter. |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |

---

## 八、MCP 配置类

### MCPServerStdio

**模块：** `crewai.mcp.config`

**说明：** Stdio MCP server configuration.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `command` | `<class 'str'>` | **必填** | Command to execute (e.g., 'python', 'node', 'npx', 'uvx'). |
| `args` | `list[str]` | factory: list | Command arguments (e.g., ['server.py'] or ['-y', '@mcp/server']). |
| `env` | `dict[str, str] \| None` | None | Environment variables to pass to the process. |
| `tool_filter` | `collections.abc.Callable[[crewai.mcp.filters.ToolFilterContext, dict[str, typing.Any]], bool] \| collections.abc.Callable[[dict[str, typing.Any]], bool] \| None` | None | Optional tool filter for filtering available tools. |
| `cache_tools_list` | `<class 'bool'>` | False | Whether to cache the tool list for faster subsequent access. |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |

### MCPServerHTTP

**模块：** `crewai.mcp.config`

**说明：** HTTP/Streamable HTTP MCP server configuration.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `url` | `<class 'str'>` | **必填** | Server URL (e.g., 'https://api.example.com/mcp'). |
| `headers` | `dict[str, str] \| None` | None | Optional HTTP headers for authentication or other purposes. |
| `streamable` | `<class 'bool'>` | True | Whether to use streamable HTTP transport (default: True). |
| `tool_filter` | `collections.abc.Callable[[crewai.mcp.filters.ToolFilterContext, dict[str, typing.Any]], bool] \| collections.abc.Callable[[dict[str, typing.Any]], bool] \| None` | None | Optional tool filter for filtering available tools. |
| `cache_tools_list` | `<class 'bool'>` | False | Whether to cache the tool list for faster subsequent access. |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |

### MCPServerSSE

**模块：** `crewai.mcp.config`

**说明：** Server-Sent Events (SSE) MCP server configuration.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `url` | `<class 'str'>` | **必填** | Server URL (e.g., 'https://api.example.com/mcp/sse'). |
| `headers` | `dict[str, str] \| None` | None | Optional HTTP headers for authentication or other purposes. |
| `tool_filter` | `collections.abc.Callable[[crewai.mcp.filters.ToolFilterContext, dict[str, typing.Any]], bool] \| collections.abc.Callable[[dict[str, typing.Any]], bool] \| None` | None | Optional tool filter for filtering available tools. |
| `cache_tools_list` | `<class 'bool'>` | False | Whether to cache the tool list for faster subsequent access. |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |

---

## 九、A2A 配置类

### A2AConfig

**模块：** `crewai.a2a.config`

**说明：** Configuration for A2A protocol integration.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `endpoint` | `<class 'str'>` | **必填** | A2A agent endpoint URL |
| `auth` | `crewai.a2a.auth.client_schemes.ClientAuthScheme \| None` | None | Authentication scheme |
| `timeout` | `<class 'int'>` | 120 | Request timeout in seconds |
| `max_turns` | `<class 'int'>` | 10 | Maximum conversation turns with A2A agent |
| `response_model` | `type[pydantic.main.BaseModel] \| None` | None | Optional Pydantic model for structured A2A agent responses |
| `fail_fast` | `<class 'bool'>` | True | If True, raise error when agent unreachable; if False, skip |
| `trust_remote_completion_status` | `<class 'bool'>` | False | If True, return A2A result directly when completed |
| `updates` | `typing.Any` | factory: _get_default_update_config | Update mechanism config |
| `client_extensions` | `list[typing.Annotated[typing.Any, BeforeValidator(func=<function _validate_a2a_extension at 0x7f91e5ac9580>, json_schema_input_type=PydanticUndefined)]]` | factory: list | Client-side processing hooks for tool injection and prompt augmentation |
| `transport` | `<class 'crewai.a2a.config.ClientTransportConfig'>` | factory: ClientTransportConfig | Transport configuration (preferred, supported transports, gRPC settings) |
| `transport_protocol` | `typing.Optional[typing.Literal['JSONRPC', 'GRPC', 'HTTP+JSON']]` | None | Deprecated: Use transport.preferred instead |
| `supported_transports` | `list[typing.Literal['JSONRPC', 'GRPC', 'HTTP+JSON']] \| None` | None | Deprecated: Use transport.supported instead |
| `use_client_preference` | `bool \| None` | None | Deprecated: Set transport.preferred to enable client preference |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(self: 'BaseModel', context: 'Any', /) -> 'None'` | None | This function is meant to behave like a BaseModel method to initialise private attributes. |

### A2AServerConfig

**模块：** `crewai.a2a.config`

**说明：** Configuration for exposing a Crew or Agent as an A2A server.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `name` | `str \| None` | None | Human-readable name for the agent. Auto-derived from Crew/Agent if not provided. |
| `description` | `str \| None` | None | Human-readable description of the agent. Auto-derived from Crew/Agent if not provided. |
| `version` | `<class 'str'>` | '1.0.0' | Version string for the agent card |
| `skills` | `list[typing.Any]` | factory: list | List of agent skills. Auto-derived from tasks/tools if not provided. |
| `default_input_modes` | `list[str]` | factory: <lambda> | Default supported input MIME types |
| `default_output_modes` | `list[str]` | factory: <lambda> | Default supported output MIME types |
| `capabilities` | `typing.Any` | factory: <lambda> | Declaration of optional capabilities supported by the agent |
| `protocol_version` | `typing.Literal['0.2.0', '0.2.1', '0.2.2', '0.2.3', '0.2.4', '0.2.5', '0.2.6', '0.3.0', '0.4.0']` | '0.3.0' | A2A protocol version this agent supports |
| `provider` | `typing.Any \| None` | None | Information about the agent's service provider |
| `documentation_url` | `typing.Optional[typing.Annotated[str, BeforeValidator(func=<function <lambda> at 0x7f91e59a0e00>, json_schema_input_type=PydanticUndefined)]]` | None | URL to the agent's documentation |
| `icon_url` | `typing.Optional[typing.Annotated[str, BeforeValidator(func=<function <lambda> at 0x7f91e59a0e00>, json_schema_input_type=PydanticUndefined)]]` | None | URL to an icon for the agent |
| `additional_interfaces` | `list[typing.Any]` | factory: list | Additional supported interfaces. |
| `security` | `list[dict[str, list[str]]]` | factory: list | Security requirement objects for all agent interactions |
| `security_schemes` | `dict[str, typing.Any]` | factory: dict | Security schemes available to authorize requests |
| `supports_authenticated_extended_card` | `<class 'bool'>` | False | Whether agent provides extended card to authenticated users |
| `extended_skills` | `list[typing.Any]` | factory: list | Additional skills visible only to authenticated users in the extended card |
| `url` | `typing.Optional[typing.Annotated[str, BeforeValidator(func=<function <lambda> at 0x7f91e59a0e00>, json_schema_input_type=PydanticUndefined)]]` | None | Preferred endpoint URL for the agent. Set at runtime if not provided. |
| `signing_config` | `crewai.a2a.config.AgentCardSigningConfig \| None` | None | Configuration for signing the AgentCard with JWS |
| `signatures` | `list[typing.Any] \| None` | None | Deprecated: Use signing_config instead. Pre-computed JWS signatures for the AgentCard. |
| `server_extensions` | `list[typing.Any]` | factory: list | Server-side A2A protocol extensions that modify agent behavior |
| `push_notifications` | `crewai.a2a.config.ServerPushNotificationConfig \| None` | None | Configuration for outgoing push notifications |
| `transport` | `<class 'crewai.a2a.config.ServerTransportConfig'>` | factory: ServerTransportConfig | Transport configuration (preferred transport, gRPC, REST settings) |
| `preferred_transport` | `typing.Optional[typing.Literal['JSONRPC', 'GRPC', 'HTTP+JSON']]` | None | Deprecated: Use transport.preferred instead |
| `auth` | `crewai.a2a.auth.server_schemes.ServerAuthScheme \| None` | None | Authentication scheme for A2A endpoints. Defaults to SimpleTokenAuth using AUTH_TOKEN env var. |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |

### A2AClientConfig

**模块：** `crewai.a2a.config`

**说明：** Configuration for connecting to remote A2A agents.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `endpoint` | `<class 'str'>` | **必填** | A2A agent endpoint URL |
| `auth` | `crewai.a2a.auth.client_schemes.ClientAuthScheme \| None` | None | Authentication scheme |
| `timeout` | `<class 'int'>` | 120 | Request timeout in seconds |
| `max_turns` | `<class 'int'>` | 10 | Maximum conversation turns with A2A agent |
| `response_model` | `type[pydantic.main.BaseModel] \| None` | None | Optional Pydantic model for structured A2A agent responses |
| `fail_fast` | `<class 'bool'>` | True | If True, raise error when agent unreachable; if False, skip |
| `trust_remote_completion_status` | `<class 'bool'>` | False | If True, return A2A result directly when completed |
| `updates` | `typing.Any` | factory: _get_default_update_config | Update mechanism config |
| `accepted_output_modes` | `list[str]` | factory: <lambda> | Media types the client can accept in responses |
| `extensions` | `list[str]` | factory: list | Extension URIs the client supports |
| `client_extensions` | `list[typing.Annotated[typing.Any, BeforeValidator(func=<function _validate_a2a_extension at 0x7f91e5ac9580>, json_schema_input_type=PydanticUndefined)]]` | factory: list | Client-side processing hooks for tool injection and prompt augmentation |
| `transport` | `<class 'crewai.a2a.config.ClientTransportConfig'>` | factory: ClientTransportConfig | Transport configuration (preferred, supported transports, gRPC settings) |
| `transport_protocol` | `typing.Optional[typing.Literal['JSONRPC', 'GRPC', 'HTTP+JSON']]` | None | Deprecated: Use transport.preferred instead |
| `supported_transports` | `list[typing.Literal['JSONRPC', 'GRPC', 'HTTP+JSON']] \| None` | None | Deprecated: Use transport.supported instead |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(self: 'BaseModel', context: 'Any', /) -> 'None'` | None | This function is meant to behave like a BaseModel method to initialise private attributes. |

---

## 十、输出类

### CrewOutput

**模块：** `crewai.crews.crew_output`

**说明：** Class that represents the result of a crew.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `raw` | `<class 'str'>` | '' | Raw output of crew |
| `pydantic` | `pydantic.main.BaseModel \| None` | None | Pydantic output of Crew |
| `json_dict` | `dict[str, typing.Any] \| None` | None | JSON dict output of Crew |
| `tasks_output` | `list[crewai.tasks.task_output.TaskOutput]` | factory: list | Output of each task |
| `token_usage` | `<class 'crewai.types.usage_metrics.UsageMetrics'>` | factory: UsageMetrics | Processed token summary |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | *(property)* | — |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |
| `to_dict` | `() -> 'dict[str, Any]'` | dict[str, Any] | Convert json_output and pydantic_output to a dictionary. |

### TaskOutput

**模块：** `crewai.tasks.task_output`

**说明：** Class that represents the result of a task.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `description` | `<class 'str'>` | **必填** | Description of the task |
| `name` | `str \| None` | None | Name of the task |
| `expected_output` | `str \| None` | None | Expected output of the task |
| `summary` | `str \| None` | None | Summary of the task |
| `raw` | `<class 'str'>` | '' | Raw output of the task |
| `pydantic` | `pydantic.main.BaseModel \| None` | None | Pydantic output of task |
| `json_dict` | `dict[str, typing.Any] \| None` | None | JSON dictionary of task |
| `agent` | `<class 'str'>` | **必填** | Agent that executed the task |
| `output_format` | `<enum 'OutputFormat'>` | <OutputFormat.RAW: 'raw'> | Output format of the task |
| `messages` | `list[crewai.utilities.types.LLMMessage]` | factory: list | Messages of the task |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | *(property)* | — | Get the JSON string representation of the task output. |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |
| `set_summary` | `() -> 'TaskOutput'` | TaskOutput | Set the summary field based on the description. |
| `to_dict` | `() -> 'dict[str, Any]'` | dict[str, Any] | Convert json_output and pydantic_output to a dictionary. |

### LiteAgentOutput

**模块：** `crewai.lite_agent_output`

**说明：** Class that represents the result of a LiteAgent execution.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `raw` | `<class 'str'>` | '' | Raw output of the agent |
| `pydantic` | `pydantic.main.BaseModel \| None` | None | Pydantic output of the agent |
| `agent_role` | `<class 'str'>` | **必填** | Role of the agent that produced this output |
| `usage_metrics` | `dict[str, typing.Any] \| None` | None | Token usage metrics for this execution |
| `messages` | `list[crewai.utilities.types.LLMMessage]` | factory: list | Messages of the agent |
| `plan` | `str \| None` | None | The execution plan that was generated, if any |
| `todos` | `list[crewai.lite_agent_output.TodoExecutionResult]` | factory: list | List of todos that were executed with their results |
| `replan_count` | `<class 'int'>` | 0 | Number of times the plan was regenerated |
| `last_replan_reason` | `str \| None` | None | Reason for the last replan, if any |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `completed_todos` | *(property)* | — | Get only the completed todos. |
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `failed_todos` | *(property)* | — | Get only the failed todos. |
| `had_plan` | *(property)* | — | Check if the agent executed with a plan. |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |
| `to_dict` | `() -> 'dict[str, Any]'` | dict[str, Any] | Convert pydantic_output to a dictionary. |

---

## 十一、上下文与状态类

### ExecutionContext

**模块：** `crewai.context`

**说明：** Snapshot of ContextVar execution state.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `current_task_id` | `str \| None` | None |  |
| `flow_request_id` | `str \| None` | None |  |
| `flow_id` | `str \| None` | None |  |
| `flow_method_name` | `<class 'str'>` | 'unknown' |  |
| `event_id_stack` | `tuple[tuple[str, str], ...]` | factory: tuple |  |
| `last_event_id` | `str \| None` | None |  |
| `triggering_event_id` | `str \| None` | None |  |
| `emission_sequence` | `<class 'int'>` | 0 |  |
| `feedback_callback_info` | `dict[str, typing.Any] \| None` | None |  |
| `platform_token` | `str \| None` | None |  |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |

### RuntimeState

**模块：** `crewai.state.runtime`

**说明：** !!! abstract "Usage Documentation"     [`RootModel` and Custom Root Types](../concepts/models.md#rootmodel-and-custom-root-types)

**父类：** RootModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `root` | `list[typing.Annotated[crewai.flow.flow.Flow \| crewai.crew.Crew \| crewai.agent.core.Agent, FieldInfo(annotation=NoneType, required=True, discriminator='entity_type')]]` | **必填** |  |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `acheckpoint` | `(location: 'str') -> 'str'` | str | Async version of :meth:`checkpoint`. |
| `checkpoint` | `(location: 'str') -> 'str'` | str | Write a checkpoint. |
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `event_record` | *(property)* | — | The execution event record. |
| `fork` | `(branch: 'str \| None' = None) -> 'None'` | None | Create a new execution branch and write an initial checkpoint. |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(self: 'BaseModel', context: 'Any', /) -> 'None'` | None | This function is meant to behave like a BaseModel method to initialise private attributes. |

---

## 十二、枚举

### Process

**模块：** `crewai.process`

**成员：** `sequential`、`hierarchical`

### OutputFormat

**模块：** `crewai.tasks.task_output`

**成员：** `JSON`、`PYDANTIC`、`RAW`

---

## 十三、Flow 装饰器

### start()

**模块：** `crewai.flow.flow`

**签名：** `(condition: 'str \| FlowCondition \| Callable[..., Any] \| None' = None) -> 'Callable[[Callable[P, R]], StartMethod[P, R]]'`

**说明：** Marks a method as a flow's starting point.

### listen()

**模块：** `crewai.flow.flow`

**签名：** `(condition: 'str \| FlowCondition \| Callable[..., Any]') -> 'Callable[[Callable[P, R]], ListenMethod[P, R]]'`

**说明：** Creates a listener that executes when specified conditions are met.

### router()

**模块：** `crewai.flow.flow`

**签名：** `(condition: 'str \| FlowCondition \| Callable[..., Any]') -> 'Callable[[Callable[P, R]], RouterMethod[P, R]]'`

**说明：** Creates a routing method that directs flow execution based on conditions.

### and_()

**模块：** `crewai.flow.flow`

**签名：** `(*conditions: 'str \| FlowCondition \| Callable[..., Any]') -> 'FlowCondition'`

**说明：** Combines multiple conditions with AND logic for flow control.

### or_()

**模块：** `crewai.flow.flow`

**签名：** `(*conditions: 'str \| FlowCondition \| Callable[..., Any]') -> 'FlowCondition'`

**说明：** Combines multiple conditions with OR logic for flow control.

---

## 十四、其他工具类

### Converter

**模块：** `crewai.utilities.converter`

**说明：** Class that converts text into either pydantic or json.

**父类：** OutputConverter

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `text` | `<class 'str'>` | **必填** | Text to be converted. |
| `llm` | `typing.Any` | **必填** | The language model to be used to convert the text. |
| `model` | `type[pydantic.main.BaseModel]` | **必填** | The model to be used to convert the text. |
| `instructions` | `<class 'str'>` | **必填** | Conversion instructions to the LLM. |
| `max_attempts` | `<class 'int'>` | 3 | Max number of attempts to try to get the output formatted. |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |
| `to_json` | `(current_attempt: 'int' = 1) -> 'str \| ConverterError \| Any'` | str \| ConverterError \| Any | Convert text to json. |
| `to_pydantic` | `(current_attempt: 'int' = 1) -> 'BaseModel'` | BaseModel | Convert text to pydantic. |

### UsageMetrics

**模块：** `crewai.types.usage_metrics`

**说明：** Track usage metrics for crew execution.

**父类：** BaseModel

**字段：**

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `total_tokens` | `<class 'int'>` | 0 | Total number of tokens used. |
| `prompt_tokens` | `<class 'int'>` | 0 | Number of tokens used in prompts. |
| `cached_prompt_tokens` | `<class 'int'>` | 0 | Number of cached prompt tokens used. |
| `completion_tokens` | `<class 'int'>` | 0 | Number of tokens used in completions. |
| `reasoning_tokens` | `<class 'int'>` | 0 | Number of reasoning/thinking tokens (e.g. OpenAI o-series, Gemini thinking). |
| `cache_creation_tokens` | `<class 'int'>` | 0 | Number of cache creation tokens (e.g. Anthropic cache writes). |
| `successful_requests` | `<class 'int'>` | 0 | Number of successful requests made. |

**方法：**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `add_usage_metrics` | `(usage_metrics: Self) -> None` | — | Add usage metrics from another UsageMetrics object. |
| `copy` | `(*, include: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, exclude: 'AbstractSetIntStr \| MappingIntStrAny \| None' = None, update: 'Dict[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | Returns a copy of the model. |
| `dict` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'` | Dict[str, Any] |  |
| `json` | `(*, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] \| None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'` | str |  |
| `model_copy` | `(*, update: 'Mapping[str, Any] \| None' = None, deep: 'bool' = False) -> 'Self'` | Self | !!! abstract "Usage Documentation" |
| `model_dump` | `(*, mode: "Literal['json', 'python'] \| str" = 'python', include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'` | dict[str, Any] | !!! abstract "Usage Documentation" |
| `model_dump_json` | `(*, indent: 'int \| None' = None, ensure_ascii: 'bool' = False, include: 'IncEx \| None' = None, exclude: 'IncEx \| None' = None, context: 'Any \| None' = None, by_alias: 'bool \| None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool \| Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] \| None' = None, serialize_as_any: 'bool' = False) -> 'str'` | str | !!! abstract "Usage Documentation" |
| `model_extra` | *(property)* | — | Get extra fields set during validation. |
| `model_fields_set` | *(property)* | — | Returns the set of fields that have been explicitly set on this model instance. |
| `model_post_init` | `(context: 'Any', /) -> 'None'` | None | Override this method to perform additional initialization after `__init__` and `model_construct`. |

---

## 十五、crewai_tools 预置工具

共发现 **124** 个工具类。

| 工具类 | 模块 | 说明 |
|---|---|---|
| `AIMindTool` | `crewai_tools.tools.ai_mind_tool.ai_mind_tool` | !!! abstract "Usage Documentation" |
| `ApifyActorsTool` | `crewai_tools.tools.apify_actors_tool.apify_actors_tool` | !!! abstract "Usage Documentation" |
| `ArxivPaperTool` | `crewai_tools.tools.arxiv_paper_tool.arxiv_paper_tool` | !!! abstract "Usage Documentation" |
| `BedrockInvokeAgentTool` | `crewai_tools.aws.bedrock.agents.invoke_agent_tool` | !!! abstract "Usage Documentation" |
| `BedrockKBRetrieverTool` | `crewai_tools.aws.bedrock.knowledge_base.retriever_tool` | !!! abstract "Usage Documentation" |
| `BraveImageSearchTool` | `crewai_tools.tools.brave_search_tool.brave_image_tool` | A tool that performs image searches using the Brave Search API. |
| `BraveLLMContextTool` | `crewai_tools.tools.brave_search_tool.brave_llm_context_tool` | A tool that retrieves context for LLM usage from the Brave Search API. |
| `BraveLocalPOIsDescriptionTool` | `crewai_tools.tools.brave_search_tool.brave_local_pois_tool` | A tool that retrieves AI-generated descriptions for local POIs using the Brave Search API. |
| `BraveLocalPOIsTool` | `crewai_tools.tools.brave_search_tool.brave_local_pois_tool` | A tool that retrieves local POIs using the Brave Search API. |
| `BraveNewsSearchTool` | `crewai_tools.tools.brave_search_tool.brave_news_tool` | A tool that performs news searches using the Brave Search API. |
| `BraveSearchTool` | `crewai_tools.tools.brave_search_tool.brave_search_tool` | A tool that performs web searches using the Brave Search API. |
| `BraveSearchToolBase` | `crewai_tools.tools.brave_search_tool.base` | Base class for Brave Search API interactions. |
| `BraveVideoSearchTool` | `crewai_tools.tools.brave_search_tool.brave_video_tool` | A tool that performs video searches using the Brave Search API. |
| `BraveWebSearchTool` | `crewai_tools.tools.brave_search_tool.brave_web_tool` | A tool that performs web searches using the Brave Search API. |
| `BrightDataDatasetTool` | `crewai_tools.tools.brightdata_tool.brightdata_dataset` | CrewAI-compatible tool for scraping structured data using Bright Data Datasets. |
| `BrightDataSearchTool` | `crewai_tools.tools.brightdata_tool.brightdata_serp` | A web search tool that utilizes Bright Data's SERP API to perform queries and return either structured results |
| `BrightDataWebUnlockerTool` | `crewai_tools.tools.brightdata_tool.brightdata_unlocker` | A tool for performing web scraping using the Bright Data Web Unlocker API. |
| `BrowserBaseTool` | `crewai_tools.aws.bedrock.browser.browser_toolkit` | Base class for browser tools. |
| `BrowserbaseLoadTool` | `crewai_tools.tools.browserbase_load_tool.browserbase_load_tool` | !!! abstract "Usage Documentation" |
| `CSVSearchTool` | `crewai_tools.tools.csv_search_tool.csv_search_tool` | !!! abstract "Usage Documentation" |
| `ClickTool` | `crewai_tools.aws.bedrock.browser.browser_toolkit` | Tool for clicking on an element with the given CSS selector. |
| `CodeDocsSearchTool` | `crewai_tools.tools.code_docs_search_tool.code_docs_search_tool` | !!! abstract "Usage Documentation" |
| `ComposioTool` | `crewai_tools.tools.composio_tool.composio_tool` | Wrapper for composio tools. |
| `ContextualAICreateAgentTool` | `crewai_tools.tools.contextualai_create_agent_tool.contextual_create_agent_tool` | Tool to create Contextual AI RAG agents with documents. |
| `ContextualAIParseTool` | `crewai_tools.tools.contextualai_parse_tool.contextual_parse_tool` | Tool to parse documents using Contextual AI's parser. |
| `ContextualAIQueryTool` | `crewai_tools.tools.contextualai_query_tool.contextual_query_tool` | Tool to query Contextual AI RAG agents. |
| `ContextualAIRerankTool` | `crewai_tools.tools.contextualai_rerank_tool.contextual_rerank_tool` | Tool to rerank documents using Contextual AI's instruction-following reranker. |
| `CouchbaseFTSVectorSearchTool` | `crewai_tools.tools.couchbase_tool.couchbase_tool` | Tool to search the Couchbase database. |
| `CrewAIPlatformActionTool` | `crewai_tools.tools.crewai_platform_tools.crewai_platform_action_tool` | !!! abstract "Usage Documentation" |
| `CurrentWebPageTool` | `crewai_tools.aws.bedrock.browser.browser_toolkit` | Tool for getting information about the current webpage. |
| `DOCXSearchTool` | `crewai_tools.tools.docx_search_tool.docx_search_tool` | !!! abstract "Usage Documentation" |
| `DallETool` | `crewai_tools.tools.dalle_tool.dalle_tool` | !!! abstract "Usage Documentation" |
| `DatabricksQueryTool` | `crewai_tools.tools.databricks_query_tool.databricks_query_tool` | A tool for querying Databricks workspace tables using SQL. |
| `DaytonaBaseTool` | `crewai_tools.tools.daytona_sandbox_tool.daytona_base_tool` | Shared base for tools that act on a Daytona sandbox. |
| `DaytonaExecTool` | `crewai_tools.tools.daytona_sandbox_tool.daytona_exec_tool` | Run a shell command inside a Daytona sandbox. |
| `DaytonaFileTool` | `crewai_tools.tools.daytona_sandbox_tool.daytona_file_tool` | Read, write, and manage files inside a Daytona sandbox. |
| `DaytonaPythonTool` | `crewai_tools.tools.daytona_sandbox_tool.daytona_python_tool` | Run Python source inside a Daytona sandbox. |
| `DeleteFilesTool` | `crewai_tools.aws.bedrock.code_interpreter.code_interpreter_toolkit` | Tool for removing files from the environment. |
| `DirectoryReadTool` | `crewai_tools.tools.directory_read_tool.directory_read_tool` | !!! abstract "Usage Documentation" |
| `DirectorySearchTool` | `crewai_tools.tools.directory_search_tool.directory_search_tool` | !!! abstract "Usage Documentation" |
| `E2BBaseTool` | `crewai_tools.tools.e2b_sandbox_tool.e2b_base_tool` | Shared base for tools that act on an E2B sandbox. |
| `E2BExecTool` | `crewai_tools.tools.e2b_sandbox_tool.e2b_exec_tool` | Run a shell command inside an E2B sandbox. |
| `E2BFileTool` | `crewai_tools.tools.e2b_sandbox_tool.e2b_file_tool` | Read, write, and manage files inside an E2B sandbox. |
| `E2BPythonTool` | `crewai_tools.tools.e2b_sandbox_tool.e2b_python_tool` | Run Python code inside an E2B code interpreter sandbox. |
| `EXASearchTool` | `crewai_tools.tools.exa_tools.exa_search_tool` | !!! abstract "Usage Documentation" |
| `EnterpriseActionTool` | `crewai_tools.adapters.enterprise_adapter` | A tool that executes a specific enterprise action. |
| `ExecuteCodeTool` | `crewai_tools.aws.bedrock.code_interpreter.code_interpreter_toolkit` | Tool for executing code in various languages. |
| `ExecuteCommandTool` | `crewai_tools.aws.bedrock.code_interpreter.code_interpreter_toolkit` | Tool for running shell commands in the code interpreter environment. |
| `ExtractHyperlinksTool` | `crewai_tools.aws.bedrock.browser.browser_toolkit` | Tool for extracting hyperlinks from a webpage. |
| `ExtractTextTool` | `crewai_tools.aws.bedrock.browser.browser_toolkit` | Tool for extracting text from a webpage. |
| `FileCompressorTool` | `crewai_tools.tools.files_compressor_tool.files_compressor_tool` | !!! abstract "Usage Documentation" |
| `FileReadTool` | `crewai_tools.tools.file_read_tool.file_read_tool` | A tool for reading file contents. |
| `FileWriterTool` | `crewai_tools.tools.file_writer_tool.file_writer_tool` | !!! abstract "Usage Documentation" |
| `FirecrawlCrawlWebsiteTool` | `crewai_tools.tools.firecrawl_crawl_website_tool.firecrawl_crawl_website_tool` | Tool for crawling websites using Firecrawl v2 API. To run this tool, you need to have a Firecrawl API key. |
| `FirecrawlScrapeWebsiteTool` | `crewai_tools.tools.firecrawl_scrape_website_tool.firecrawl_scrape_website_tool` | Tool for scraping webpages using Firecrawl v2 API. To run this tool, you need to have a Firecrawl API key. |
| `FirecrawlSearchTool` | `crewai_tools.tools.firecrawl_search_tool.firecrawl_search_tool` | Tool for searching webpages using Firecrawl v2 API. To run this tool, you need to have a Firecrawl API key. |
| `GenerateCrewaiAutomationTool` | `crewai_tools.tools.generate_crewai_automation_tool.generate_crewai_automation_tool` | !!! abstract "Usage Documentation" |
| `GetElementsTool` | `crewai_tools.aws.bedrock.browser.browser_toolkit` | Tool for getting elements from a webpage. |
| `GetTaskTool` | `crewai_tools.aws.bedrock.code_interpreter.code_interpreter_toolkit` | Tool for checking status of async tasks. |
| `GithubSearchTool` | `crewai_tools.tools.github_search_tool.github_search_tool` | !!! abstract "Usage Documentation" |
| `HyperbrowserLoadTool` | `crewai_tools.tools.hyperbrowser_load_tool.hyperbrowser_load_tool` | HyperbrowserLoadTool. |
| `InvokeCrewAIAutomationTool` | `crewai_tools.tools.invoke_crewai_automation_tool.invoke_crewai_automation_tool` | A CrewAI tool for invoking external crew/flows APIs. |
| `JSONSearchTool` | `crewai_tools.tools.json_search_tool.json_search_tool` | !!! abstract "Usage Documentation" |
| `JinaScrapeWebsiteTool` | `crewai_tools.tools.jina_scrape_website_tool.jina_scrape_website_tool` | !!! abstract "Usage Documentation" |
| `LinkupSearchTool` | `crewai_tools.tools.linkup.linkup_search_tool` | !!! abstract "Usage Documentation" |
| `ListFilesTool` | `crewai_tools.aws.bedrock.code_interpreter.code_interpreter_toolkit` | Tool for listing files in directories in the environment. |
| `LlamaIndexTool` | `crewai_tools.tools.llamaindex_tool.llamaindex_tool` | Tool to wrap LlamaIndex tools/query engines. |
| `MDXSearchTool` | `crewai_tools.tools.mdx_search_tool.mdx_search_tool` | !!! abstract "Usage Documentation" |
| `MergeAgentHandlerTool` | `crewai_tools.tools.merge_agent_handler_tool.merge_agent_handler_tool` | Wrapper for Merge Agent Handler tools. |
| `MongoDBVectorSearchTool` | `crewai_tools.tools.mongodb_vector_search_tool.vector_search` | Tool to perfrom a vector search the MongoDB database. |
| `MultiOnTool` | `crewai_tools.tools.multion_tool.multion_tool` | Tool to wrap MultiOn Browse Capabilities. |
| `MySQLSearchTool` | `crewai_tools.tools.mysql_search_tool.mysql_search_tool` | !!! abstract "Usage Documentation" |
| `NL2SQLTool` | `crewai_tools.tools.nl2sql.nl2sql_tool` | Tool that converts natural language to SQL and executes it against a database. |
| `NavigateBackTool` | `crewai_tools.aws.bedrock.browser.browser_toolkit` | Tool for navigating back in browser history. |
| `NavigateTool` | `crewai_tools.aws.bedrock.browser.browser_toolkit` | Tool for navigating a browser to a URL. |
| `OCRTool` | `crewai_tools.tools.ocr_tool.ocr_tool` | A tool for performing Optical Character Recognition on images. |
| `OxylabsAmazonProductScraperTool` | `crewai_tools.tools.oxylabs_amazon_product_scraper_tool.oxylabs_amazon_product_scraper_tool` | Scrape Amazon product pages with OxylabsAmazonProductScraperTool. |
| `OxylabsAmazonSearchScraperTool` | `crewai_tools.tools.oxylabs_amazon_search_scraper_tool.oxylabs_amazon_search_scraper_tool` | Scrape Amazon search results with OxylabsAmazonSearchScraperTool. |
| `OxylabsGoogleSearchScraperTool` | `crewai_tools.tools.oxylabs_google_search_scraper_tool.oxylabs_google_search_scraper_tool` | Scrape Google Search results with OxylabsGoogleSearchScraperTool. |
| `OxylabsUniversalScraperTool` | `crewai_tools.tools.oxylabs_universal_scraper_tool.oxylabs_universal_scraper_tool` | Scrape any website with OxylabsUniversalScraperTool. |
| `PDFSearchTool` | `crewai_tools.tools.pdf_search_tool.pdf_search_tool` | !!! abstract "Usage Documentation" |
| `ParallelSearchTool` | `crewai_tools.tools.parallel_tools.parallel_search_tool` | !!! abstract "Usage Documentation" |
| `PatronusEvalTool` | `crewai_tools.tools.patronus_eval_tool.patronus_eval_tool` | !!! abstract "Usage Documentation" |
| `PatronusLocalEvaluatorTool` | `crewai_tools.tools.patronus_eval_tool.patronus_local_evaluator_tool` | !!! abstract "Usage Documentation" |
| `PatronusPredefinedCriteriaEvalTool` | `crewai_tools.tools.patronus_eval_tool.patronus_predefined_criteria_eval_tool` | PatronusEvalTool is a tool to automatically evaluate and score agent interactions. |
| `QdrantVectorSearchTool` | `crewai_tools.tools.qdrant_vector_search_tool.qdrant_search_tool` | Vector search tool for Qdrant. |
| `RagTool` | `crewai_tools.tools.rag.rag_tool` | !!! abstract "Usage Documentation" |
| `ReadFilesTool` | `crewai_tools.aws.bedrock.code_interpreter.code_interpreter_toolkit` | Tool for reading content of files in the environment. |
| `S3ReaderTool` | `crewai_tools.aws.s3.reader_tool` | !!! abstract "Usage Documentation" |
| `S3WriterTool` | `crewai_tools.aws.s3.writer_tool` | !!! abstract "Usage Documentation" |
| `ScrapeElementFromWebsiteTool` | `crewai_tools.tools.scrape_element_from_website.scrape_element_from_website` | !!! abstract "Usage Documentation" |
| `ScrapeWebsiteTool` | `crewai_tools.tools.scrape_website_tool.scrape_website_tool` | !!! abstract "Usage Documentation" |
| `ScrapegraphScrapeTool` | `crewai_tools.tools.scrapegraph_scrape_tool.scrapegraph_scrape_tool` | A tool that uses Scrapegraph AI to intelligently scrape website content. |
| `ScrapflyScrapeWebsiteTool` | `crewai_tools.tools.scrapfly_scrape_website_tool.scrapfly_scrape_website_tool` | !!! abstract "Usage Documentation" |
| `SeleniumScrapingTool` | `crewai_tools.tools.selenium_scraping_tool.selenium_scraping_tool` | !!! abstract "Usage Documentation" |
| `SerpApiBaseTool` | `crewai_tools.tools.serpapi_tool.serpapi_base_tool` | Base class for SerpApi functionality with shared capabilities. |
| `SerpApiGoogleSearchTool` | `crewai_tools.tools.serpapi_tool.serpapi_google_search_tool` | Base class for SerpApi functionality with shared capabilities. |
| `SerpApiGoogleShoppingTool` | `crewai_tools.tools.serpapi_tool.serpapi_google_shopping_tool` | Base class for SerpApi functionality with shared capabilities. |
| `SerperDevTool` | `crewai_tools.tools.serper_dev_tool.serper_dev_tool` | !!! abstract "Usage Documentation" |
| `SerperScrapeWebsiteTool` | `crewai_tools.tools.serper_scrape_website_tool.serper_scrape_website_tool` | !!! abstract "Usage Documentation" |
| `SerplyJobSearchTool` | `crewai_tools.tools.serply_api_tool.serply_job_search_tool` | !!! abstract "Usage Documentation" |
| `SerplyNewsSearchTool` | `crewai_tools.tools.serply_api_tool.serply_news_search_tool` | !!! abstract "Usage Documentation" |
| `SerplyScholarSearchTool` | `crewai_tools.tools.serply_api_tool.serply_scholar_search_tool` | !!! abstract "Usage Documentation" |
| `SerplyWebSearchTool` | `crewai_tools.tools.serply_api_tool.serply_web_search_tool` | !!! abstract "Usage Documentation" |
| `SerplyWebpageToMarkdownTool` | `crewai_tools.tools.serply_api_tool.serply_webpage_to_markdown_tool` | !!! abstract "Usage Documentation" |
| `SingleStoreSearchTool` | `crewai_tools.tools.singlestore_search_tool.singlestore_search_tool` | A tool for performing semantic searches on SingleStore database tables. |
| `SnowflakeSearchTool` | `crewai_tools.tools.snowflake_search_tool.snowflake_search_tool` | Tool for executing queries and semantic search on Snowflake. |
| `SpiderTool` | `crewai_tools.tools.spider_tool.spider_tool` | Tool for scraping and crawling websites. |
| `StagehandTool` | `crewai_tools.tools.stagehand_tool.stagehand_tool` | A tool that uses Stagehand to automate web browser interactions using natural language with atomic action handling. |
| `StartCommandTool` | `crewai_tools.aws.bedrock.code_interpreter.code_interpreter_toolkit` | Tool for starting long-running commands asynchronously. |
| `StopTaskTool` | `crewai_tools.aws.bedrock.code_interpreter.code_interpreter_toolkit` | Tool for stopping running tasks. |
| `TXTSearchTool` | `crewai_tools.tools.txt_search_tool.txt_search_tool` | !!! abstract "Usage Documentation" |
| `TavilyExtractorTool` | `crewai_tools.tools.tavily_extractor_tool.tavily_extractor_tool` | !!! abstract "Usage Documentation" |
| `TavilyGetResearchTool` | `crewai_tools.tools.tavily_get_research_tool.tavily_get_research_tool` | Tool that uses the Tavily Research status endpoint to retrieve results. |
| `TavilyResearchTool` | `crewai_tools.tools.tavily_research_tool.tavily_research_tool` | Tool that uses the Tavily Research API to create research tasks. |
| `TavilySearchTool` | `crewai_tools.tools.tavily_search_tool.tavily_search_tool` | Tool that uses the Tavily Search API to perform web searches. |
| `VisionTool` | `crewai_tools.tools.vision_tool.vision_tool` | Tool for analyzing images using vision models. |
| `WeaviateVectorSearchTool` | `crewai_tools.tools.weaviate_tool.vector_search` | Tool to search the Weaviate database. |
| `WebsiteSearchTool` | `crewai_tools.tools.website_search.website_search_tool` | !!! abstract "Usage Documentation" |
| `WriteFilesTool` | `crewai_tools.aws.bedrock.code_interpreter.code_interpreter_toolkit` | Tool for creating or updating files in the environment. |
| `XMLSearchTool` | `crewai_tools.tools.xml_search_tool.xml_search_tool` | !!! abstract "Usage Documentation" |
| `YoutubeChannelSearchTool` | `crewai_tools.tools.youtube_channel_search_tool.youtube_channel_search_tool` | !!! abstract "Usage Documentation" |
| `YoutubeVideoSearchTool` | `crewai_tools.tools.youtube_video_search_tool.youtube_video_search_tool` | !!! abstract "Usage Documentation" |
| `ZapierActionTool` | `crewai_tools.adapters.zapier_adapter` | A tool that wraps a Zapier action. |

---

## 十六、全包类索引

crewai 包内公开模块全部类（按模块分组）：

- `crewai.a2a.auth.schemas`：`APIKeyAuth`、`AuthScheme`、`BearerTokenAuth`、`HTTPBasicAuth`、`HTTPDigestAuth`、`OAuth2AuthorizationCode`、`OAuth2ClientCredentials`
- `crewai.a2a.auth.server_schemes`：`APIKeyServerAuth`、`AuthenticatedUser`、`EnterpriseTokenAuth`、`HTTPException`、`MTLSServerAuth`、`OAuth2ServerAuth`、`OIDCAuth`、`ServerAuthScheme`、`SimpleTokenAuth`
- `crewai.a2a.config`：`A2AClientConfig`、`A2AConfig`、`A2AServerConfig`、`AgentCardSigningConfig`、`ClientTransportConfig`、`GRPCClientConfig`、`GRPCServerConfig`、`HTTPJSONConfig`、`JSONRPCClientConfig`、`JSONRPCServerConfig`、`ServerPushNotificationConfig`、`ServerTransportConfig`
- `crewai.a2a.types`：`AgentResponseProtocol`、`PartsDict`、`PartsMetadataDict`
- `crewai.a2a.utils.logging`：`JSONFormatter`、`LogContext`
- `crewai.agent.core`：`Agent`
- `crewai.agent.internal.meta`：`AgentMeta`
- `crewai.agent.planning_config`：`PlanningConfig`
- `crewai.agents.agent_adapters.base_agent_adapter`：`BaseAgentAdapter`
- `crewai.agents.agent_adapters.base_converter_adapter`：`BaseConverterAdapter`
- `crewai.agents.agent_adapters.base_tool_adapter`：`BaseToolAdapter`
- `crewai.agents.agent_adapters.langgraph.langgraph_adapter`：`LangGraphAgentAdapter`
- `crewai.agents.agent_adapters.langgraph.langgraph_tool_adapter`：`LangGraphToolAdapter`
- `crewai.agents.agent_adapters.langgraph.protocols`：`LangGraphCheckPointMemoryModule`、`LangGraphMemorySaver`、`LangGraphPrebuiltModule`
- `crewai.agents.agent_adapters.langgraph.structured_output_converter`：`LangGraphConverterAdapter`
- `crewai.agents.agent_adapters.openai_agents.protocols`：`AgentKwargs`、`OpenAIAgent`、`OpenAIAgentsModule`、`OpenAIFunctionTool`、`OpenAIRunner`、`OpenAITool`
- `crewai.agents.agent_adapters.openai_agents.structured_output_converter`：`OpenAIConverterAdapter`
- `crewai.agents.agent_builder.base_agent`：`BaseAgent`
- `crewai.agents.agent_builder.base_agent_executor`：`BaseAgentExecutor`
- `crewai.agents.agent_builder.utilities.base_output_converter`：`OutputConverter`
- `crewai.agents.agent_builder.utilities.base_token_process`：`TokenProcess`
- `crewai.agents.cache.cache_handler`：`CacheHandler`
- `crewai.agents.crew_agent_executor`：`CrewAgentExecutor`
- `crewai.agents.parser`：`AgentAction`、`AgentFinish`、`OutputParserError`
- `crewai.agents.planner_observer`：`PlannerObserver`
- `crewai.agents.step_executor`：`StepExecutor`
- `crewai.agents.tools_handler`：`ToolsHandler`
- `crewai.context`：`ExecutionContext`
- `crewai.core.providers.content_processor`：`ContentProcessorProvider`、`NoOpContentProcessor`
- `crewai.core.providers.human_input`：`AsyncExecutorContext`、`ExecutorContext`、`HumanInputProvider`、`SyncHumanInputProvider`
- `crewai.crew`：`Crew`
- `crewai.crews.crew_output`：`CrewOutput`
- `crewai.crews.utils`：`ForEachStreamingContext`、`StreamingContext`、`TaskExecutionData`
- `crewai.events.base_event_listener`：`BaseEventListener`
- `crewai.events.base_events`：`BaseEvent`
- `crewai.events.depends`：`Depends`、`EventHandler`
- `crewai.events.event_bus`：`CrewAIEventsBus`
- `crewai.events.event_context`：`EmptyStackError`、`EventContextConfig`、`EventPairingError`、`MismatchBehavior`、`StackDepthExceededError`
- `crewai.events.event_listener`：`EventListener`
- `crewai.events.handler_graph`：`CircularDependencyError`、`HandlerGraph`
- `crewai.events.listeners.tracing.first_time_trace_handler`：`FirstTimeTraceHandler`
- `crewai.events.listeners.tracing.trace_batch_manager`：`TraceBatch`、`TraceBatchManager`
- `crewai.events.listeners.tracing.trace_listener`：`TraceCollectionListener`
- `crewai.events.listeners.tracing.types`：`TraceEvent`
- `crewai.events.types.a2a_events`：`A2AAgentCardFetchedEvent`、`A2AArtifactReceivedEvent`、`A2AAuthenticationFailedEvent`、`A2AConnectionErrorEvent`、`A2AContentTypeNegotiatedEvent`、`A2AContextCompletedEvent`、`A2AContextCreatedEvent`、`A2AContextExpiredEvent`、`A2AContextIdleEvent`、`A2AContextPrunedEvent`、`A2AConversationCompletedEvent`、`A2AConversationStartedEvent`、`A2ADelegationCompletedEvent`、`A2ADelegationStartedEvent`、`A2AEventBase`、`A2AMessageSentEvent`、`A2AParallelDelegationCompletedEvent`、`A2AParallelDelegationStartedEvent`、`A2APollingStartedEvent`、`A2APollingStatusEvent`、`A2APushNotificationReceivedEvent`、`A2APushNotificationRegisteredEvent`、`A2APushNotificationSentEvent`、`A2APushNotificationTimeoutEvent`、`A2AResponseReceivedEvent`、`A2AServerTaskCanceledEvent`、`A2AServerTaskCompletedEvent`、`A2AServerTaskFailedEvent`、`A2AServerTaskStartedEvent`、`A2AStreamingChunkEvent`、`A2AStreamingStartedEvent`、`A2ATransportNegotiatedEvent`
- `crewai.events.types.agent_events`：`AgentEvaluationCompletedEvent`、`AgentEvaluationFailedEvent`、`AgentEvaluationStartedEvent`、`AgentExecutionCompletedEvent`、`AgentExecutionErrorEvent`、`AgentExecutionStartedEvent`、`LiteAgentExecutionCompletedEvent`、`LiteAgentExecutionErrorEvent`、`LiteAgentExecutionStartedEvent`
- `crewai.events.types.checkpoint_events`：`CheckpointBaseEvent`、`CheckpointCompletedEvent`、`CheckpointFailedEvent`、`CheckpointForkBaseEvent`、`CheckpointForkCompletedEvent`、`CheckpointForkStartedEvent`、`CheckpointPrunedEvent`、`CheckpointRestoreBaseEvent`、`CheckpointRestoreCompletedEvent`、`CheckpointRestoreFailedEvent`、`CheckpointRestoreStartedEvent`、`CheckpointStartedEvent`
- `crewai.events.types.crew_events`：`CrewBaseEvent`、`CrewKickoffCompletedEvent`、`CrewKickoffFailedEvent`、`CrewKickoffStartedEvent`、`CrewTestCompletedEvent`、`CrewTestFailedEvent`、`CrewTestResultEvent`、`CrewTestStartedEvent`、`CrewTrainCompletedEvent`、`CrewTrainFailedEvent`、`CrewTrainStartedEvent`
- `crewai.events.types.env_events`：`CCEnvEvent`、`CodexEnvEvent`、`CursorEnvEvent`、`DefaultEnvEvent`
- `crewai.events.types.flow_events`：`FlowCreatedEvent`、`FlowEvent`、`FlowFinishedEvent`、`FlowInputReceivedEvent`、`FlowInputRequestedEvent`、`FlowPausedEvent`、`FlowPlotEvent`、`FlowStartedEvent`、`HumanFeedbackReceivedEvent`、`HumanFeedbackRequestedEvent`、`MethodExecutionFailedEvent`、`MethodExecutionFinishedEvent`、`MethodExecutionPausedEvent`、`MethodExecutionStartedEvent`
- `crewai.events.types.knowledge_events`：`KnowledgeEventBase`、`KnowledgeQueryCompletedEvent`、`KnowledgeQueryFailedEvent`、`KnowledgeQueryStartedEvent`、`KnowledgeRetrievalCompletedEvent`、`KnowledgeRetrievalStartedEvent`、`KnowledgeSearchQueryFailedEvent`
- `crewai.events.types.llm_events`：`FunctionCall`、`LLMCallCompletedEvent`、`LLMCallFailedEvent`、`LLMCallStartedEvent`、`LLMCallType`、`LLMEventBase`、`LLMStreamChunkEvent`、`LLMThinkingChunkEvent`、`ToolCall`
- `crewai.events.types.llm_guardrail_events`：`LLMGuardrailBaseEvent`、`LLMGuardrailCompletedEvent`、`LLMGuardrailStartedEvent`
- `crewai.events.types.logging_events`：`AgentLogsExecutionEvent`、`AgentLogsStartedEvent`
- `crewai.events.types.mcp_events`：`MCPConfigFetchFailedEvent`、`MCPConnectionCompletedEvent`、`MCPConnectionFailedEvent`、`MCPConnectionStartedEvent`、`MCPEvent`、`MCPToolExecutionCompletedEvent`、`MCPToolExecutionFailedEvent`、`MCPToolExecutionStartedEvent`
- `crewai.events.types.memory_events`：`MemoryBaseEvent`、`MemoryQueryCompletedEvent`、`MemoryQueryFailedEvent`、`MemoryQueryStartedEvent`、`MemoryRetrievalCompletedEvent`、`MemoryRetrievalFailedEvent`、`MemoryRetrievalStartedEvent`、`MemorySaveCompletedEvent`、`MemorySaveFailedEvent`、`MemorySaveStartedEvent`
- `crewai.events.types.observation_events`：`GoalAchievedEarlyEvent`、`ObservationEvent`、`PlanRefinementEvent`、`PlanReplanTriggeredEvent`、`StepObservationCompletedEvent`、`StepObservationFailedEvent`、`StepObservationStartedEvent`
- `crewai.events.types.reasoning_events`：`AgentReasoningCompletedEvent`、`AgentReasoningFailedEvent`、`AgentReasoningStartedEvent`、`ReasoningEvent`
- `crewai.events.types.skill_events`：`SkillActivatedEvent`、`SkillDiscoveryCompletedEvent`、`SkillDiscoveryStartedEvent`、`SkillEvent`、`SkillLoadFailedEvent`、`SkillLoadedEvent`
- `crewai.events.types.system_events`：`SigContEvent`、`SigHupEvent`、`SigIntEvent`、`SigTStpEvent`、`SigTermEvent`、`SignalType`
- `crewai.events.types.task_events`：`TaskCompletedEvent`、`TaskEvaluationEvent`、`TaskFailedEvent`、`TaskStartedEvent`
- `crewai.events.types.tool_usage_events`：`ToolExecutionErrorEvent`、`ToolSelectionErrorEvent`、`ToolUsageErrorEvent`、`ToolUsageEvent`、`ToolUsageFinishedEvent`、`ToolUsageStartedEvent`、`ToolValidateInputErrorEvent`
- `crewai.events.utils.console_formatter`：`ConsoleFormatter`
- `crewai.experimental.agent_executor`：`AgentExecutor`、`AgentExecutorState`、`CrewAgentExecutorFlow`
- `crewai.experimental.evaluation.agent_evaluator`：`AgentEvaluator`、`ExecutionState`
- `crewai.experimental.evaluation.base_evaluator`：`AgentAggregatedEvaluationResult`、`AgentEvaluationResult`、`AggregationStrategy`、`BaseEvaluator`、`EvaluationScore`、`MetricCategory`
- `crewai.experimental.evaluation.evaluation_display`：`EvaluationDisplayFormatter`
- `crewai.experimental.evaluation.evaluation_listener`：`EvaluationTraceCallback`
- `crewai.experimental.evaluation.experiment.result`：`ExperimentResult`、`ExperimentResults`
- `crewai.experimental.evaluation.experiment.result_display`：`ExperimentResultsDisplay`
- `crewai.experimental.evaluation.experiment.runner`：`ExperimentRunner`
- `crewai.experimental.evaluation.metrics.goal_metrics`：`GoalAlignmentEvaluator`
- `crewai.experimental.evaluation.metrics.reasoning_metrics`：`ReasoningEfficiencyEvaluator`、`ReasoningPatternType`
- `crewai.experimental.evaluation.metrics.semantic_quality_metrics`：`SemanticQualityEvaluator`
- `crewai.experimental.evaluation.metrics.tools_metrics`：`ParameterExtractionEvaluator`、`ToolInvocationEvaluator`、`ToolSelectionEvaluator`
- `crewai.flow.async_feedback.providers`：`ConsoleProvider`
- `crewai.flow.async_feedback.types`：`HumanFeedbackPending`、`HumanFeedbackProvider`、`PendingFeedbackContext`
- `crewai.flow.flow`：`Flow`、`FlowMeta`、`FlowState`、`LockedDictProxy`、`LockedListProxy`、`StateProxy`
- `crewai.flow.flow_config`：`FlowConfig`
- `crewai.flow.flow_serializer`：`EdgeInfo`、`FlowStructureInfo`、`MethodInfo`、`StateFieldInfo`、`StateSchemaInfo`
- `crewai.flow.flow_trackable`：`FlowTrackable`
- `crewai.flow.flow_wrappers`：`FlowCondition`、`FlowMethod`、`ListenMethod`、`RouterMethod`、`StartMethod`
- `crewai.flow.human_feedback`：`DistilledLessons`、`HumanFeedbackConfig`、`HumanFeedbackMethod`、`HumanFeedbackResult`、`PreReviewResult`
- `crewai.flow.input_provider`：`InputProvider`、`InputResponse`
- `crewai.flow.persistence.base`：`FlowPersistence`
- `crewai.flow.persistence.decorators`：`PersistenceDecorator`
- `crewai.flow.persistence.sqlite`：`SQLiteFlowPersistence`
- `crewai.flow.types`：`CompletedMethodData`、`ExecutionMethodData`、`FlowData`、`FlowExecutionData`、`FlowMethodCallable`、`FlowMethodData`、`InputHistoryEntry`
- `crewai.flow.visualization.renderers.interactive`：`CSSExtension`、`JSExtension`
- `crewai.flow.visualization.types`：`FlowStructure`、`NodeMetadata`、`StructureEdge`
- `crewai.hooks.llm_hooks`：`LLMCallHookContext`
- `crewai.hooks.tool_hooks`：`ToolCallHookContext`
- `crewai.hooks.types`：`AfterLLMCallHook`、`AfterToolCallHook`、`BeforeLLMCallHook`、`BeforeToolCallHook`、`Hook`
- `crewai.hooks.wrappers`：`AfterLLMCallHookMethod`、`AfterToolCallHookMethod`、`BeforeLLMCallHookMethod`、`BeforeToolCallHookMethod`
- `crewai.knowledge.knowledge`：`Knowledge`
- `crewai.knowledge.knowledge_config`：`KnowledgeConfig`
- `crewai.knowledge.source.base_file_knowledge_source`：`BaseFileKnowledgeSource`
- `crewai.knowledge.source.base_knowledge_source`：`BaseKnowledgeSource`
- `crewai.knowledge.source.crew_docling_source`：`CrewDoclingSource`
- `crewai.knowledge.source.csv_knowledge_source`：`CSVKnowledgeSource`
- `crewai.knowledge.source.excel_knowledge_source`：`ExcelKnowledgeSource`
- `crewai.knowledge.source.json_knowledge_source`：`JSONKnowledgeSource`
- `crewai.knowledge.source.pdf_knowledge_source`：`PDFKnowledgeSource`
- `crewai.knowledge.source.string_knowledge_source`：`StringKnowledgeSource`
- `crewai.knowledge.source.text_file_knowledge_source`：`TextFileKnowledgeSource`
- `crewai.knowledge.source.utils.source_helper`：`SourceHelper`
- `crewai.knowledge.storage.base_knowledge_storage`：`BaseKnowledgeStorage`
- `crewai.knowledge.storage.knowledge_storage`：`KnowledgeStorage`
- `crewai.lite_agent`：`LiteAgent`
- `crewai.lite_agent_output`：`LiteAgentOutput`、`TodoExecutionResult`
- `crewai.llm`：`AccumulatedToolArgs`、`Delta`、`FunctionArgs`、`LLM`、`StreamingChoices`
- `crewai.llms.base_llm`：`BaseLLM`、`JsonResponseFormat`
- `crewai.llms.hooks.base`：`BaseInterceptor`
- `crewai.llms.hooks.transport`：`AsyncHTTPTransport`、`HTTPTransport`、`HTTPTransportKwargs`
- `crewai.llms.providers.openai.completion`：`CodeInterpreterFileResult`、`CodeInterpreterLogResult`、`CodeInterpreterResult`、`ComputerUseResult`、`FileSearchResult`、`FileSearchResultItem`、`OpenAICompletion`、`ReasoningSummary`、`ResponsesAPIResult`、`WebSearchResult`
- `crewai.llms.providers.openai_compatible.completion`：`OpenAICompatibleCompletion`、`ProviderConfig`
- `crewai.mcp.config`：`MCPServerHTTP`、`MCPServerSSE`、`MCPServerStdio`
- `crewai.mcp.filters`：`StaticToolFilter`、`ToolFilterContext`
- `crewai.mcp.tool_resolver`：`MCPToolResolver`
- `crewai.mcp.transports.base`：`BaseTransport`、`TransportType`
- `crewai.mcp.transports.http`：`HTTPTransport`
- `crewai.mcp.transports.sse`：`SSETransport`
- `crewai.mcp.transports.stdio`：`StdioTransport`
- `crewai.memory.analyze`：`ConsolidationAction`、`ConsolidationPlan`、`ExtractedMemories`、`ExtractedMetadata`、`MemoryAnalysis`、`QueryAnalysis`
- `crewai.memory.encoding_flow`：`EncodingFlow`、`EncodingState`、`ItemState`
- `crewai.memory.memory_scope`：`MemoryScope`、`MemorySlice`
- `crewai.memory.recall_flow`：`RecallFlow`、`RecallState`
- `crewai.memory.storage.backend`：`StorageBackend`
- `crewai.memory.storage.kickoff_task_outputs_storage`：`KickoffTaskOutputsSQLiteStorage`
- `crewai.memory.storage.lancedb_storage`：`LanceDBStorage`
- `crewai.memory.types`：`MemoryConfig`、`MemoryMatch`、`MemoryRecord`、`ScopeInfo`
- `crewai.memory.unified_memory`：`Memory`
- `crewai.process`：`Process`
- `crewai.project.crew_base`：`AgentConfig`、`CrewBase`、`CrewBaseMeta`、`TaskConfig`
- `crewai.project.wrappers`：`AfterKickoffMethod`、`AgentMethod`、`BeforeKickoffMethod`、`BoundTaskMethod`、`CacheHandlerMethod`、`CallbackMethod`、`CrewClass`、`CrewInstance`、`CrewMetadata`、`CrewMethod`、`DecoratedMethod`、`LLMMethod`、`OutputClass`、`OutputJsonClass`、`OutputPydanticClass`、`TaskMethod`、`TaskResult`、`ToolMethod`
- `crewai.rag.chromadb.config`：`ChromaDBConfig`
- `crewai.rag.chromadb.types`：`ChromaDBCollectionCreateParams`、`ChromaDBCollectionSearchParams`、`ChromaEmbeddingFunctionWrapper`、`ExtractedSearchParams`、`PreparedDocuments`
- `crewai.rag.config.base`：`BaseRagConfig`
- `crewai.rag.config.optional_imports.protocols`：`ChromaFactoryModule`、`QdrantFactoryModule`
- `crewai.rag.config.optional_imports.providers`：`MissingChromaDBConfig`、`MissingQdrantConfig`
- `crewai.rag.config.utils`：`RagContext`
- `crewai.rag.core.base_client`：`BaseClient`、`BaseCollectionAddParams`、`BaseCollectionParams`、`BaseCollectionSearchParams`
- `crewai.rag.core.base_embeddings_callable`：`EmbeddingFunction`
- `crewai.rag.core.base_embeddings_provider`：`BaseEmbeddingsProvider`、`BaseEmbeddingsProvider[AmazonBedrockEmbeddingFunction]`、`BaseEmbeddingsProvider[Any]`、`BaseEmbeddingsProvider[CohereEmbeddingFunction]`、`BaseEmbeddingsProvider[CustomEmbeddingFunction]`、`BaseEmbeddingsProvider[GoogleGenAIVertexEmbeddingFunction]`、`BaseEmbeddingsProvider[GoogleGenerativeAiEmbeddingFunction]`、`BaseEmbeddingsProvider[HuggingFaceEmbeddingFunction]`、`BaseEmbeddingsProvider[InstructorEmbeddingFunction]`、`BaseEmbeddingsProvider[JinaEmbeddingFunction]`、`BaseEmbeddingsProvider[ONNXMiniLM_L6_V2]`、`BaseEmbeddingsProvider[OllamaEmbeddingFunction]`、`BaseEmbeddingsProvider[OpenAIEmbeddingFunction]`、`BaseEmbeddingsProvider[OpenCLIPEmbeddingFunction]`、`BaseEmbeddingsProvider[RoboflowEmbeddingFunction]`、`BaseEmbeddingsProvider[SentenceTransformerEmbeddingFunction]`、`BaseEmbeddingsProvider[Text2VecEmbeddingFunction]`、`BaseEmbeddingsProvider[VoyageAIEmbeddingFunction]`、`BaseEmbeddingsProvider[WatsonXEmbeddingFunction]`
- `crewai.rag.core.exceptions`：`ClientMethodMismatchError`
- `crewai.rag.embeddings.providers.aws.bedrock`：`BedrockProvider`
- `crewai.rag.embeddings.providers.aws.types`：`BedrockProviderConfig`、`BedrockProviderSpec`
- `crewai.rag.embeddings.providers.cohere.cohere_provider`：`CohereProvider`
- `crewai.rag.embeddings.providers.cohere.types`：`CohereProviderConfig`、`CohereProviderSpec`
- `crewai.rag.embeddings.providers.custom.custom_provider`：`CustomProvider`
- `crewai.rag.embeddings.providers.custom.embedding_callable`：`CustomEmbeddingFunction`
- `crewai.rag.embeddings.providers.custom.types`：`CustomProviderConfig`、`CustomProviderSpec`
- `crewai.rag.embeddings.providers.google.genai_vertex_embedding`：`GoogleGenAIVertexEmbeddingFunction`
- `crewai.rag.embeddings.providers.google.generative_ai`：`GenerativeAiProvider`
- `crewai.rag.embeddings.providers.google.types`：`GenerativeAiProviderConfig`、`GenerativeAiProviderSpec`、`VertexAIProviderConfig`、`VertexAIProviderSpec`
- `crewai.rag.embeddings.providers.google.vertex`：`VertexAIProvider`
- `crewai.rag.embeddings.providers.huggingface.huggingface_provider`：`HuggingFaceProvider`
- `crewai.rag.embeddings.providers.huggingface.types`：`HuggingFaceProviderConfig`、`HuggingFaceProviderSpec`
- `crewai.rag.embeddings.providers.ibm.embedding_callable`：`WatsonXEmbeddingFunction`
- `crewai.rag.embeddings.providers.ibm.types`：`WatsonXProviderConfig`、`WatsonXProviderSpec`
- `crewai.rag.embeddings.providers.ibm.watsonx`：`WatsonXProvider`
- `crewai.rag.embeddings.providers.instructor.instructor_provider`：`InstructorProvider`
- `crewai.rag.embeddings.providers.instructor.types`：`InstructorProviderConfig`、`InstructorProviderSpec`
- `crewai.rag.embeddings.providers.jina.jina_provider`：`JinaProvider`
- `crewai.rag.embeddings.providers.jina.types`：`JinaProviderConfig`、`JinaProviderSpec`
- `crewai.rag.embeddings.providers.microsoft.azure`：`AzureProvider`
- `crewai.rag.embeddings.providers.microsoft.types`：`AzureProviderConfig`、`AzureProviderSpec`
- `crewai.rag.embeddings.providers.ollama.ollama_provider`：`OllamaProvider`
- `crewai.rag.embeddings.providers.ollama.types`：`OllamaProviderConfig`、`OllamaProviderSpec`
- `crewai.rag.embeddings.providers.onnx.onnx_provider`：`ONNXProvider`
- `crewai.rag.embeddings.providers.onnx.types`：`ONNXProviderConfig`、`ONNXProviderSpec`
- `crewai.rag.embeddings.providers.openai.openai_provider`：`OpenAIProvider`
- `crewai.rag.embeddings.providers.openai.types`：`OpenAIProviderConfig`、`OpenAIProviderSpec`
- `crewai.rag.embeddings.providers.openclip.openclip_provider`：`OpenCLIPProvider`
- `crewai.rag.embeddings.providers.openclip.types`：`OpenCLIPProviderConfig`、`OpenCLIPProviderSpec`
- `crewai.rag.embeddings.providers.roboflow.roboflow_provider`：`RoboflowProvider`
- `crewai.rag.embeddings.providers.roboflow.types`：`RoboflowProviderConfig`、`RoboflowProviderSpec`
- `crewai.rag.embeddings.providers.sentence_transformer.sentence_transformer_provider`：`SentenceTransformerProvider`
- `crewai.rag.embeddings.providers.sentence_transformer.types`：`SentenceTransformerProviderConfig`、`SentenceTransformerProviderSpec`
- `crewai.rag.embeddings.providers.text2vec.text2vec_provider`：`Text2VecProvider`
- `crewai.rag.embeddings.providers.text2vec.types`：`Text2VecProviderConfig`、`Text2VecProviderSpec`
- `crewai.rag.embeddings.providers.voyageai.embedding_callable`：`VoyageAIEmbeddingFunction`
- `crewai.rag.embeddings.providers.voyageai.types`：`VoyageAIProviderConfig`、`VoyageAIProviderSpec`
- `crewai.rag.embeddings.providers.voyageai.voyageai_provider`：`VoyageAIProvider`
- `crewai.rag.storage.base_rag_storage`：`BaseRAGStorage`
- `crewai.rag.types`：`BaseRecord`、`SearchResult`
- `crewai.security.fingerprint`：`Fingerprint`
- `crewai.security.security_config`：`SecurityConfig`
- `crewai.skills.models`：`Skill`、`SkillFrontmatter`
- `crewai.skills.parser`：`SkillParseError`
- `crewai.state.checkpoint_config`：`CheckpointConfig`
- `crewai.state.event_record`：`EventNode`、`EventRecord`
- `crewai.state.provider.core`：`BaseProvider`
- `crewai.state.provider.json_provider`：`JsonProvider`
- `crewai.state.provider.sqlite_provider`：`SqliteProvider`
- `crewai.state.runtime`：`RuntimeState`
- `crewai.task`：`Task`
- `crewai.tasks.conditional_task`：`ConditionalTask`
- `crewai.tasks.hallucination_guardrail`：`HallucinationGuardrail`
- `crewai.tasks.llm_guardrail`：`LLMGuardrail`、`LLMGuardrailResult`
- `crewai.tasks.output_format`：`OutputFormat`
- `crewai.tasks.task_output`：`TaskOutput`
- `crewai.telemetry.telemetry`：`SafeOTLPSpanExporter`、`Telemetry`
- `crewai.tools.agent_tools.add_image_tool`：`AddImageTool`、`AddImageToolSchema`
- `crewai.tools.agent_tools.agent_tools`：`AgentTools`
- `crewai.tools.agent_tools.ask_question_tool`：`AskQuestionTool`、`AskQuestionToolSchema`
- `crewai.tools.agent_tools.base_agent_tools`：`BaseAgentTool`
- `crewai.tools.agent_tools.delegate_work_tool`：`DelegateWorkTool`、`DelegateWorkToolSchema`
- `crewai.tools.agent_tools.read_file_tool`：`ReadFileTool`、`ReadFileToolSchema`
- `crewai.tools.base_tool`：`BaseTool`、`EnvVar`、`Tool`
- `crewai.tools.cache_tools.cache_tools`：`CacheTools`
- `crewai.tools.mcp_native_tool`：`MCPNativeTool`
- `crewai.tools.mcp_tool_wrapper`：`MCPToolWrapper`
- `crewai.tools.memory_tools`：`RecallMemorySchema`、`RecallMemoryTool`、`RememberSchema`、`RememberTool`
- `crewai.tools.structured_tool`：`CrewStructuredTool`、`ToolUsageLimitExceededError`
- `crewai.tools.tool_calling`：`InstructorToolCalling`、`ToolCalling`
- `crewai.tools.tool_types`：`ToolResult`
- `crewai.tools.tool_usage`：`ToolUsage`、`ToolUsageError`
- `crewai.types.crew_chat`：`ChatInputField`、`ChatInputs`
- `crewai.types.streaming`：`CrewStreamingOutput`、`FlowStreamingOutput`、`StreamChunk`、`StreamChunkType`、`StreamingOutputBase`、`ToolCallChunk`
- `crewai.types.usage_metrics`：`UsageMetrics`
- `crewai.utilities.agent_utils`：`NativeToolCallResult`、`SummaryContent`
- `crewai.utilities.converter`：`Converter`、`ConverterError`、`CreateConverterKwargs`
- `crewai.utilities.crew.models`：`CrewContext`
- `crewai.utilities.crew_json_encoder`：`CrewJSONEncoder`
- `crewai.utilities.errors`：`AgentRepositoryError`、`DatabaseError`、`DatabaseOperationError`
- `crewai.utilities.evaluators.crew_evaluator_handler`：`CrewEvaluator`、`TaskEvaluationPydanticOutput`
- `crewai.utilities.evaluators.task_evaluator`：`Entity`、`TaskEvaluation`、`TaskEvaluator`、`TrainingTaskEvaluation`
- `crewai.utilities.exceptions.context_window_exceeding_exception`：`LLMContextLengthExceededError`
- `crewai.utilities.file_handler`：`FileHandler`、`LogEntry`、`PickleHandler`
- `crewai.utilities.guardrail`：`GuardrailResult`
- `crewai.utilities.i18n`：`I18N`
- `crewai.utilities.import_utils`：`OptionalDependencyError`
- `crewai.utilities.internal_instructor`：`InternalInstructor`
- `crewai.utilities.logger`：`Logger`
- `crewai.utilities.planning_handler`：`CrewPlanner`、`PlanPerTask`、`PlannerTaskPydanticOutput`
- `crewai.utilities.planning_types`：`PlanStep`、`StepObservation`、`StepRefinement`、`TodoItem`、`TodoList`
- `crewai.utilities.printer`：`ColoredText`、`Printer`
- `crewai.utilities.prompts`：`Prompts`、`StandardPromptResult`、`SystemPromptResult`
- `crewai.utilities.pydantic_schema_utils`：`JsonSchemaInfo`、`ModelDescription`
- `crewai.utilities.reasoning_handler`：`AgentPlanning`、`AgentPlanningOutput`、`AgentReasoning`、`AgentReasoningOutput`、`PlanningPlan`、`ReasoningPlan`
- `crewai.utilities.rpm_controller`：`RPMController`
- `crewai.utilities.rw_lock`：`RWLock`
- `crewai.utilities.step_execution_context`：`StepExecutionContext`、`StepResult`
- `crewai.utilities.streaming`：`StreamingState`、`TaskInfo`
- `crewai.utilities.task_output_storage_handler`：`TaskOutputStorageHandler`
- `crewai.utilities.token_counter_callback`：`TokenCalcHandler`
- `crewai.utilities.training_converter`：`TrainingConverter`
- `crewai.utilities.training_handler`：`CrewTrainingHandler`
- `crewai.utilities.types`：`LLMMessage`
