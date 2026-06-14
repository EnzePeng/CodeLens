import * as http from "http";
import * as https from "https";
import { URL } from "url";

/**
 * 与本地 llama.cpp 服务通信的轻量客户端。
 * 仅依赖 Node 内置的 http/https 模块，无需第三方依赖。
 */

export interface InfillParams {
  serverUrl: string;
  prefix: string;
  suffix: string;
  maxTokens: number;
  temperature: number;
  timeoutMs: number;
  /** 额外上下文，例如其它文件片段（可选）。 */
  extraContext?: { filename?: string; text: string }[];
  signal?: AbortSignal;
}

export interface CompletionParams {
  serverUrl: string;
  prompt: string;
  maxTokens: number;
  temperature: number;
  timeoutMs: number;
  stop?: string[];
  signal?: AbortSignal;
}

/**
 * 调用 /infill 端点完成 FIM（Fill-In-the-Middle）补全。
 * llama.cpp 会用模型自带的 FIM 特殊 token 组装提示。
 */
export async function infill(params: InfillParams): Promise<string> {
  const body: Record<string, unknown> = {
    input_prefix: params.prefix,
    input_suffix: params.suffix,
    n_predict: params.maxTokens,
    temperature: params.temperature,
    top_p: 0.9,
    stream: false,
    // 遇到这些标记说明模型想换主题/结束，提前停止以保证补全简洁。
    stop: ["<|file_sep|>", "<|repo_name|>", "<|endoftext|>"],
  };
  if (params.extraContext && params.extraContext.length > 0) {
    body.input_extra = params.extraContext.map((e) => ({
      filename: e.filename ?? "",
      text: e.text,
    }));
  }

  const json = await postJson(
    `${params.serverUrl}/infill`,
    body,
    params.timeoutMs,
    params.signal
  );
  return extractContent(json);
}

/**
 * 调用 /completion 端点做通用文本补全（用于注释生成等场景）。
 */
export async function completion(params: CompletionParams): Promise<string> {
  const body: Record<string, unknown> = {
    prompt: params.prompt,
    n_predict: params.maxTokens,
    temperature: params.temperature,
    top_p: 0.9,
    stream: false,
    cache_prompt: true,
  };
  if (params.stop && params.stop.length > 0) {
    body.stop = params.stop;
  }

  const json = await postJson(
    `${params.serverUrl}/completion`,
    body,
    params.timeoutMs,
    params.signal
  );
  return extractContent(json);
}

/**
 * 检查服务是否在线，返回 /health 的状态字符串。
 */
export async function checkHealth(serverUrl: string, timeoutMs = 3000): Promise<string> {
  const json = await getJson(`${serverUrl}/health`, timeoutMs);
  if (json && typeof json === "object" && "status" in json) {
    return String((json as { status: unknown }).status);
  }
  return "unknown";
}

function extractContent(json: unknown): string {
  if (json && typeof json === "object" && "content" in json) {
    const content = (json as { content: unknown }).content;
    return typeof content === "string" ? content : "";
  }
  return "";
}

function postJson(
  url: string,
  body: unknown,
  timeoutMs: number,
  signal?: AbortSignal
): Promise<unknown> {
  const payload = Buffer.from(JSON.stringify(body), "utf8");
  return request(url, "POST", payload, timeoutMs, signal);
}

function getJson(url: string, timeoutMs: number, signal?: AbortSignal): Promise<unknown> {
  return request(url, "GET", null, timeoutMs, signal);
}

function request(
  url: string,
  method: "GET" | "POST",
  payload: Buffer | null,
  timeoutMs: number,
  signal?: AbortSignal
): Promise<unknown> {
  return new Promise((resolve, reject) => {
    let parsed: URL;
    try {
      parsed = new URL(url);
    } catch (e) {
      reject(new Error(`非法的服务地址: ${url}`));
      return;
    }

    const transport = parsed.protocol === "https:" ? https : http;
    const headers: Record<string, string> = { Accept: "application/json" };
    if (payload) {
      headers["Content-Type"] = "application/json";
      headers["Content-Length"] = String(payload.length);
    }

    const req = transport.request(
      {
        hostname: parsed.hostname,
        port: parsed.port,
        path: parsed.pathname + parsed.search,
        method,
        headers,
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (chunk) => chunks.push(chunk as Buffer));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          const status = res.statusCode ?? 0;
          if (status < 200 || status >= 300) {
            reject(new Error(`HTTP ${status}: ${text.slice(0, 200)}`));
            return;
          }
          try {
            resolve(text ? JSON.parse(text) : {});
          } catch (e) {
            reject(new Error(`响应不是合法 JSON: ${text.slice(0, 200)}`));
          }
        });
      }
    );

    req.on("error", (err) => reject(err));
    req.setTimeout(timeoutMs, () => {
      req.destroy(new Error(`请求超时 (${timeoutMs}ms)`));
    });

    if (signal) {
      if (signal.aborted) {
        req.destroy(new Error("aborted"));
      } else {
        signal.addEventListener("abort", () => req.destroy(new Error("aborted")), {
          once: true,
        });
      }
    }

    if (payload) {
      req.write(payload);
    }
    req.end();
  });
}
