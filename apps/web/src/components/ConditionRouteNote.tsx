import { Alert, Space, Tag, Typography } from "antd";
import type { ConditionProvenance } from "../api";
import { conditionRoute } from "../conditionRoute";

const { Paragraph, Text } = Typography;

/**
 * Why this record is decided the way it is, beside the condition it explains.
 *
 * The reviewer's question is asked by the box above this one. A record whose
 * source states its test in words shows no comparison there, and until this
 * existed the panel offered no account of that — so the honest reading of an
 * empty box was "the extraction failed here", 273 times in a row, with the
 * field holding the actual answer sitting unread in the payload.
 *
 * Placed under the condition rather than on the readiness tab on purpose. This
 * explains `rule.condition`, and an explanation of a thing belongs next to the
 * thing. Splitting them is what produced the defect being fixed: the same fact
 * was cut from the rule's description on the grounds that another surface
 * carried it, and no surface did.
 *
 * The route wording lives in `conditionRoute.ts` so every future caller says
 * the same thing, and so a test can enumerate what the server can emit and
 * check that all of it has words.
 */
export function ConditionRouteNote({
  provenance,
}: {
  provenance?: ConditionProvenance | null;
}) {
  const route = conditionRoute(provenance);
  if (!route) return null;

  // Keyed on content, never on the code. Only one case populates it today, and
  // a reader of this panel wants the text whenever there is text — tying the
  // block to a particular code would hide it the day a second case carries one.
  const expression = (provenance?.unsupported_expression ?? "").trim();

  // The figure two of the route wordings promise is "shown alongside". Keyed
  // on content for the same reason, and for a sharper one: the promise is made
  // by a sentence, so a code that carries a figure without being on a list
  // here would leave that sentence lying.
  const quantity = (provenance?.unprojected_quantity ?? "").trim();

  return (
    <Alert
      className="condition-route"
      type="info"
      showIcon
      title={
        <Space size={8} wrap>
          <Text strong>How this one is decided</Text>
          {route.route && <Tag color={route.color}>{route.route}</Tag>}
        </Space>
      }
      description={
        <>
          <Paragraph type="secondary" className="condition-route-reason">
            {route.reason}
          </Paragraph>
          {quantity && (
            <div className="condition-route-quantity">
              <Text type="secondary">The figure the source states, word for word:</Text>
              <Text code>{quantity}</Text>
            </div>
          )}
          {expression && (
            <div className="condition-route-expression">
              <Text type="secondary">The expression the extraction produced for it, word for word:</Text>
              <Text code>{expression}</Text>
            </div>
          )}
        </>
      }
    />
  );
}
