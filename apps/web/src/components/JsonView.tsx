import { useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { Button, Typography } from "antd";
import { CopyOutlined, CheckOutlined, DownloadOutlined } from "@ant-design/icons";

const { Text } = Typography;

/**
 * Matches one JSON token. The optional second group is the `:` that follows a
 * key, which is the only thing distinguishing an object key from a string
 * value — so keys and values can be coloured differently.
 */
const TOKEN =
  /("(?:\\.|[^"\\])*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false)\b|\b(null)\b/g;

/**
 * Tokenizes one line of pretty-printed JSON into coloured spans.
 *
 * Deliberately builds React elements rather than an HTML string: rule content
 * is user/AI-supplied and would otherwise need manual escaping before hitting
 * `dangerouslySetInnerHTML`. React escapes text children for us, so this is
 * XSS-safe by construction rather than by remembering to escape.
 *
 * `JSON.stringify` never emits a raw newline inside a string (it escapes them
 * as `\n`), so tokenizing line-by-line can't split a token in half.
 */
function highlightLine(line: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let key = 0;
  TOKEN.lastIndex = 0;

  let m: RegExpExecArray | null;
  while ((m = TOKEN.exec(line)) !== null) {
    if (m.index > last) out.push(line.slice(last, m.index));

    const [, str, colon, num, bool, nul] = m;
    if (str !== undefined) {
      out.push(
        <span key={key++} className={colon ? "json-key" : "json-string"}>
          {str}
        </span>
      );
      if (colon) out.push(colon);
    } else if (num !== undefined) {
      out.push(
        <span key={key++} className="json-number">
          {num}
        </span>
      );
    } else if (bool !== undefined) {
      out.push(
        <span key={key++} className="json-boolean">
          {bool}
        </span>
      );
    } else if (nul !== undefined) {
      out.push(
        <span key={key++} className="json-null">
          {nul}
        </span>
      );
    }
    last = m.index + m[0].length;
  }

  if (last < line.length) out.push(line.slice(last));
  return out;
}

interface JsonViewProps {
  /** Any JSON-serializable value. Serialized with 2-space indentation. */
  value: unknown;
  /** Filename used by the download button (`.json` appended if absent). */
  downloadName?: string;
  /** Optional cap for the code area; capped viewers scroll vertically. */
  maxHeight?: CSSProperties["maxHeight"];
}

/**
 * Read-only, syntax-highlighted JSON viewer with copy and download.
 *
 * No syntax-highlighting dependency: a single regex covers the whole JSON
 * grammar, which is proportionate here — pulling in a highlighter to render
 * one object would be far more weight than the problem deserves.
 */
export function JsonView({ value, downloadName = "data.json", maxHeight }: JsonViewProps) {
  const [copied, setCopied] = useState(false);

  const json = useMemo(() => {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      // Cyclic or otherwise unserializable — surface it rather than crashing
      // the whole inspector tab.
      return "// Unable to serialize this value as JSON.";
    }
  }, [value]);

  const lines = useMemo(() => json.split("\n"), [json]);
  const codeStyle = maxHeight === undefined ? undefined : ({ maxHeight, overflowY: "auto" } satisfies CSSProperties);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(json);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  const download = () => {
    const name = downloadName.endsWith(".json") ? downloadName : `${downloadName}.json`;
    const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="json-view">
      <div className="json-view-toolbar">
        <Text type="secondary" className="json-view-meta">
          {lines.length} lines · {(new TextEncoder().encode(json).length / 1024).toFixed(1)} KB
        </Text>
        <div className="json-view-actions">
          <Button
            size="small"
            icon={copied ? <CheckOutlined /> : <CopyOutlined />}
            onClick={copy}
            title="Copy the full JSON to the clipboard"
          >
            {copied ? "Copied" : "Copy"}
          </Button>
          <Button size="small" icon={<DownloadOutlined />} onClick={download} title="Download as a .json file">
            Download
          </Button>
        </div>
      </div>
      <pre className="json-view-code" style={codeStyle}>
        <code>
          {lines.map((line, i) => (
            <div className="json-line" key={i}>
              <span className="json-line-no" aria-hidden="true">
                {i + 1}
              </span>
              <span className="json-line-text">{highlightLine(line)}</span>
            </div>
          ))}
        </code>
      </pre>
    </div>
  );
}
