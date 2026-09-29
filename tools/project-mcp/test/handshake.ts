import { call, connect } from "./client.ts";
const c = await connect();
const tools = await c.listTools();
console.log("tools:", tools.tools.length);
console.log(tools.tools.map((t) => t.name).join(" "));
const r = await call(c, "project_inspect_project");
console.log("inspect_project ok:", r.ok, r.data?.environment?.environment, r.ms, "ms");
await c.close();
