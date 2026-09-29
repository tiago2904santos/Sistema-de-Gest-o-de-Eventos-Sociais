/** MCP sanity: handshake, lista de ferramentas e uma chamada real (usado no CI e no doctor). */
import { call, connect } from "./client.ts";

const c = await connect();
const tools = (await c.listTools()).tools;
const r = await call(c, "project_inspect_project");
const k = await call(c, "knowledge_search", { query: "catraca acessibilidade" });
await c.close();
const ok = tools.length >= 100 && r.ok && !!r.data?.environment && k.ok && k.data.results.length > 0;
console.log(JSON.stringify({ ok, tools: tools.length, environment: r.data?.environment?.environment, knowledge_hits: k.data?.results?.length, ms: r.ms + k.ms }));
process.exit(ok ? 0 : 1);
