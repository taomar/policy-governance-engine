import type { GroundingRef, SizeRef } from '../contracts/caseDecision'

/**
 * What the fabrication guard refused, and whether the record fit.
 *
 * v1 reported one grounding block because it ran one gather. v2 grounds each
 * track separately, so a refused citation belongs to a named track — and saying
 * which one matters: a fabricated citation under the verdict track is a claim
 * about *this case* that was invented, while one under the information track is
 * an invented claim about what a policy says. Merging them into a single count
 * would lose the distinction and flatter the worse of the two.
 *
 * This is a notice, not a card. It renders nothing at all when there is nothing
 * to report, because a panel reading "0 fabricated citations" is decoration
 * pretending to be evidence.
 */

export interface TrackGrounding {
  track: string
  grounding: GroundingRef | null | undefined
}

export function GroundingNotices({
  tracks,
  size,
}: {
  tracks: TrackGrounding[]
  size?: SizeRef | null
}) {
  const refused = tracks
    .map(({ track, grounding }) => ({
      track,
      citations: (grounding?.fabricated_citations ?? []) as string[],
    }))
    .filter((entry) => entry.citations.length > 0)

  const oversize = size?.oversize === true

  if (refused.length === 0 && !oversize) return null

  return (
    <>
      {refused.map(({ track, citations }) => (
        <div
          className="banner banner--action"
          key={track}
          data-testid="playground-fabricated"
          data-track={track}
        >
          <strong className="banner__heading">
            {citations.length === 1
              ? `A fabricated citation was refused on the ${track} track`
              : `${citations.length} fabricated citations were refused on the ${track} track`}
          </strong>
          <span className="banner__body">
            The answer tried to cite {citations.join(', ')},{' '}
            {citations.length === 1 ? 'which is not a rule' : 'which are not rules'} in the
            evaluated policies. {citations.length === 1 ? 'It was' : 'They were'} dropped and
            reported here rather than shown as evidence.
          </span>
        </div>
      ))}

      {oversize ? (
        <div className="banner banner--action" data-testid="playground-oversize">
          <strong className="banner__heading">
            The evaluated policy payload was too large to read in one grounded pass
          </strong>
          <span className="banner__body">No partial answer should be treated as complete.</span>
        </div>
      ) : null}
    </>
  )
}
