import * as vscode from "vscode";

/**
 * 读取插件配置的辅助函数集合。
 * 所有配置项都定义在 package.json 的 contributes.configuration 中。
 */
export interface LocalCoderConfig {
  serverUrl: string;
  enableInlineCompletion: boolean;
  debounceMs: number;
  maxTokens: number;
  temperature: number;
  maxPrefixChars: number;
  maxSuffixChars: number;
  timeoutMs: number;
  disabledLanguages: string[];
}

const SECTION = "localCoder";

export function getConfig(): LocalCoderConfig {
  const c = vscode.workspace.getConfiguration(SECTION);
  return {
    serverUrl: stripTrailingSlash(c.get<string>("serverUrl", "http://127.0.0.1:8080")),
    enableInlineCompletion: c.get<boolean>("enableInlineCompletion", true),
    debounceMs: c.get<number>("debounceMs", 300),
    maxTokens: c.get<number>("maxTokens", 128),
    temperature: c.get<number>("temperature", 0.2),
    maxPrefixChars: c.get<number>("maxPrefixChars", 3000),
    maxSuffixChars: c.get<number>("maxSuffixChars", 1000),
    timeoutMs: c.get<number>("timeoutMs", 8000),
    disabledLanguages: c.get<string[]>("disabledLanguages", [
      "plaintext",
      "markdown",
      "scminput",
    ]),
  };
}

export async function setInlineCompletionEnabled(enabled: boolean): Promise<void> {
  const c = vscode.workspace.getConfiguration(SECTION);
  await c.update("enableInlineCompletion", enabled, vscode.ConfigurationTarget.Global);
}

function stripTrailingSlash(url: string): string {
  return url.replace(/\/+$/, "");
}
