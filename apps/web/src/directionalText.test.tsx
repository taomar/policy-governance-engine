/**
 * Text that mixes directions must reach the screen as the document's words.
 *
 * The defect these guard against is not a spelling mistake, it is a layout one:
 * a right-to-left run placed in a left-to-right container has its neutral
 * characters — digits, per-cent signs, brackets, commas — resolved against the
 * container instead of the run, so a quantity is laid out on the wrong side of
 * the phrase it qualifies and a reviewer reads a figure the document does not
 * state. In a policy platform the quantities are the operative content, so this
 * is not cosmetic.
 *
 * The fixtures below are frozen literals, read once from the bilingual source
 * PDF and checked by eye against it. They are deliberately *not* derived from
 * the application's own output at test time. A fixture taken from output moves
 * whenever the code moves, so it can only ever confirm that the code agrees
 * with itself; the whole reason this defect survived an earlier verbatim check
 * is that the check compared records against a store carrying the same fault.
 * Being literals, they are frozen at the moment they were verified and cannot
 * drift with the code.
 *
 * The strongest assertion here is the plainest one: what is rendered, read back
 * as text, is character-for-character what went in. That single check forbids
 * reversal, reordering, dropping, substitution and any "repair" of the stored
 * text, and it is what makes a copied rule paste as the document's words rather
 * than as whatever the screen happened to show.
 */
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DirectionalText } from "./components/DirectionalText";
import { baseDirection, hasRtl, splitDirectionalRuns } from "./directionalText";

/* -------------------------------------------------------------------------
 * Fixtures — read from the bilingual employee handbook, verified by eye.
 * ---------------------------------------------------------------------- */

/** A whole penalty clause in Arabic, including a bracketed Western numeral and
 *  Arabic punctuation. Reads: "Being late for work by up to (15) minutes
 *  without permission or an acceptable excuse, if it does not result in
 *  disrupting other workers." */
const ARABIC_CLAUSE =
  "التأخر عن مواعيد الحضور للعمل لغاية (15) دقيقة دون إذن أو عذر مقبول، إذا لم يترتب على ذلك تعطيل عمال آخرين.";

/** The English column of the same table row. */
const ENGLISH_CLAUSE =
  "Late for work, 15 minutes or less without permission or a valid reason, if it did not cause delay to other employees.";

/** One table cell carrying both languages — the English penalty followed by the
 *  Arabic for "written warning". */
const BILINGUAL_CELL = "Written Warning إنذار كتابي";

/** A penalty cell where a quantity sits on each side of the language boundary.
 *  This is the shape the defect corrupts: `10` and `%` are neutral characters,
 *  so which side of the Arabic phrase they land on is decided by the direction
 *  of whatever contains them. */
const DEDUCTION_CELL = "10% deduction حسم %10";

/** A day-count penalty, where the quantity is bracketed inside the Arabic. */
const DAY_DEDUCTION_CELL = "One (1) day deduction حسم (1) يوم";

/**
 * Genuinely damaged text, quoted from the violations-and-penalties table.
 *
 * English letters are shredded into Arabic words character by character. This
 * is not something writing produces and it is not this module's to repair — it
 * happens upstream in table extraction. It appears here because correct
 * directional rendering of damaged text would make it look like clean bilingual
 * prose, and that is the one outcome worth less than leaving it untidy.
 */
const SHREDDED_CELL = "سم أج ر yدaقائd ق( ا1ل)ت أeخrرO deduction";

/* -------------------------------------------------------------------------
 * The invariant that forbids repair.
 * ---------------------------------------------------------------------- */

describe("the rendered text is the stored text", () => {
  const everything = [
    ARABIC_CLAUSE,
    ENGLISH_CLAUSE,
    BILINGUAL_CELL,
    DEDUCTION_CELL,
    DAY_DEDUCTION_CELL,
    SHREDDED_CELL,
    "",
    "   ",
    "حسم ٢٥٪ من الأجر اليومي",
    "עברית 42% and English",
  ];

  it.each(everything)("splits %j into runs that rebuild it exactly", (source) => {
    const rebuilt = splitDirectionalRuns(source)
      .map((run) => run.text)
      .join("");

    expect(rebuilt).toBe(source);
  });

  it.each(everything.filter((s) => s.trim()))(
    "renders %j so that reading it back gives the same characters",
    (source) => {
      const { container } = render(<DirectionalText>{source}</DirectionalText>);

      // `textContent` is what a plain-text copy of the selection yields, so this
      // is the copy-and-paste round trip: a reviewer who copies a rule gets the
      // document's logical Unicode, not a visual rendering of it.
      expect(container.textContent).toBe(source);
    },
  );

  it("never emits a run whose characters are reordered", () => {
    // Stated separately from the round trip because a reversal inside one run
    // that is undone by a reversal in another would still rebuild the whole
    // string. Each run must be a contiguous slice of the source, in order.
    let cursor = 0;
    for (const run of splitDirectionalRuns(DEDUCTION_CELL)) {
      expect(DEDUCTION_CELL.slice(cursor, cursor + run.text.length)).toBe(run.text);
      cursor += run.text.length;
    }
    expect(cursor).toBe(DEDUCTION_CELL.length);
  });
});

/* -------------------------------------------------------------------------
 * Each run is marked and isolated.
 * ---------------------------------------------------------------------- */

describe("each directional run is marked and isolated", () => {
  it("gives an Arabic-only clause a right-to-left run", () => {
    const { container } = render(<DirectionalText>{ARABIC_CLAUSE}</DirectionalText>);
    const runs = [...container.querySelectorAll("bdi")];

    expect(runs.length).toBeGreaterThan(0);
    expect(runs.some((run) => run.getAttribute("dir") === "rtl")).toBe(true);
    expect(container.firstElementChild?.getAttribute("dir")).toBe("rtl");
  });

  it("marks the script rather than guessing a language", () => {
    // Arabic script carries Arabic, Farsi, Urdu and Pashto. Claiming `lang="ar"`
    // for all of them would have a screen reader pronounce Urdu as Arabic, so
    // what is stated is what was observed: the script.
    const { container } = render(<DirectionalText>{ARABIC_CLAUSE}</DirectionalText>);
    const arabic = container.querySelector('bdi[dir="rtl"]');

    expect(arabic?.getAttribute("lang")).toBe("und-Arab");
  });

  it("splits a bilingual cell into one run per language, in source order", () => {
    const { container } = render(<DirectionalText>{BILINGUAL_CELL}</DirectionalText>);
    const runs = [...container.querySelectorAll("bdi")];

    expect(runs.map((run) => run.getAttribute("dir"))).toEqual(["ltr", "rtl"]);
    expect(runs[0].textContent).toBe("Written Warning ");
    expect(runs[1].textContent).toBe("إنذار كتابي");
  });

  it("uses <bdi>, so isolation holds without this app's stylesheet", () => {
    // `<bdi>` carries `unicode-bidi: isolate` in the user-agent stylesheet. A
    // class that set it in App.css would be lost on a printed page, in an
    // exported fragment, or anywhere the stylesheet does not reach.
    const { container } = render(<DirectionalText>{BILINGUAL_CELL}</DirectionalText>);

    for (const run of container.querySelectorAll("[dir]")) {
      if (run === container.firstElementChild) continue;
      expect(run.tagName).toBe("BDI");
    }
  });

  it("keeps a quantity attached to the phrase it qualifies", () => {
    // `10` and `%` are neutral characters. The defect is that they resolve
    // against the container rather than the run, so the figure lands on the
    // wrong side of the Arabic phrase. Whichever run they belong to, they must
    // stay contiguous and in source order inside it.
    const { container } = render(<DirectionalText>{DEDUCTION_CELL}</DirectionalText>);
    const runs = [...container.querySelectorAll("bdi")];

    const arabicRun = runs.find((run) => run.getAttribute("dir") === "rtl");
    expect(arabicRun?.textContent).toContain("%10");
    expect(arabicRun?.textContent).not.toContain("01");

    const englishRun = runs.find((run) => run.getAttribute("dir") === "ltr");
    expect(englishRun?.textContent).toContain("10%");
  });

  it("keeps bracketed numerals whole inside a right-to-left run", () => {
    const { container } = render(<DirectionalText>{DAY_DEDUCTION_CELL}</DirectionalText>);
    const arabic = container.querySelector('bdi[dir="rtl"]');

    expect(arabic?.textContent).toContain("(1)");
  });

  it("keeps Arabic-Indic numerals in the run that carries them", () => {
    const source = "حسم ٢٥٪ من الأجر اليومي";
    const { container } = render(<DirectionalText>{source}</DirectionalText>);

    expect(container.textContent).toBe(source);
    expect(container.querySelector('bdi[dir="rtl"]')?.textContent).toContain("٢٥٪");
  });
});

/* -------------------------------------------------------------------------
 * The control: text in the interface's own direction must not move.
 * ---------------------------------------------------------------------- */

describe("text that needs nothing is left alone", () => {
  it("renders an English-only clause with no wrapping and no direction", () => {
    const { container } = render(<DirectionalText>{ENGLISH_CLAUSE}</DirectionalText>);

    expect(container.querySelectorAll("bdi")).toHaveLength(0);
    expect(container.firstElementChild?.hasAttribute("dir")).toBe(false);
    expect(container.textContent).toBe(ENGLISH_CLAUSE);
  });

  it("produces the same DOM as a bare span for English", () => {
    const { container: withComponent } = render(
      <DirectionalText className="policy-row-title">{ENGLISH_CLAUSE}</DirectionalText>,
    );
    const { container: bare } = render(
      <span className="policy-row-title">{ENGLISH_CLAUSE}</span>,
    );

    expect(withComponent.innerHTML).toBe(bare.innerHTML);
  });

  it("passes non-string children through untouched", () => {
    const { container } = render(
      <DirectionalText>
        <em>already an element</em>
      </DirectionalText>,
    );

    expect(container.querySelector("em")?.textContent).toBe("already an element");
    expect(container.querySelectorAll("bdi")).toHaveLength(0);
  });
});

/* -------------------------------------------------------------------------
 * Damaged text must not be dressed up as prose.
 * ---------------------------------------------------------------------- */

describe("text that was shredded upstream is marked, not tidied", () => {
  it("marks a run whose scripts alternate faster than they form words", () => {
    const { container } = render(<DirectionalText>{SHREDDED_CELL}</DirectionalText>);
    const flagged = [...container.querySelectorAll('[data-interleaved="true"]')];

    expect(flagged.length).toBeGreaterThan(0);
    expect(flagged[0].getAttribute("title")).toMatch(/damaged/i);
  });

  it("still shows the damaged characters exactly as stored", () => {
    // Marking is not censoring. The reviewer needs to see what is there, and
    // nothing may be substituted or reconstructed.
    const { container } = render(<DirectionalText>{SHREDDED_CELL}</DirectionalText>);

    expect(container.textContent).toBe(SHREDDED_CELL);
  });

  it("does not mark ordinary bilingual text", () => {
    // The opposite failure, and the more damaging one: if the marker fired on
    // well-formed bilingual text, every Arabic rule in the product would be
    // presented as damaged and the signal would be worthless.
    for (const clean of [BILINGUAL_CELL, DEDUCTION_CELL, DAY_DEDUCTION_CELL, ARABIC_CLAUSE]) {
      const { container } = render(<DirectionalText>{clean}</DirectionalText>);
      expect(container.querySelectorAll('[data-interleaved="true"]')).toHaveLength(0);
    }
  });

  it("does not mark two words merely joined without a space", () => {
    // A missing space is a typo, not shredding. The test is whether the scripts
    // interleave, not whether they touch.
    const { container } = render(<DirectionalText>{"العربيةEnglish"}</DirectionalText>);

    expect(container.querySelectorAll('[data-interleaved="true"]')).toHaveLength(0);
  });
});

/* -------------------------------------------------------------------------
 * Generality: nothing here knows about Arabic.
 * ---------------------------------------------------------------------- */

describe("direction is read from Unicode, not from a language list", () => {
  it.each([
    ["Hebrew", "שלום 42% world", "und-Hebr"],
    ["Thaana", "ދިވެހި 42% world", "und-Thaa"],
    ["Syriac", "ܠܫܢܐ 42% world", "und-Syrc"],
    ["N'Ko", "ߒߞߏ 42% world", "und-Nkoo"],
  ])("treats %s as right-to-left", (_name, source, subtag) => {
    const { container } = render(<DirectionalText>{source}</DirectionalText>);
    const rtl = container.querySelector('bdi[dir="rtl"]');

    expect(rtl).not.toBeNull();
    expect(rtl?.getAttribute("lang")).toBe(subtag);
    expect(container.textContent).toBe(source);
    expect(hasRtl(source)).toBe(true);
  });

  it("gives a single foreign term inside English its own run and moves nothing else", () => {
    const source = "The Arabic term إجازة means leave.";
    const { container } = render(<DirectionalText>{source}</DirectionalText>);
    const runs = [...container.querySelectorAll("bdi")];

    expect(runs.map((run) => run.getAttribute("dir"))).toEqual(["ltr", "rtl", "ltr"]);
    expect(runs[1].textContent).toBe("إجازة ");
    expect(container.textContent).toBe(source);
    // The sentence is English, so the block stays left-to-right and the term is
    // an island within it.
    expect(baseDirection(source)).toBe("ltr");
  });

  it("takes a block's direction from where the passage starts, not from a majority", () => {
    // A rule quoted in English with several Arabic terms is an English rule and
    // is read from the left, however many Arabic characters it contains.
    expect(baseDirection(ENGLISH_CLAUSE)).toBe("ltr");
    expect(baseDirection(ARABIC_CLAUSE)).toBe("rtl");
    expect(baseDirection(BILINGUAL_CELL)).toBe("ltr");
    expect(baseDirection("42% — 15 (30)")).toBe("auto");
  });
});

/* -------------------------------------------------------------------------
 * Parallel columns.
 * ---------------------------------------------------------------------- */

describe("parallel columns are aligned to their own side", () => {
  it("aligns each cell from the side its own text starts", () => {
    // One rule does both: `text-align: start` follows the `dir` on the element,
    // so an Arabic cell is right-aligned and an English cell left-aligned
    // without either being named.
    const { container } = render(
      <table>
        <tbody>
          <tr>
            <DirectionalText as="td" align>
              {ENGLISH_CLAUSE}
            </DirectionalText>
            <DirectionalText as="td" align>
              {ARABIC_CLAUSE}
            </DirectionalText>
          </tr>
        </tbody>
      </table>,
    );

    const [english, arabic] = [...container.querySelectorAll("td")];

    expect(english.className).toContain("directional-text--block");
    expect(arabic.className).toContain("directional-text--block");
    expect(english.hasAttribute("dir")).toBe(false);
    expect(arabic.getAttribute("dir")).toBe("rtl");
  });

  it("does not let one cell reorder the next", () => {
    // Isolation is the whole point of `<bdi>`: an Arabic cell ending in a
    // number and an English cell beginning with one must not merge into a
    // single bidirectional run across the boundary.
    const { container } = render(
      <div>
        <DirectionalText>{"حسم %10"}</DirectionalText>
        <DirectionalText>{"20% deduction"}</DirectionalText>
      </div>,
    );

    expect(container.textContent).toBe("حسم %1020% deduction");
    for (const run of container.querySelectorAll("bdi")) {
      expect(run.tagName).toBe("BDI");
    }
  });
});
