type RecordItem = { id: string; kind: string; name: string; data: Record<string, any> };
const show = (value: unknown) => typeof value === "string" ? value : JSON.stringify(value, null, 2);

function Body({ title, value }: { title: string; value: unknown }) {
  if (value === undefined) return null;
  return <section className="eg-ops-content-block"><h3>{title}</h3><pre>{show(value) ?? "无"}</pre></section>;
}

function Messages({ messages }: { messages: unknown }) {
  if (!Array.isArray(messages)) return <Body title="消息" value={messages} />;
  return <div className="eg-ops-messages">{messages.map((message, i) =>
    <section className="eg-ops-message" key={i}>
      <h4><span>{i + 1}</span> {message.role || "unknown"}{message.tool_call_id && <small> · 工具回执 {message.tool_call_id}</small>}</h4>
      <pre>{show(message.content) ?? "本轮无文本；查看工具调用"}</pre>
      <Body title="模型请求的工具调用" value={message.tool_calls} />
      <Body title="附加消息字段" value={Object.keys(message).some(k => !["role", "content", "tool_calls", "tool_call_id"].includes(k)) ? Object.fromEntries(Object.entries(message).filter(([k]) => !["role", "content", "tool_calls", "tool_call_id"].includes(k))) : undefined} />
    </section>)}</div>;
}

function Request({ request }: { request: Record<string, any> }) {
  const { messages, tools, ...parameters } = request;
  return <>
    <h3>模型输入 / 提示词</h3>
    <Messages messages={messages} />
    <Body title="请求参数" value={parameters} />
    {tools !== undefined && <details className="eg-ops-content-block"><summary>工具定义 / Schema（{Array.isArray(tools) ? tools.length : "—"}）</summary><pre>{show(tools)}</pre></details>}
  </>;
}

export function RecordContent({ record, records }: { record: RecordItem; records: RecordItem[] }) {
  const data = record.data;
  const body = data.content || {};
  const capture = data.capture;
  const full = capture?.version === 1 && ["full_redacted", "truncated"].includes(capture?.mode);
  const prompt = data.promptId ? records.find(r => r.id === data.promptId && r.kind === "prompt") : undefined;
  return <div className="eg-ops-record-content" data-testid="record-content">
    <p className={`eg-ops-content-status ${capture?.truncated ? "limited" : ""}`}>
      {full ? capture.truncated ? "正文已达采集上限 · 截断位置有标记" : "已采集正文 · 密钥与媒体已脱敏" : capture?.mode === "unavailable" ? "本条正文采集失败 · 原业务调用不受影响" : "本条没有完整正文 · 历史摘要不能还原为原文"}
    </p>
    {record.kind === "prompt" && data.request && <Request request={data.request} />}
    {record.kind === "model" && <>
      {prompt?.data.request ? <Request request={prompt.data.request} /> : <p className="eg-ops-note">关联的输入快照不在当前数据包中。</p>}
      <Body title="模型原始输出（脱敏）" value={body.response} />
      <Body title="模型错误" value={body.error} />
      <Body title="调用与用量" value={{ model: data.model, operation: data.operation, httpStatus: data.httpStatus, providerRequestId: data.providerRequestId, usage: data.usage }} />
    </>}
    {record.name === "context.prepared" && <><h3>本轮组装的上下文</h3><Messages messages={body.messages} /><Body title="本轮可用工具" value={body.tools} /></>}
    {record.name === "model.output" && <Body title="交给 Agent 的模型输出" value={body.output} />}
    {["tool.started", "tool.finished"].includes(record.name) && <>
      <h3>工具：{data.tool || "unknown"}</h3>
      <Body title="工具参数" value={body.arguments} />
      {Array.isArray(body.positionalArguments) && body.positionalArguments.length > 0 && <Body title="位置参数" value={body.positionalArguments} />}
      <Body title="工具返回结果" value={body.result} />
      <Body title="工具错误" value={body.error} />
    </>}
    {record.name === "agent.result" && <>
      <Body title="最终回复（实际返回 App）" value={body.answer} />
      <Body title="最终工具回执" value={body.toolReceipts} />
      {body.error && <Body title="任务错误" value={body.error} />}
      <p className="eg-ops-note">这是运行时最终回复；业务校验或回退可能使它与模型原始输出不同。</p>
    </>}
    {record.name === "deployed_prompt" && <><Body title="当前进程的系统提示词" value={data.systemPrompt} /><Body title="工具定义" value={data.tools} /></>}
    <details className="eg-ops-content-block"><summary>查看原始记录 JSON</summary><pre>{JSON.stringify(record, null, 2)}</pre></details>
  </div>;
}
