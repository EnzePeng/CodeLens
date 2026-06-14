import * as vscode from "vscode";
import { LocalCoderInlineProvider } from "./completionProvider";
import { getConfig } from "./config";
import { infill, completion } from "./llamaClient";

let inlineProvider: LocalCoderInlineProvider | undefined;

export function activate(context: vscode.ExtensionContext) {
  // Create status bar item
  const statusBar = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Right,
    100
  );
  statusBar.text = "$(sparkle) Local Coder";
  statusBar.tooltip = "Local Coder - 本地代码补全";
  statusBar.show();
  context.subscriptions.push(statusBar);

  // Register inline completion provider
  inlineProvider = new LocalCoderInlineProvider(statusBar);
  const selector = [
    { scheme: "file" },
    { language: "python" },
    { language: "javascript" },
    { language: "typescript" },
    { language: "javascriptreact" },
    { language: "typescriptreact" },
    { language: "go" },
    { language: "rust" },
    { language: "java" },
    { language: "c" },
    { language: "cpp" },
    { language: "csharp" },
    { language: "ruby" },
    { language: "php" },
    { language: "swift" },
    { language: "kotlin" },
  ];

  const disposable = vscode.languages.registerInlineCompletionItemProvider(
    selector,
    inlineProvider
  );
  context.subscriptions.push(disposable);

  // Register toggle command
  context.subscriptions.push(
    vscode.commands.registerCommand("localCoder.toggle", () => {
      const config = vscode.workspace.getConfiguration("localCoder");
      const current = config.get<boolean>("enableInlineCompletion", true);
      config.update("enableInlineCompletion", !current, vscode.ConfigurationTarget.Global);
      vscode.window.showInformationMessage(
        `Local Coder ${!current ? "已开启" : "已关闭"}`
      );
    })
  );

  // Register comment generation command
  context.subscriptions.push(
    vscode.commands.registerCommand("localCoder.generateComment", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showWarningMessage("没有打开的编辑器");
        return;
      }

      const selection = editor.document.getText(editor.selection);
      if (!selection) {
        vscode.window.showWarningMessage("请先选中需要生成注释的代码");
        return;
      }

      const cfg = getConfig();
      statusBar.text = "$(loading~spin) Local Coder";

      try {
        const language = editor.document.languageId;
        const prompt = `为以下${language}代码生成详细的中文注释。要求：
1. 解释代码的功能和目的
2. 说明关键参数和返回值
3. 标注重要的逻辑分支
4. 如果有潜在问题或优化建议，请指出

代码：
\`\`\`${language}
${selection}
\`\`\`

请直接输出注释后的代码，不要添加额外的解释：`;

        const result = await completion({
          serverUrl: cfg.serverUrl,
          prompt: prompt,
          maxTokens: 1024,
          temperature: 0.3,
          timeoutMs: 30000,
        });

        // 清理输出
        let comment = result.trim();
        // 移除可能的代码块标记
        comment = comment.replace(/^```[\s\S]*?\n/, "").replace(/\n```$/, "");

        // 在选中代码上方插入注释
        await editor.edit((editBuilder) => {
          const position = editor.selection.start;
          editBuilder.insert(position, comment + "\n\n");
        });

        vscode.window.showInformationMessage("注释已生成");
      } catch (err) {
        vscode.window.showErrorMessage(`注释生成失败: ${err}`);
      } finally {
        statusBar.text = "$(sparkle) Local Coder";
      }
    })
  );

  // Register manual trigger command
  context.subscriptions.push(
    vscode.commands.registerCommand("localCoder.triggerCompletion", () => {
      vscode.commands.executeCommand("editor.action.triggerSuggest");
    })
  );

  // Register server health check command
  context.subscriptions.push(
    vscode.commands.registerCommand("localCoder.checkServer", async () => {
      const cfg = getConfig();
      statusBar.text = "$(loading~spin) Local Coder";

      try {
        const https = cfg.serverUrl.startsWith("https") ? require("https") : require("http");
        const url = new URL(cfg.serverUrl);
        
        await new Promise<void>((resolve, reject) => {
          const req = https.get(
            {
              hostname: url.hostname,
              port: url.port,
              path: "/health",
              timeout: 5000,
            },
            (res: any) => {
              if (res.statusCode === 200) {
                vscode.window.showInformationMessage("模型服务连接正常");
                resolve();
              } else {
                vscode.window.showWarningMessage(`模型服务返回: ${res.statusCode}`);
                resolve();
              }
            }
          );
          req.on("error", (e: Error) => {
            reject(e);
          });
          req.on("timeout", () => {
            req.destroy();
            reject(new Error("连接超时"));
          });
        });
      } catch (err) {
        vscode.window.showErrorMessage(`模型服务连接失败: ${err}`);
      } finally {
        statusBar.text = "$(sparkle) Local Coder";
      }
    })
  );
}

export function deactivate() {
  inlineProvider?.dispose();
}
