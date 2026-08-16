import { useEffect, useRef, useState } from "react";
import { Alert, Button, Modal, Tooltip, Typography } from "antd";
import { BulbOutlined } from "@ant-design/icons";
import { aiApi, type PolicyExplanation } from "../api";
import { describeApiFailure, type LoadState } from "../loadState";
import { DirectionalText } from "./DirectionalText";

const { Text } = Typography;

/**
 * A plain-language reading of one policy's record, on request.
 *
 * WHAT IT EXPLAINS, WHICH IS NOT WHAT A READER MIGHT ASSUME
 *
 * It explains **our extraction**, not the document. That distinction is the
 * whole of the design and the interface has to carry it, because a reader who
 * mistakes one for the other is worse off than before they clicked: they came
 * to check whether the decomposition is faithful, and a fluent paragraph
 * describing the decomposition reads exactly like a fluent paragraph describing
 * the source.
 *
 * So the document's own sentences are in this dialog, beside the reading, not
 * behind another click. The reading is checked *against* them rather than
 * *instead of* them, and the dialog says which is which in the words of its own
 * two headings rather than by styling alone.
 *
 * WHY IT IS NOT STYLED LIKE THE CARD'S QUOTATIONS
 *
 * `MarkedQuotation` renders the document's words, and everything about it —
 * the rule, the indent, the marks — signals "this is the source". This uses
 * none of it. It takes the `✦` and the "by this app" naming the generated
 * subject label established, so a reader who has learned what that mark means
 * on the card finds it meaning the same thing here.
 *
 * FOUR OUTCOMES, AND THEY ARE NOT THE SAME OUTCOME
 *
 * Nobody asked; asked and waiting; asked and the request failed; asked and
 * nothing usable came back. The last two are separated because a reader can act
 * on one and not the other — a failure is worth retrying and a refusal is not,
 * and a dialog that collapsed them would have people clicking again at
 * something that will decline again for the same reason.
 *
 * WHY A REFUSAL IS RENDERED HERE, HAVING BEEN SUPPRESSED ON THE CARD
 *
 * The generated subject label withholds its refusal, because that line sits in
 * the card's lead position unbidden and spending it to report having nothing to
 * add costs more attention than the fact is worth. Neither condition holds
 * here. This dialog exists because somebody pressed a button, and a button that
 * opens onto nothing has failed them; the reason is the answer to the question
 * they asked.
 */
export function PolicyExplainButton({
  provisionId,
  policyKey,
}: {
  /** The persisted grouping to explain. Absent when the policy is not one. */
  provisionId: string;
  /** For the dialog's title, so a reader knows which card they opened. */
  policyKey: string;
}) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<LoadState | "idle">("idle");
  const [result, setResult] = useState<PolicyExplanation | null>(null);
  const [failure, setFailure] = useState<string>("");

  // This button is not remounted when the policy under it changes. It sits in a
  // panel that swaps which record it shows while the button keeps its position,
  // so React reuses this instance and only the `provisionId` prop changes. A
  // reading generated for the previous policy is not about the one now on
  // screen, so on that change it is cleared and any open dialog is closed: the
  // next open asks about the policy now in hand rather than showing the last.
  const askedFor = useRef(provisionId);
  useEffect(() => {
    askedFor.current = provisionId;
    setOpen(false);
    setState("idle");
    setResult(null);
    setFailure("");
  }, [provisionId]);

  async function ask(regenerate = false) {
    const forPolicy = provisionId;
    setState("loading");
    setFailure("");
    try {
      const reading = await aiApi.explainPolicy(forPolicy, regenerate);
      // The reader may have moved to another policy while this was in flight.
      // A reading answered for a policy no longer on screen is dropped, never
      // shown under the one that replaced it.
      if (askedFor.current !== forPolicy) return;
      setResult(reading);
      setState("ready");
    } catch (error) {
      // The request never landed or the server refused it. Distinct from the
      // server answering that it has no explanation, which arrives as a
      // successful response carrying a code.
      if (askedFor.current !== forPolicy) return;
      setFailure(describeApiFailure(error));
      setState("unavailable");
    }
  }

  return (
    <>
      <Tooltip title="Read what this policy's extracted record says, in plain words. The document's own text is shown beside it.">
        <Button
          size="small"
          icon={<BulbOutlined />}
          data-testid="policy-explain-button"
          onClick={(event) => {
            event.stopPropagation();
            setOpen(true);
            if (state === "idle") void ask();
          }}
        >
          Explain
        </Button>
      </Tooltip>
      <Modal
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        width={760}
        title="What this policy's record says"
        aria-label={`What the record of policy ${policyKey} says`}
        data-testid="policy-explain-modal"
      >
        <div className="policy-explain" data-testid="policy-explain-body">
          {/* Said before the reading rather than after it. A caveat under a
              paragraph is read by someone who has already believed the
              paragraph. */}
          <Alert
            type="info"
            showIcon={false}
            className="policy-explain__scope"
            message={
              <Text type="secondary">
                This describes what this app extracted, not what the document
                says. The two agree only if the extraction is right, and that is
                what you are here to decide — so the document's own words are
                below, to read this against.
              </Text>
            }
          />

          {state === "loading" && (
            <p className="policy-explain__pending" data-testid="policy-explain-pending">
              Reading the record…
            </p>
          )}

          {state === "unavailable" && (
            <Alert
              type="warning"
              showIcon
              data-testid="policy-explain-failed"
              message="The request did not complete"
              description={
                <>
                  <p>{failure}</p>
                  <Button size="small" onClick={() => void ask()}>
                    Try again
                  </Button>
                </>
              }
            />
          )}

          {state === "ready" && result && (
            <>
              {result.explanation ? (
                <section
                  className="policy-explain__reading"
                  data-generated="true"
                  data-testid="policy-explain-reading"
                >
                  <p className="policy-explain__what">
                    <span className="policy-explain__mark" aria-hidden>
                      ✦
                    </span>{" "}
                    In plain words, by this app
                  </p>
                  {/* Unquoted, for the reason the subject label gives: quotation
                      marks would present these as somebody's exact words, and
                      they are nobody's. */}
                  <div className="policy-explain__text">
                    <DirectionalText>{result.explanation}</DirectionalText>
                  </div>
                  <p className="policy-explain__provenance">
                    <Text type="secondary">
                      Written by {result.model_deployment ?? "a language model"}
                      {result.generated_at
                        ? ` on ${new Date(result.generated_at).toLocaleString()}`
                        : ""}
                      {result.generated_earlier
                        ? ", from this record as it stands now."
                        : "."}{" "}
                      {!result.covers_every_rule &&
                        `It covers the first ${result.rules.length} of this policy's ${result.rule_count} rules; the rest are on the card and are unaffected.`}
                    </Text>
                  </p>
                  <Button size="small" onClick={() => void ask(true)}>
                    Write it again
                  </Button>
                </section>
              ) : (
                <Alert
                  type="info"
                  showIcon
                  data-testid="policy-explain-none"
                  message="No reading was written for this policy"
                  description={unavailableReason(result)}
                />
              )}

              <section className="policy-explain__source" data-testid="policy-explain-source">
                <h4 className="policy-explain__source-heading">
                  The document's own words, for each rule
                </h4>
                <ol className="policy-explain__rules">
                  {result.rules.map((rule, index) => (
                    <li key={rule.rule_id || index} className="policy-explain__rule">
                      <p className="policy-explain__rule-title">
                        <DirectionalText>{rule.title}</DirectionalText>
                      </p>
                      {rule.stated_text && (
                        <blockquote className="policy-explain__quote">
                          <DirectionalText>{rule.stated_text}</DirectionalText>
                        </blockquote>
                      )}
                    </li>
                  ))}
                </ol>
                {result.rules.length === 0 && (
                  <p>
                    <Text type="secondary">
                      This policy's rules recorded no source text, so there is
                      nothing here to read the record against. The rules
                      themselves are on the card.
                    </Text>
                  </p>
                )}
              </section>
            </>
          )}
        </div>
      </Modal>
    </>
  );
}

/**
 * Why no reading was written, in words a reviewer can act on.
 *
 * Every branch says what happened and what it means for them. None of them
 * describes either decision route, and none of them frames the outcome as
 * something this system was unable to do — a record that reads back as one
 * statement is a short policy, which is an ordinary thing for a document to
 * contain and not a defect in it or in us.
 */
function unavailableReason(result: PolicyExplanation): string {
  switch (result.unavailable_code) {
    case "record_states_a_single_rule":
      return "This policy states one rule. A reading of it could only repeat that rule in different words, sitting next to the document's own — so the document's words are below on their own, which is the shorter path to the same answer.";
    case "reply_no_shorter_than_the_source":
      return "What came back was as long as the passage it was standing in for, so it would have been a second copy of the text rather than a way through it. The document's words are below.";
    case "record_states_a_single_rule_and_no_text":
    case "no_record_to_explain":
      return "This policy's rules hold nothing to read back — no stated parts and no recorded text. The card shows what was extracted.";
    case "reply_declined_to_explain":
      return "The model was asked and answered that this record does not hold enough to describe. That is its answer rather than a failure to reach it, so asking again would put the same question to the same record.";
    case "reply_named_a_decision_route":
      return "What came back described how these rules would be decided rather than what they require, which is not what was asked for and is not what this dialog is for. Writing it again may produce a usable reading.";
    case "reply_unusable":
      return "Nothing usable came back. Writing it again may produce a reading.";
    case "model_call_failed":
      return "The request to the model did not complete. This is worth trying again — the record is unchanged and nothing about it caused this.";
    default:
      // No code and no explanation: nobody asked a model anything, because none
      // is configured on this server. Distinct from every branch above, all of
      // which report an attempt.
      return "No language model is configured on this server, so nothing was asked for. Everything below is from the record itself and is unaffected.";
  }
}
