/**
 * Which language this dialog's answers come back in.
 *
 * WHY NATIVE RADIOS
 *
 * A group of native `<input type="radio">` in a `radiogroup` is a real choice
 * to every assistive technology and to the keyboard, with arrow-key movement,
 * a single tab stop and a `checked` state, none of which has to be written
 * here or can drift. A row of styled `<button>`s would need all of it
 * reimplemented and would still announce two letters.
 *
 * WHAT A SCREEN READER HEARS
 *
 * The visible label is the two-letter form the request asked for, and two
 * letters are not a language when read aloud. So the visible text is
 * `aria-hidden` and each input carries the language's own name for itself as
 * its accessible name — "English", "العربية" — while the group carries a
 * sentence saying what is being chosen and that it reaches this dialog alone.
 *
 * IT DOES NOT KNOW HOW MANY LANGUAGES THERE ARE
 *
 * The options are whatever it is handed. Nothing here counts them, pairs them,
 * or names one.
 */
import type { AskAnswerLanguage } from "../askAnswerLanguage";
import { DirectionalText } from "./DirectionalText";

export function AnswerLanguageToggle({
  languages,
  value,
  onChange,
  label,
  scopeNote,
}: {
  languages: readonly AskAnswerLanguage[];
  value: AskAnswerLanguage;
  onChange: (language: AskAnswerLanguage) => void;
  /** Accessible name of the whole group, in the language now selected. */
  label: string;
  /** Said next to the control, so the scope is not a thing you must discover. */
  scopeNote: string;
}) {
  return (
    <div
      className="ask-rule-language"
      role="radiogroup"
      aria-label={`${label} — ${scopeNote}`}
      data-testid="ask-rule-language"
    >
      {languages.map((language) => {
        const selected = language.tag === value.tag;
        return (
          <label
            key={language.tag}
            className={`ask-rule-language__option${selected ? " ask-rule-language__option--on" : ""}`}
            title={language.endonym}
          >
            <input
              type="radio"
              className="ask-rule-language__input"
              name="ask-rule-answer-language"
              value={language.tag}
              checked={selected}
              onChange={() => onChange(language)}
              // The name a screen reader announces. The two letters beside it
              // are for the eye only.
              aria-label={language.endonym}
              data-testid={`ask-rule-language-${language.tag}`}
            />
            <span aria-hidden className="ask-rule-language__text" lang={language.tag}>
              {/* Short labels are text in a language too — one of them will be
                  in a right-to-left script the day a third row is added. */}
              <DirectionalText>{language.shortLabel}</DirectionalText>
            </span>
          </label>
        );
      })}
    </div>
  );
}
