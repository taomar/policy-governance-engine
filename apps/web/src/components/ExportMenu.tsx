/**
 * Small reusable "Export" dropdown offering JSON / JSONL / CSV — used
 * anywhere a set of rules can be downloaded (policy version rule list,
 * candidate rule queue). Delegates the actual fetch+download to the
 * caller-supplied `onExport` so this component stays format-agnostic about
 * *what* it's exporting.
 */
import { useState } from "react";
import { Button, Dropdown, message, type MenuProps } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import type { ExportFormat } from "../api";

const FORMAT_LABELS: Record<ExportFormat, string> = {
  json: "JSON (.json)",
  jsonl: "JSON Lines (.jsonl)",
  csv: "CSV (.csv)",
};

interface ExportMenuProps {
  onExport: (format: ExportFormat) => Promise<void>;
  label?: string;
  size?: "small" | "middle" | "large";
}

export function ExportMenu({ onExport, label = "Export", size = "middle" }: ExportMenuProps) {
  const [busy, setBusy] = useState(false);

  const items: MenuProps["items"] = (Object.keys(FORMAT_LABELS) as ExportFormat[]).map((fmt) => ({
    key: fmt,
    label: FORMAT_LABELS[fmt],
  }));

  const handleClick: MenuProps["onClick"] = async ({ key }) => {
    setBusy(true);
    try {
      await onExport(key as ExportFormat);
    } catch (e) {
      message.error(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dropdown menu={{ items, onClick: handleClick }} trigger={["click"]}>
      <Button icon={<DownloadOutlined />} loading={busy} size={size}>
        {label}
      </Button>
    </Dropdown>
  );
}
