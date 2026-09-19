import type { Card } from '../types'
import { formatSalary, formatValuePerMillion } from '../format'
import LiveStatGraph from './LiveStatGraph'

export default function CardResult({ card }: { card: Card }) {
  if (card.void) {
    return (
      <div className="card-result card-result--void">
        <strong>Build voided:</strong> {card.void_reason}
      </div>
    )
  }

  return (
    <div className="card-result">
      <LiveStatGraph ratings={card.ratings} />

      <div className="card-result__header">
        <div>
          <div className="card-result__ovr">{card.ovr}</div>
          <div className="card-result__ovr-label">OVR</div>
        </div>
        <div className="card-result__meta">
          <div>{formatSalary(card.contract)}/yr</div>
          <div>{formatValuePerMillion(card.ovr, card.contract)} OVR per $M</div>
          {/* The card is keyed on a uid; this is the only part of it a reader
              can actually recognise. */}
          <div className="card-result__date">
            created {card.date}
            {card.creator_name ? ` by ${card.creator_name}` : ''}
          </div>
        </div>
      </div>

      <table className="card-result__table">
        <thead>
          <tr>
            <th>Attribute</th>
            <th>Rating</th>
            <th>Player</th>
            <th>Salary</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {card.ratings.map((r) => (
            <tr key={r.slot}>
              <td>{r.label}</td>
              <td className="card-result__rating">{r.rating}</td>
              <td>{r.player_name}</td>
              <td>{formatSalary(r.salary)}</td>
              <td className="card-result__note">{r.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
