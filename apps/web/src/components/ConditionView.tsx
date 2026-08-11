import { Tree, Typography } from "antd";
import type { ConditionNode } from "../api";
import { OPERATOR_SYMBOLS, formatConditionValue as formatValue, formatFactor } from "../ruleDisplay";

const { Text } = Typography;

interface TreeDatum {
  key: string;
  title: React.ReactNode;
  children?: TreeDatum[];
}

let keySeq = 0;

function buildTreeData(node: ConditionNode): TreeDatum {
  const key = `cond-${keySeq++}`;

  if (node.type === "factComparison") {
    const symbol = OPERATOR_SYMBOLS[node.operator] ?? node.operator;
    const showValue = !["exists", "isNull"].includes(node.operator);
    return {
      key,
      title: (
        <span className="cond-leaf">
          <Text code className="cond-fact">
            {node.fact}
          </Text>
          <Text strong className="cond-op">
            {symbol}
          </Text>
          {showValue && (
            <Text keyboard className="cond-value">
              {formatValue(node.value)}
            </Text>
          )}
        </span>
      ),
    };
  }

  if (node.type === "factRelativeComparison") {
    const symbol = OPERATOR_SYMBOLS[node.operator] ?? node.operator;
    // The referenced fact is rendered with the same `cond-fact` treatment as
    // the subject, because it is a fact path the fact model must supply too —
    // styling it as a literal value would hide that it is a second input.
    return {
      key,
      title: (
        <span className="cond-leaf">
          <Text code className="cond-fact">
            {node.fact}
          </Text>
          <Text strong className="cond-op">
            {symbol}
          </Text>
          {node.reference.factor !== 1 && (
            <Text keyboard className="cond-value">
              {formatFactor(node.reference.factor)} of
            </Text>
          )}
          <Text code className="cond-fact">
            {node.reference.fact}
          </Text>
        </span>
      ),
    };
  }

  if (node.type === "all" || node.type === "any") {
    const children = node.type === "all" ? node.all : node.any;
    const label = node.type === "all" ? "ALL of" : "ANY of";
    return {
      key,
      title: (
        <Text strong className="cond-group-label">
          {label}
        </Text>
      ),
      children: children.map(buildTreeData),
    };
  }

  // not
  return {
    key,
    title: (
      <Text strong className="cond-group-label">
        NOT
      </Text>
    ),
    children: [buildTreeData(node.not)],
  };
}

/**
 * Recursively renders a ConditionNode (factComparison / all / any / not) as
 * a readable, indented tree instead of raw JSON — using Ant Design's Tree
 * component for clean guide lines and expand/collapse affordance.
 */
export function ConditionView({ node }: { node: ConditionNode }) {
  keySeq = 0;
  const treeData = [buildTreeData(node)];
  return (
    <Tree
      treeData={treeData}
      defaultExpandAll
      selectable={false}
      showLine={{ showLeafIcon: false }}
      className="cond-tree"
    />
  );
}
