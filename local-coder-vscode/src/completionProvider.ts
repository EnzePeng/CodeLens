import * as vscode from "vscode";
import { getConfig } from "./config";
import { infill } from "./llamaClient";

/**
 * 行内补全提供器：基于 FIM 在光标处生成 ghost text。
 *
 * VSCode 会在用户输入时（以及 debounce 后）调用 provideInlineCompletionItems。
 * 我们取光标前后的文本作为 prefix / suffix 交给本地模型做 Fill-In-the-Middle。
 */
export class LocalCoderInlineProvider implements vscode.InlineCompletionItemProvider {
  private inFlight?: AbortController;
  private debounceTimer?: NodeJS.Timeout;
  private readonly statusBar: vscode.StatusBarItem;

  constructor(statusBar: vscode.StatusBarItem) {
    this.statusBar = statusBar;
  }

  async provideInlineCompletionItems(
    document: vscode.TextDocument,
    position: vscode.Position,
    _context: vscode.InlineCompletionContext,
    token: vscode.CancellationToken
  ): Promise<vscode.InlineCompletionItem[] | undefined> {
    const cfg = getConfig();

    if (!cfg.enableInlineCompletion) {
      return undefined;
    }
    if (cfg.disabledLanguages.includes(document.languageId)) {
      return undefined;
    }

    // 防抖：在用户停止输入 debounceMs 之后才真正发请求。
    await this.debounce(cfg.debounceMs, token);
    if (token.isCancellationRequested) {
      return undefined;
    }

    const { prefix, suffix } = buildPrefixSuffix(
      document,
      position,
      cfg.maxPrefixChars,
      cfg.maxSuffixChars
    );

    // 空文档或仅有空白时不触发，避免无意义请求。
    if (prefix.trim().length === 0 && suffix.trim().length === 0) {
      return undefined;
    }

    // 取消上一个仍在进行的请求。
    this.inFlight?.abort();
    const controller = new AbortController();
    this.inFlight = controller;
    token.onCancellationRequested(() => controller.abort());

    this.setStatus(true);
    try {
      const raw = await infill({
        serverUrl: cfg.serverUrl,
        prefix,
        suffix,
        maxTokens: cfg.maxTokens,
        temperature: cfg.temperature,
        timeoutMs: cfg.timeoutMs,
        signal: controller.signal,
      });

      if (token.isCancellationRequested) {
        return undefined;
      }

      const text = postProcess(raw, suffix);
      if (!text) {
        return undefined;
      }

      const item = new vscode.InlineCompletionItem(
        text,
        new vscode.Range(position, position)
      );
      return [item];
    } catch (err) {
      // 网络/超时错误静默处理，仅在状态栏体现，避免打扰编码。
      if (!isAbortError(err)) {
        this.flashError();
      }
      return undefined;
    } finally {
      if (this.inFlight === controller) {
        this.inFlight = undefined;
      }
      this.setStatus(false);
    }
  }

  private debounce(ms: number, token: vscode.CancellationToken): Promise<void> {
    return new Promise((resolve) => {
      if (this.debounceTimer) {
        clearTimeout(this.debounceTimer);
      }
      this.debounceTimer = setTimeout(resolve, ms);
      token.onCancellationRequested(() => {
        if (this.debounceTimer) {
          clearTimeout(this.debounceTimer);
        }
        resolve();
      });
    });
  }

  private setStatus(loading: boolean): void {
    this.statusBar.text = loading
      ? "$(loading~spin) Local Coder"
      : "$(sparkle) Local Coder";
  }

  private flashError(): void {
    this.statusBar.text = "$(error) Local Coder";
    setTimeout(() => this.setStatus(false), 1500);
  }

  dispose(): void {
    this.inFlight?.abort();
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }
  }
}

/**
 * 从文档中提取光标前后的文本，并裁剪到配置的上限。
 */
export function buildPrefixSuffix(
  document: vscode.TextDocument,
  position: vscode.Position,
  maxPrefixChars: number,
  maxSuffixChars: number
): { prefix: string; suffix: string } {
  const fullStart = new vscode.Position(0, 0);
  const lastLine = document.lineCount - 1;
  const fullEnd = document.lineAt(lastLine).range.end;

  let prefix = document.getText(new vscode.Range(fullStart, position));
  let suffix = document.getText(new vscode.Range(position, fullEnd));

  if (prefix.length > maxPrefixChars) {
    prefix = prefix.slice(prefix.length - maxPrefixChars);
  }
  if (suffix.length > maxSuffixChars) {
    suffix = suffix.slice(0, maxSuffixChars);
  }
  return { prefix, suffix };
}

/**
 * 清理模型输出：去掉特殊 token、避免与后文重复。
 */
export function postProcess(raw: string, suffix: string): string {
  if (!raw) {
    return "";
  }
  let text = raw;

  // 去掉可能泄漏的 FIM / 特殊标记。
  text = text.replace(
    /<\|(fim_[a-z]+|endoftext|im_end|im_start|file_sep|repo_name)\|>/g,
    ""
  );

  // 如果补全结尾与后文开头重复，去掉重复部分，避免出现重复代码。
  const suffixHead = suffix.slice(0, 40).trimStart();
  if (suffixHead) {
    const idx = text.indexOf(suffixHead);
    if (idx >= 0) {
      text = text.slice(0, idx);
    }
  }

  // 去掉末尾多余空白，但保留有意义的换行结构。
  return text.replace(/\s+$/g, (m) => (m.includes("\n") ? "\n" : ""));
}

function isAbortError(err: unknown): boolean {
  if (err instanceof Error) {
    return err.message === "aborted" || err.name === "AbortError";
  }
  return false;
}
